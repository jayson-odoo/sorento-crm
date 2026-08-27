"""S2 / R8 - the rows behind the SPO, Incoming PL and PO cells of the loading plan.

`PLAN-scm-fulfilment-feedback-p4.md` section 2, AC-B4 / AC-B5. The contract this file
exists to hold is ONE sentence: the drill's `total` IS the figure the cell shows, for the
same product, because both come from one predicate. Every kind therefore asserts the drill
against `_stock_context`'s own output as the build returns it, never against a number typed
into the test - a predicate that drifts on one side and not the other is exactly the bug the
endpoint was created to make impossible.

Seeds its own chain under a marker-prefixed tag (CI's database is empty), reusing the
container-request suite's own seed helpers so the two suites cannot disagree about what an
open PO line or a landed shipment looks like.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.procurement import InboundShipment, SPOAllocation
from tests.scm.conftest import requires_pg
from tests.scm.test_container_request import (
    BUILD_URL,
    _incoming_spo,
    _on_hand,
    _outstanding_po,
    _packing_list,
    _row,
    _so,
    _warehouse,
)
from tests.scm.test_loading_plan import World
from tests.scm.test_outstanding_import_routes import as_company_user

pytestmark = requires_pg

MARKER = "ZZCRD"

DRILL_URL = "/api/v1/scm/container-requests/drill"


def _drill(app, supplier_id: str, product_id: str, kind: str):
    return TestClient(app).get(
        DRILL_URL,
        params={"supplier_id": supplier_id, "product_id": product_id, "kind": kind},
    )


def _cell(app, w: World, key: str) -> dict:
    """The row the loading plan grid draws, so a test can read the cell it drills into."""
    r = TestClient(app).post(BUILD_URL, json={"supplier_id": str(w.supplier.id)})
    assert r.status_code == 200, r.text
    return _row(r.json()["rows"], key, w)


def _landed_spo(db, w: World, key: str, wh, qty: float, *, arrived: date) -> None:
    """An SPO whose shipment has landed - History, never Open (`on_order_v`'s own rule)."""
    ship = InboundShipment(
        id=str(uuid.uuid4()),
        shipment_number=f"{MARKER}-SH-{uuid.uuid4().hex[:8]}",
        supplier_id=w.supplier.id,
        shipment_date=arrived - timedelta(days=30),
        estimated_arrival_date=arrived,
        actual_arrival_date=arrived,
        shipment_status="fully_received",
    )
    db.add(ship)
    db.flush()
    db.add(
        SPOAllocation(
            id=str(uuid.uuid4()),
            spo_number=f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}",
            inbound_shipment_id=ship.id,
            product_id=w.product(key).id,
            warehouse_id=wh.id,
            allocated_quantity=qty,
            quantity_received=qty,
            receipt_status="fully_received",
        )
    )
    db.flush()


def _closed_po(db, w: World, key: str, wh, qty: float, *, issued: date) -> None:
    """A purchase order line that has nothing left to come - the PO dialog's History tab."""
    po_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO purchase_orders (id, po_number, supplier_id, issue_date, status, "
            "company_id, created_at, updated_at) VALUES (:i, :n, :s, :d, 'closed', "
            "(SELECT company_id FROM suppliers WHERE id = :s), now(), now())"
        ),
        {"i": po_id, "n": f"{MARKER}-CPO-{uuid.uuid4().hex[:8]}", "s": str(w.supplier.id),
         "d": issued},
    )
    db.execute(
        text(
            "INSERT INTO purchase_order_lines (id, purchase_order_id, product_id, "
            "warehouse_id, qty_ordered, qty_received, line_status, unit_cost, currency, "
            "expected_date, company_id, created_at, updated_at) "
            "VALUES (:i, :po, :p, :w, :q, :q, 'closed', 335, 'CNY', :d, "
            "(SELECT company_id FROM purchase_orders WHERE id = :po), now(), now())"
        ),
        {"i": str(uuid.uuid4()), "po": po_id, "p": str(w.product(key).id), "w": str(wh.id),
         "q": qty, "d": issued},
    )
    db.flush()


# ---------------------------------------------------------------------------
# AC-B5 - the total IS the cell
# ---------------------------------------------------------------------------


def test_drill_po_total_is_the_po_cell(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=10, cbm=0.5)
    _so(db, w, "A", 100)
    wh = _warehouse(db)
    _outstanding_po(db, w, "A", wh, 30)
    _outstanding_po(db, w, "A", wh, 12)

    cell = _cell(app, w, "A")
    r = _drill(app, str(w.supplier.id), str(w.product("A").id), "po")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "po"
    assert body["total"] == cell["outstanding_po"] == 42
    assert sum(row["still_to_come"] for row in body["rows"]) == 42
    assert {row["qty_ordered"] for row in body["rows"]} == {30, 12}
    assert all(row["po_number"] for row in body["rows"])
    assert all(row["supplier_name"] for row in body["rows"])


def test_drill_incoming_pl_total_is_the_incoming_pl_cell(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=10, cbm=0.5)
    _so(db, w, "A", 100)
    ship = _packing_list(db, w, "A", 60, received=10, eta=date(2026, 7, 27))
    ship.shipping_container_number = f"{MARKER}CONT1"
    db.flush()

    cell = _cell(app, w, "A")
    r = _drill(app, str(w.supplier.id), str(w.product("A").id), "incoming_pl")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "incoming_pl"
    assert body["total"] == cell["incoming_pl"] == 50  # 60 shipped - 10 received
    row = next(x for x in body["rows"] if x["shipment_id"] == str(ship.id))
    assert row["qty"] == 50
    assert row["shipment_number"] == ship.shipment_number
    assert row["container_number"] == f"{MARKER}CONT1"
    assert row["eta"] == "2026-07-27"
    assert row["supplier_name"]
    # A packing list is reference only, so there is no landed history tab behind it.
    assert body["history"] == []


def test_drill_incoming_pl_leaves_out_shipments_that_have_arrived(scm_app):
    # Arrived stock is already in On hand; a dialog listing it would show it twice.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=10, cbm=0.5)
    _so(db, w, "A", 100)
    _packing_list(db, w, "A", 60, arrived=date(2026, 7, 1))

    cell = _cell(app, w, "A")
    r = _drill(app, str(w.supplier.id), str(w.product("A").id), "incoming_pl")

    assert r.status_code == 200, r.text
    assert r.json()["rows"] == []
    assert r.json()["total"] == cell["incoming_pl"] == 0


def test_drill_spo_total_is_the_spo_cell_and_counts_site_pools_only(scm_app):
    # The cell nets SITE POOL supply only (`_stock_context`); a project bin's SPO is shown
    # muted on the row and must not appear in the dialog that foots to the cell.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=10, cbm=0.5)
    _so(db, w, "A", 200)
    pool = _warehouse(db)
    group = _warehouse(db, segment="project")
    _incoming_spo(db, w, "A", pool, 90)
    _incoming_spo(db, w, "A", group, 70)

    cell = _cell(app, w, "A")
    r = _drill(app, str(w.supplier.id), str(w.product("A").id), "spo")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "spo"
    assert body["total"] == cell["incoming_spo"] == 90
    assert sum(row["qty"] for row in body["rows"]) == 90
    assert {row["warehouse_code"] for row in body["rows"]} == {pool.warehouse_code}
    row = body["rows"][0]
    assert row["spo_number"]
    assert row["shipment_number"]
    assert row["received"] == 0


def test_drill_spo_history_holds_the_landed_shipments_not_the_open_ones(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=10, cbm=0.5)
    _so(db, w, "A", 200)
    pool = _warehouse(db)
    _incoming_spo(db, w, "A", pool, 90)
    _landed_spo(db, w, "A", pool, 40, arrived=date.today() - timedelta(days=30))

    r = _drill(app, str(w.supplier.id), str(w.product("A").id), "spo")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 90  # the landed one is history, never open
    assert [row["qty"] for row in body["history"]] == [40]
    assert body["history"][0]["received"] == 40


def test_drill_po_history_holds_the_closed_lines_not_the_open_ones(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=10, cbm=0.5)
    _so(db, w, "A", 100)
    wh = _warehouse(db)
    _outstanding_po(db, w, "A", wh, 30)
    _closed_po(db, w, "A", wh, 100, issued=date.today() - timedelta(days=60))
    _closed_po(db, w, "A", wh, 55, issued=date.today() - timedelta(days=800))

    r = _drill(app, str(w.supplier.id), str(w.product("A").id), "po")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 30
    # Twelve months back, so the 800-day-old order is out of the window.
    assert [row["qty_ordered"] for row in body["history"]] == [100]
    assert body["history"][0]["still_to_come"] == 0
    assert body["history"][0]["unit_price"] == 335
    assert body["history"][0]["currency"] == "CNY"


def test_drill_returns_empty_rows_and_a_zero_total_for_a_product_with_nothing(scm_app):
    # An empty answer is a real zero, not a failed load - the dialog says so with a total.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=10, cbm=0.5)
    _on_hand(db, w, "A", _warehouse(db), 5)

    for kind in ("spo", "incoming_pl", "po"):
        r = _drill(app, str(w.supplier.id), str(w.product("A").id), kind)
        assert r.status_code == 200, r.text
        assert r.json() == {"kind": kind, "rows": [], "total": 0, "history": []}


# ---------------------------------------------------------------------------
# Company scope and the refusals
# ---------------------------------------------------------------------------


def test_drill_never_shows_another_companys_lines(scm_app):
    # BL-2: the drill reads raw SQL, which bypasses the ORM's company filter unless the
    # predicate is written by hand. A PO line stamped elsewhere is not this caller's.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=10, cbm=0.5)
    _so(db, w, "A", 100)
    wh = _warehouse(db)
    _outstanding_po(db, w, "A", wh, 30)

    foreign_co = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO companies (id, name, code, is_active, created_at) "
            "VALUES (:i, :n, :c, true, now())"
        ),
        {"i": foreign_co, "n": f"{MARKER} other co", "c": f"{MARKER}-{foreign_co[:8]}"},
    )
    po_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO purchase_orders (id, po_number, supplier_id, issue_date, status, "
            "company_id, created_at, updated_at) VALUES (:i, :n, :s, :d, 'active', :co, "
            "now(), now())"
        ),
        {"i": po_id, "n": f"{MARKER}-FPO-{uuid.uuid4().hex[:8]}", "s": str(w.supplier.id),
         "d": date(2026, 1, 1), "co": foreign_co},
    )
    db.execute(
        text(
            "INSERT INTO purchase_order_lines (id, purchase_order_id, product_id, "
            "warehouse_id, qty_ordered, qty_received, line_status, company_id, created_at, "
            "updated_at) VALUES (:i, :po, :p, :w, 999, 0, 'open', :co, now(), now())"
        ),
        {"i": str(uuid.uuid4()), "po": po_id, "p": str(w.product("A").id), "w": str(wh.id),
         "co": foreign_co},
    )
    db.flush()

    r = _drill(app, str(w.supplier.id), str(w.product("A").id), "po")

    assert r.status_code == 200, r.text
    assert r.json()["total"] == 30
    assert 999 not in {row["qty_ordered"] for row in r.json()["rows"]}


def test_drill_404s_on_a_supplier_this_caller_does_not_hold(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=10, cbm=0.5)

    r = _drill(app, str(uuid.uuid4()), str(w.product("A").id), "po")

    assert r.status_code == 404, r.text


def test_drill_404s_on_an_unknown_product(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=10, cbm=0.5)

    r = _drill(app, str(w.supplier.id), str(uuid.uuid4()), "po")

    assert r.status_code == 404, r.text


@pytest.mark.parametrize("bad", ["not-an-id", ""])
def test_drill_refuses_a_value_that_is_not_an_id_rather_than_500ing(scm_app, bad):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=10, cbm=0.5)

    r = _drill(app, str(w.supplier.id), bad, "po")

    assert r.status_code in (404, 422), r.text


def test_drill_422s_on_a_kind_nothing_reads(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=10, cbm=0.5)

    r = _drill(app, str(w.supplier.id), str(w.product("A").id), "on_hand")

    assert r.status_code == 422, r.text
