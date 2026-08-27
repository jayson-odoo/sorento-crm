"""S13 - the container request, the demand-first stage in front of the Loading Plan's CBM fit.

`PLAN-scm-loading-plan-demand-first.md` section 6 is this file's contract. `build` is a pure
read over the supplier's current stock list crossed with the outstanding sales-order book,
ranked by the ACTIVE Fulfilment Priority policy - the same call the fulfilment board makes
(AC-H5), so this suite seeds its own `scm.priority_policy` row rather than assuming one is
active, exactly like `test_priority_demand_rows.py`'s policy tests. `send` is a thin wrapper
over `supplier_notice_service.request_and_notify`, the S8 machinery under a new
`notice_type`, so its render/storage side effects are stubbed the same way
`test_supplier_notice.py` stubs them - this suite is about the request, not WeasyPrint.

Every test seeds its own chain under a marker-prefixed tag (CI's database is empty).
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.inventory import Stock, Warehouse
from app.models.job import ImportJob, JobStatus
from app.models.order import SalesOrder, SalesOrderLine
from app.models.procurement import (
    InboundShipment,
    PurchaseOrder,
    PurchaseOrderLine,
    SPOAllocation,
)
from app.models.scm import PriorityPolicy
from app.models.supplier_notice import SupplierNoticeLine
from app.services.scm import supplier_notice_service
from tests.scm.conftest import as_user, requires_pg, seed_user
from tests.scm.test_loading_plan import World
from tests.scm.test_outstanding_import_routes import as_company_user

pytestmark = requires_pg

MARKER = "ZZCR"

BUILD_URL = "/api/v1/scm/container-requests/build"
SEND_URL = "/api/v1/scm/container-requests"


@pytest.fixture(autouse=True)
def _no_pdf_no_storage(monkeypatch):
    """This suite is about the notice record, not WeasyPrint - same stub as S8's own suite."""
    monkeypatch.setattr(
        supplier_notice_service, "render_document", lambda html: b"%PDF-1.4 stub"
    )
    monkeypatch.setattr(
        supplier_notice_service, "_store", lambda data, filename: ("s3", f"exports/test/{filename}")
    )


def _policy(db, factors: dict, class_weights: dict | None = None) -> str:
    """A policy owned by this test. Deactivates the incumbent rather than deleting it -
    same pattern as `test_priority_demand_rows.py`'s `_policy`."""
    db.query(PriorityPolicy).filter(PriorityPolicy.is_active.is_(True)).update(
        {"is_active": False}, synchronize_session=False
    )
    row = PriorityPolicy(
        id=str(uuid.uuid4()),
        name=f"{MARKER}-policy-{uuid.uuid4().hex[:6]}",
        is_active=True,
        factors=factors,
        demand_class_weights=class_weights or {},
    )
    db.add(row)
    db.flush()
    return str(row.id)


def _so(
    db,
    w: World,
    key: str,
    qty: float,
    *,
    demand_class: str | None = "retail",
    demand_origin: str | None = None,
    required_date: date | None = None,
    order_date: date | None = None,
    delivered: float = 0,
    status: str = "open",
    line_status: str = "open",
    purchasing_status: str = "not_reviewed",
) -> SalesOrder:
    # RETAIL by default, because the sales-order BOOK speaks for the retail channel and
    # for nothing else (`is_plan_demand_order()`, P3 of PLAN-scm-purchasing-uat-journey.md).
    # A project-class line is not purchasing demand as a book line at all - it becomes
    # demand when CS raises an Order Inquiry ORDER row for it, which this screen does not
    # read yet (F1 of PLAN-scm-fulfilment-feedback.md, ruling R1). So `demand_class` is
    # stated as "project" below only where the point is that the row is EXCLUDED, and
    # `demand_origin` no longer decides anything: the retired sheet leg is what read it.
    so = SalesOrder(
        id=str(uuid.uuid4()),
        so_number=f"{MARKER}-SO-{uuid.uuid4().hex[:8]}",
        status=status,
        demand_class=demand_class,
        demand_origin=demand_origin,
        order_date=order_date or date(2026, 1, 1),
    )
    db.add(so)
    db.flush()
    db.add(
        SalesOrderLine(
            id=str(uuid.uuid4()),
            sales_order_id=so.id,
            product_id=w.product(key).id,
            qty_ordered=qty,
            qty_delivered=delivered,
            line_status=line_status,
            purchasing_status=purchasing_status,
            required_date=required_date,
        )
    )
    db.flush()
    return so


def _row(rows: list[dict], key: str, w: World) -> dict:
    code = w.product(key).product_code
    return next(r for r in rows if r["item_code"] == code)


def _warehouse(db) -> Warehouse:
    wh = Warehouse(
        id=str(uuid.uuid4()),
        warehouse_code=f"{MARKER}-WH-{uuid.uuid4().hex[:8]}",
        warehouse_name=f"{MARKER} warehouse",
        is_active=True,
    )
    db.add(wh)
    db.flush()
    return wh


def _on_hand(db, w: World, key: str, wh: Warehouse, qty: float) -> None:
    db.add(
        Stock(
            id=str(uuid.uuid4()),
            product_id=w.product(key).id,
            warehouse_id=wh.id,
            quantity_on_hand=qty,
        )
    )
    db.flush()


def _outstanding_po(db, w: World, key: str, wh: Warehouse, qty: float) -> None:
    po = PurchaseOrder(
        id=str(uuid.uuid4()),
        po_number=f"{MARKER}-OPO-{uuid.uuid4().hex[:8]}",
        supplier_id=w.supplier.id,
        issue_date=date(2026, 1, 1),
        status="active",
    )
    db.add(po)
    db.flush()
    db.add(
        PurchaseOrderLine(
            id=str(uuid.uuid4()),
            purchase_order_id=po.id,
            product_id=w.product(key).id,
            warehouse_id=wh.id,
            qty_ordered=qty,
            qty_received=0,
            line_status="open",
        )
    )
    db.flush()


def _incoming_spo(db, w: World, key: str, wh: Warehouse, qty: float) -> None:
    ship = InboundShipment(
        id=str(uuid.uuid4()),
        shipment_number=f"{MARKER}-SH-{uuid.uuid4().hex[:8]}",
        supplier_id=w.supplier.id,
        shipment_date=date(2026, 1, 1),
        shipment_status="in_transit",
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
            quantity_received=0,
        )
    )
    db.flush()


def _import_job(db, company_id: str, job_type: str) -> None:
    db.add(
        ImportJob(
            id=str(uuid.uuid4()),
            job_id=f"{MARKER}-JOB-{uuid.uuid4().hex[:8]}",
            job_type=job_type,
            status=JobStatus.FINISHED.value,
            user_id=str(uuid.uuid4()),
            company_id=company_id,
        )
    )
    db.flush()


def _foreign_product(db) -> str:
    """A product stamped with a DIFFERENT company - never the caller's own (BL-2)."""
    coid = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO companies (id, name, code, is_active, created_at) "
            "VALUES (:i, :n, :c, true, now())"
        ),
        {"i": coid, "n": f"{MARKER} product co", "c": f"{MARKER}-PCO-{coid[:8]}"},
    )
    cat_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO product_categories (id, category_code, category_name, "
            "created_at, updated_at) VALUES (:i, :c, :n, now(), now())"
        ),
        {"i": cat_id, "c": f"{MARKER}-FPC-{cat_id[:8]}", "n": f"{MARKER} foreign category"},
    )
    uom_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO units_of_measure (id, uom_code, uom_name, created_at, updated_at) "
            "VALUES (:i, :c, :n, now(), now())"
        ),
        {"i": uom_id, "c": f"{MARKER}-FU-{uom_id[:8]}"[:20], "n": "pcs"},
    )
    pid = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO products (id, product_code, product_name, category_id, "
            "base_uom_id, list_price, is_active, is_discontinued, company_id, "
            "created_at, updated_at) "
            "VALUES (:i, :c, :n, :cat, :uom, 0, true, false, :co, now(), now())"
        ),
        {"i": pid, "c": f"{MARKER}-FP-{pid[:8]}", "n": f"{MARKER} Foreign Product",
         "cat": cat_id, "uom": uom_id, "co": coid},
    )
    db.flush()
    return pid


def _foreign_supplier(db) -> str:
    """A supplier stamped with a DIFFERENT company - never the caller's own."""
    coid = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO companies (id, name, code, is_active, created_at) "
            "VALUES (:i, :n, :c, true, now())"
        ),
        {"i": coid, "n": f"{MARKER} other co", "c": f"{MARKER}-CO-{coid[:8]}"},
    )
    sid = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO suppliers (id, supplier_code, supplier_name, is_active, "
            "company_id, created_at, updated_at) "
            "VALUES (:i, :c, :n, true, :co, now(), now())"
        ),
        {"i": sid, "c": f"{MARKER}-FS-{sid[:8]}", "n": f"{MARKER} Foreign Supplier", "co": coid},
    )
    db.flush()
    return sid


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #


def test_build_scope_is_the_whole_stock_list_ranked_rows_then_no_demand_rows(scm_app):
    # CHANGE 1: row scope is now the WHOLE stock list - a product on the list with no
    # open need still gets a row (has_demand false, rank null), sorted after the ranked
    # demand rows. A product with need but off the list is still absent - the stock list
    # is what makes a product a candidate at all.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=5, cbm=0.5)  # on the list, has open need
    w.stock("B", packed=5, cbm=0.5)  # on the list, no open need
    _so(db, w, "A", 20)
    _so(db, w, "C", 30)  # need exists, but not on the list

    r = TestClient(app).post(BUILD_URL, json={"supplier_id": str(w.supplier.id)})

    assert r.status_code == 200, r.text
    body = r.json()
    codes = {row["item_code"] for row in body["rows"]}
    assert codes == {w.product("A").product_code, w.product("B").product_code}
    row_a = _row(body["rows"], "A", w)
    row_b = _row(body["rows"], "B", w)
    assert row_a["has_demand"] is True
    assert row_a["rank"] == 1
    assert row_b["has_demand"] is False
    assert row_b["rank"] is None
    # Ranked rows keep total order first; the no-demand row sorts after them.
    assert [r["item_code"] for r in body["rows"]] == [
        row_a["item_code"],
        row_b["item_code"],
    ]


def test_build_no_demand_rows_with_stock_but_zero_quantity_are_left_out_entirely(scm_app):
    # The module docstring's own carve-out: a stock-list row with neither packed nor
    # unfinished quantity AND no open need names nothing worth asking about, so it never
    # appears at all (not even as a no-demand row).
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=5, cbm=0.5)  # has open need
    w.stock("B", packed=0, unfinished=0, cbm=0.5)  # no need, no quantity either

    _so(db, w, "A", 20)

    r = TestClient(app).post(BUILD_URL, json={"supplier_id": str(w.supplier.id)})

    assert r.status_code == 200, r.text
    codes = {row["item_code"] for row in r.json()["rows"]}
    assert codes == {w.product("A").product_code}


def test_build_suggested_qty_nets_stock_and_incoming_spo_but_not_outstanding_po(scm_app):
    # CHANGE 4 (captain decision), amended 20 Aug follow-up (CWCY604 worked example):
    # suggested_qty = max(open_so_need - on_hand - incoming_spo, 0). outstanding_po is
    # deliberately NOT subtracted - a PO placed but not yet allocated is not supply this
    # container can count on (often the very demand this request is asking the supplier to
    # pack), whereas an SPO allocation is real incoming stock on the water. outstanding_po
    # still travels on the row as context. The gross figure stays on the row as open_so_need
    # so the arithmetic is visible.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=10, cbm=0.5)
    _so(db, w, "A", 120)
    wh = _warehouse(db)
    _on_hand(db, w, "A", wh, 20)
    _outstanding_po(db, w, "A", wh, 30)
    _incoming_spo(db, w, "A", wh, 15)

    r = TestClient(app).post(BUILD_URL, json={"supplier_id": str(w.supplier.id)})

    assert r.status_code == 200, r.text
    row = _row(r.json()["rows"], "A", w)
    assert row["open_so_need"] == 120
    assert row["on_hand"] == 20
    assert row["outstanding_po"] == 30  # shown, not deducted
    assert row["incoming_spo"] == 15
    assert row["suggested_qty"] == 85  # 120 - 20 - 15 (outstanding_po not subtracted)
    assert row["qty_packed"] == 10


def test_build_suggested_qty_floors_at_zero_when_stock_and_incoming_cover_the_need(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=10, cbm=0.5)
    _so(db, w, "A", 50)
    wh = _warehouse(db)
    _on_hand(db, w, "A", wh, 200)

    r = TestClient(app).post(BUILD_URL, json={"supplier_id": str(w.supplier.id)})

    assert r.status_code == 200, r.text
    row = _row(r.json()["rows"], "A", w)
    assert row["open_so_need"] == 50
    assert row["on_hand"] == 200
    assert row["suggested_qty"] == 0


def test_build_returns_a_sources_block_naming_the_latest_ingest_per_family(scm_app):
    app, db, gcu, gcuk = scm_app
    scope = as_company_user(app, db, gcu, gcuk)
    company_id = next(iter(scope))
    w = World(db)
    w.stock("A", packed=1, cbm=0.5)
    _so(db, w, "A", 10)
    _import_job(db, company_id, "outstanding_so_import")

    r = TestClient(app).post(BUILD_URL, json={"supplier_id": str(w.supplier.id)})

    assert r.status_code == 200, r.text
    body = r.json()
    sources = body["sources"]
    assert set(sources) == {
        "so_book_as_of",
        "po_book_as_of",
        "spo_as_of",
        "stock_list_as_of",
    }
    assert sources["so_book_as_of"] is not None
    assert sources["stock_list_as_of"] == body["stock_list_as_of"]
    # Nothing seeded for these two families - honest absence, not a stale guess.
    assert sources["po_book_as_of"] is None
    assert sources["spo_as_of"] is None


def test_build_include_lines_returns_flat_lines_summing_to_open_so_need(scm_app):
    # CHANGE 2 + the invariant `build`'s docstring states: sum(lines.qty per product) ==
    # open_so_need (the GROSS need, not the netted suggestion).
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=1, cbm=0.5)
    so1 = _so(db, w, "A", 20)
    so2 = _so(db, w, "A", 15)
    # A project-class book line is not demand here at all, so it contributes neither a
    # line nor a unit to `open_so_need` - the invariant holds over what the screen counts.
    _so(db, w, "A", 99, demand_class="project")

    r = TestClient(app).post(
        BUILD_URL,
        params={"include_lines": "true"},
        json={"supplier_id": str(w.supplier.id)},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    row = _row(body["rows"], "A", w)
    lines = [ln for ln in body["lines"] if ln["product_id"] == row["product_id"]]
    assert len(lines) == 2
    assert sum(ln["qty"] for ln in lines) == row["open_so_need"] == 35
    assert {ln["so_number"] for ln in lines} == {so1.so_number, so2.so_number}


def test_build_without_include_lines_omits_the_lines_key(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=1, cbm=0.5)
    _so(db, w, "A", 10)

    r = TestClient(app).post(BUILD_URL, json={"supplier_id": str(w.supplier.id)})

    assert r.status_code == 200, r.text
    assert "lines" not in r.json()


def test_build_with_a_foreign_supplier_is_a_404(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    foreign_id = _foreign_supplier(db)

    r = TestClient(app).post(BUILD_URL, json={"supplier_id": foreign_id})

    assert r.status_code == 404, r.text


def test_build_with_a_malformed_supplier_id_is_a_404_not_a_500(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)

    r = TestClient(app).post(BUILD_URL, json={"supplier_id": "not-a-uuid"})

    assert r.status_code == 404, r.text


def test_build_splits_project_and_retail_qty(scm_app):
    """The split columns are read off the BOOK, which speaks for retail alone (P3).

    A project-class book line contributes nothing - not to `project_qty`, not to
    `open_so_need`, not to `so_count` - because project demand has one source and it is
    the un-linked Order Inquiry row, which this screen does not read yet (R1 of
    PLAN-scm-fulfilment-feedback.md; F1 restores the Project column from that source).
    A row with no class stated is the book-direct channel and still counts.
    """
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=1, cbm=0.5)
    _so(db, w, "A", 80, demand_class="project")
    _so(db, w, "A", 40, demand_class="retail")
    _so(db, w, "A", 20, demand_class=None)

    r = TestClient(app).post(BUILD_URL, json={"supplier_id": str(w.supplier.id)})

    assert r.status_code == 200, r.text
    row = _row(r.json()["rows"], "A", w)
    assert row["suggested_qty"] == 60
    assert row["project_qty"] == 0
    assert row["retail_qty"] == 40
    assert row["unclassified_qty"] == 20
    assert row["so_count"] == 2


def test_build_leaves_a_project_class_book_row_unranked_and_ranks_the_retail_one(scm_app):
    """The ACTIVE policy still ranks (AC-H5), but a project book line is not demand.

    This used to assert that the project row OUTRANKED the retail one at equal dates,
    under a policy whose dominant factor is `demand_class`. P3 removed the ground it
    stood on: the book speaks for retail alone, so the project-class row reaches this
    screen with no demand at all - it is a stock-list row with `has_demand` false and no
    rank, and the retail row is the only ranked one. When F1 reads the Project column off
    the un-linked Order Inquiry rows (R1), the class weighting comes back with it.
    """
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    _policy(
        db,
        {"demand_class": 3.0, "need_by_date": 0.0, "document_age": 0.0, "po_document_sequence": 0.0},
        {"project": 1.0, "retail": 0.4},
    )
    w.stock("A", packed=1, cbm=0.5)
    w.stock("B", packed=1, cbm=0.5)
    same_date = date(2026, 9, 1)
    _so(db, w, "A", 10, demand_class="retail", required_date=same_date, order_date=same_date)
    _so(db, w, "B", 10, demand_class="project", required_date=same_date, order_date=same_date)

    r = TestClient(app).post(BUILD_URL, json={"supplier_id": str(w.supplier.id)})

    assert r.status_code == 200, r.text
    rows = r.json()["rows"]
    project_row = _row(rows, "B", w)
    retail_row = _row(rows, "A", w)
    assert project_row["has_demand"] is False
    assert project_row["rank"] is None
    assert project_row["open_so_need"] == 0
    assert retail_row["has_demand"] is True
    assert retail_row["rank"] == 1


def test_build_a_sooner_required_date_outranks_within_the_same_class(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    _policy(
        db,
        {"need_by_date": 1.0, "demand_class": 0.0, "document_age": 0.0, "po_document_sequence": 0.0},
        {"retail": 1.0},
    )
    w.stock("A", packed=1, cbm=0.5)
    w.stock("B", packed=1, cbm=0.5)
    _so(db, w, "A", 10, required_date=date(2026, 9, 4))
    _so(db, w, "B", 10, required_date=date(2027, 5, 15))

    r = TestClient(app).post(BUILD_URL, json={"supplier_id": str(w.supplier.id)})

    assert r.status_code == 200, r.text
    rows = r.json()["rows"]
    soon = _row(rows, "A", w)
    late = _row(rows, "B", w)
    assert soon["rank"] < late["rank"]
    assert soon["rank_score"] > late["rank_score"]


def test_build_with_no_stock_list_reads_as_an_empty_result_not_an_error(scm_app):
    # The route docstring's own decision: empty-with-reason, not a 409. `stock_list_as_of`
    # null is the FE's cue for the "upload a stock list first" empty state.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    _so(db, w, "A", 10)  # demand exists, but no stock list at all

    r = TestClient(app).post(BUILD_URL, json={"supplier_id": str(w.supplier.id)})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rows"] == []
    assert body["stock_list_as_of"] is None


def test_build_requires_the_read_permission(scm_app):
    app, db, gcu, gcuk = scm_app
    as_user(app, gcu, gcuk, seed_user(db, None))

    r = TestClient(app).post(BUILD_URL, json={"supplier_id": str(uuid.uuid4())})

    assert r.status_code == 403, r.text


# --------------------------------------------------------------------------- #
# send
# --------------------------------------------------------------------------- #


def test_send_creates_a_notice_with_a_copied_lines_snapshot_and_a_document(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.supplier.email = f"{MARKER}@example.test"
    db.flush()
    product = w.product("A")

    r = TestClient(app).post(
        SEND_URL,
        json={
            "supplier_id": str(w.supplier.id),
            "lines": [{"product_id": str(product.id), "qty": 42}],
        },
    )

    assert r.status_code == 201, r.text
    body = r.json()
    by_channel = {n["channel"]: n for n in body["notices"]}
    assert set(by_channel) == {"email", "chat"}
    email = by_channel["email"]
    assert email["status"] == "sent"
    assert email["has_document"] is True
    assert email["document_filename"].endswith(".pdf")

    lines = (
        db.query(SupplierNoticeLine)
        .filter(SupplierNoticeLine.notice_id == email["id"])
        .all()
    )
    assert len(lines) == 1
    assert lines[0].item_code == product.product_code
    assert lines[0].product_name == product.product_name
    assert float(lines[0].qty) == 42
    assert lines[0].kind == "pack"


def test_send_without_a_supplier_email_is_skipped_not_a_failure(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    # No email set on the supplier - the default.
    product = w.product("A")

    r = TestClient(app).post(
        SEND_URL,
        json={
            "supplier_id": str(w.supplier.id),
            "lines": [{"product_id": str(product.id), "qty": 5}],
        },
    )

    assert r.status_code == 201, r.text
    email = next(n for n in r.json()["notices"] if n["channel"] == "email")
    assert email["status"] == "skipped"
    assert "email address" in (email["status_reason"] or "").lower()


def test_send_to_an_unknown_supplier_is_a_404(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)

    r = TestClient(app).post(
        SEND_URL,
        json={
            "supplier_id": str(uuid.uuid4()),
            "lines": [{"product_id": str(uuid.uuid4()), "qty": 1}],
        },
    )

    assert r.status_code == 404, r.text


def test_send_with_a_foreign_supplier_is_a_404(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    foreign_id = _foreign_supplier(db)

    r = TestClient(app).post(
        SEND_URL,
        json={"supplier_id": foreign_id, "lines": [{"product_id": str(uuid.uuid4()), "qty": 1}]},
    )

    assert r.status_code == 404, r.text


def test_send_with_a_malformed_supplier_id_is_a_404_not_a_500(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)

    r = TestClient(app).post(
        SEND_URL,
        json={"supplier_id": "not-a-uuid", "lines": [{"product_id": str(uuid.uuid4()), "qty": 1}]},
    )

    assert r.status_code == 404, r.text


def test_send_with_unknown_or_malformed_product_ids_is_a_422_naming_them(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    unknown_id = str(uuid.uuid4())

    r = TestClient(app).post(
        SEND_URL,
        json={
            "supplier_id": str(w.supplier.id),
            "lines": [
                {"product_id": "not-a-uuid", "qty": 1},
                {"product_id": unknown_id, "qty": 1},
            ],
        },
    )

    assert r.status_code == 422, r.text
    body = r.json()
    assert "not-a-uuid" in body["message"]
    assert unknown_id in body["message"]


def test_send_with_a_foreign_product_id_is_a_422_naming_it(scm_app):
    # BL-2 (SECURITY): a well-formed id naming ANOTHER company's product must not resolve -
    # the catalogue lookup is company-scoped, so a foreign id lands in the same "unknown"
    # set as a made-up one, and the company's product_code/product_name never reach
    # `supplier_notice_lines` or the emailed PDF.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    foreign_pid = _foreign_product(db)

    r = TestClient(app).post(
        SEND_URL,
        json={
            "supplier_id": str(w.supplier.id),
            "lines": [{"product_id": foreign_pid, "qty": 1}],
        },
    )

    assert r.status_code == 422, r.text
    body = r.json()
    assert foreign_pid in body["message"]

    lines = (
        db.query(SupplierNoticeLine)
        .filter(SupplierNoticeLine.product_id == foreign_pid)
        .all()
    )
    assert lines == [], "the foreign product must never be copied into a notice line"


def test_send_with_no_lines_is_a_422(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)

    r = TestClient(app).post(
        SEND_URL, json={"supplier_id": str(w.supplier.id), "lines": []}
    )

    assert r.status_code == 422, r.text


def test_send_with_a_non_positive_qty_is_a_422(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    product = w.product("A")

    r = TestClient(app).post(
        SEND_URL,
        json={
            "supplier_id": str(w.supplier.id),
            "lines": [{"product_id": str(product.id), "qty": 0}],
        },
    )

    assert r.status_code == 422, r.text


# --------------------------------------------------------------------------- #
# N-3: GET /supplier-notices?supplier_id= with a malformed id
# --------------------------------------------------------------------------- #
#
# No dedicated supplier-notice ROUTE test file is in this pass's edit scope
# (`tests/scm/test_supplier_notice.py` exists but is owned elsewhere), so this is a
# service-level test of `list_for_supplier` directly - cheap, and it exercises the exact
# function `GET /api/v1/scm/supplier-notices` calls.


def test_list_for_supplier_with_a_malformed_id_is_an_empty_list_not_a_500(scm_app):
    _, db, _, _ = scm_app

    out = supplier_notice_service.list_for_supplier(db, "not-a-uuid")

    assert out == []


def test_send_requires_the_write_permission(scm_app):
    app, db, gcu, gcuk = scm_app
    as_user(app, gcu, gcuk, seed_user(db, None))

    r = TestClient(app).post(
        SEND_URL,
        json={
            "supplier_id": str(uuid.uuid4()),
            "lines": [{"product_id": str(uuid.uuid4()), "qty": 1}],
        },
    )

    assert r.status_code == 403, r.text
