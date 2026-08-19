"""SCM M1 — sales-order CRUD + create-DO-from-SO (Postgres-backed, rolled back).

Anchors:
  * create/get/update/delete happy path, so_number format, resolved names,
  * write RBAC deny + payload validation,
  * create-DO stamps qty_delivered and committed drops in scm.committed_v.
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.scm.conftest import as_user, requires_pg, seed_user

pytestmark = requires_pg

CUSTOMER = "300-S229"
SKU = "WESERP10B"


def _committed_for(db, sku: str) -> float:
    val = db.execute(text(
        "SELECT COALESCE(SUM(cv.committed), 0) FROM scm.committed_v cv "
        "JOIN products p ON p.id = cv.product_id WHERE p.product_code = :s"
    ), {"s": sku}).scalar()
    return float(val or 0)


def _as(scm_app, role_slug):
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, role_slug)
    as_user(app, gcu, gcuak, uid)
    return app, db


def test_create_get_update_delete(scm_app):
    app, _ = _as(scm_app, "purchasing")
    payload = {
        "order_type": "dealer",
        "customer_code": CUSTOMER,
        "priority": "high",
        "lines": [{"sku": SKU, "qty_ordered": 12, "uom": "PCS"}],
    }
    with TestClient(app) as c:
        res = c.post("/api/v1/scm/sales-orders", json=payload)
        assert res.status_code == 201, res.text
        so = res.json()
        assert re.match(r"^SO-\d{4}/\d{2}-\d{4}$", so["so_number"]), so["so_number"]
        assert so["customer_code"] == CUSTOMER
        assert so["customer_name"]  # resolved, human-readable
        assert so["market_segment"] == "Retail"
        assert so["order_type_label"] == "Dealer"
        assert so["total_qty"] == 12
        assert so["committed_qty"] == 12
        assert so["status"] == "open"
        assert so["lines"][0]["sku"] == SKU
        assert so["lines"][0]["product_name"]
        so_id = so["id"]

        got = c.get(f"/api/v1/scm/sales-orders/{so_id}")
        assert got.status_code == 200
        assert got.json()["so_number"] == so["so_number"]

        upd = c.put(
            f"/api/v1/scm/sales-orders/{so_id}",
            json={"priority": "urgent", "lines": [{"sku": SKU, "qty_ordered": 20, "uom": "PCS"}]},
        )
        assert upd.status_code == 200, upd.text
        assert upd.json()["priority"] == "urgent"
        assert upd.json()["total_qty"] == 20

        deleted = c.delete(f"/api/v1/scm/sales-orders/{so_id}")
        assert deleted.status_code == 204
        assert c.get(f"/api/v1/scm/sales-orders/{so_id}").status_code == 404


def test_list_shape(scm_app):
    app, _ = _as(scm_app, "purchasing")
    with TestClient(app) as c:
        res = c.get("/api/v1/scm/sales-orders", params={"status": "open", "limit": 5})
    assert res.status_code == 200, res.text
    body = res.json()
    assert set(body) == {"data", "empty", "pagination"}
    assert set(body["pagination"]) == {"total", "page"}
    for so in body["data"]:
        assert so["status"] == "open"
        assert "so_number" in so


def test_create_requires_write_permission(scm_app):
    app, _ = _as(scm_app, None)  # no scm.reorder.run
    with TestClient(app) as c:
        res = c.post("/api/v1/scm/sales-orders", json={
            "order_type": "dealer",
            "customer_code": CUSTOMER,
            "priority": "normal",
            "lines": [{"sku": SKU, "qty_ordered": 1, "uom": "PCS"}],
        })
    assert res.status_code == 403, res.text


def test_create_validation_empty_lines(scm_app):
    app, _ = _as(scm_app, "purchasing")
    with TestClient(app) as c:
        res = c.post("/api/v1/scm/sales-orders", json={
            "order_type": "dealer", "customer_code": CUSTOMER, "priority": "normal", "lines": [],
        })
    assert res.status_code == 422, res.text


def test_create_unknown_sku_404(scm_app):
    app, _ = _as(scm_app, "purchasing")
    with TestClient(app) as c:
        res = c.post("/api/v1/scm/sales-orders", json={
            "order_type": "dealer", "customer_code": CUSTOMER, "priority": "normal",
            "lines": [{"sku": "NO-SUCH-SKU", "qty_ordered": 1, "uom": "PCS"}],
        })
    assert res.status_code == 404, res.text


def test_create_do_from_so_drops_committed(scm_app):
    app, db = _as(scm_app, "purchasing")
    with TestClient(app) as c:
        # committed for the SKU before we add demand
        before = _committed_for(db, SKU)
        created = c.post("/api/v1/scm/sales-orders", json={
            "order_type": "dealer", "customer_code": CUSTOMER, "priority": "normal",
            "lines": [{"sku": SKU, "qty_ordered": 7, "uom": "PCS"}],
        })
        assert created.status_code == 201, created.text
        so_id = created.json()["id"]
        with_demand = _committed_for(db, SKU)
        assert with_demand == pytest.approx(before + 7), "open SO should raise committed by 7"

        res = c.post(f"/api/v1/scm/sales-orders/{so_id}/create-do")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["do_number"], "create-DO must return a do_number"
        so = body["sales_order"]
        assert so["status"] == "fulfilled"
        assert so["committed_qty"] == 0
        assert so["lines"][0]["qty_delivered"] == so["lines"][0]["qty_ordered"] == 7

        # committed_v drops back — the delivered line no longer contributes.
        after = _committed_for(db, SKU)
        assert after == pytest.approx(before), "committed should return to baseline after DO"

        # a real DO order row was materialised with that number.
        cnt = db.execute(
            text("SELECT COUNT(*) FROM orders WHERE order_number = :n"),
            {"n": body["do_number"]},
        ).scalar()
        assert cnt == 1


def test_create_do_number_is_valid_and_unique(scm_app):
    """The create-DO happy path yields a DO number derived from the SO that is
    unique in ``orders`` and materialises exactly one row."""
    app, db = _as(scm_app, "purchasing")
    with TestClient(app) as c:
        so = c.post("/api/v1/scm/sales-orders", json={
            "order_type": "dealer", "customer_code": CUSTOMER, "priority": "normal",
            "lines": [{"sku": SKU, "qty_ordered": 3, "uom": "PCS"}],
        }).json()
        res = c.post(f"/api/v1/scm/sales-orders/{so['id']}/create-do")
        assert res.status_code == 200, res.text
        do_number = res.json()["do_number"]
    # derived from the SO number, e.g. SO-2026/07-0001 → DO-2026/07-0001
    assert do_number == f"DO-{so['so_number'].split('-', 1)[-1]}"
    cnt = db.execute(
        text("SELECT COUNT(*) FROM orders WHERE order_number = :n"), {"n": do_number}
    ).scalar()
    assert cnt == 1


def test_create_do_number_retries_on_collision(scm_app):
    """When the derived DO number is already taken, create-DO must not 500 —
    it bumps the suffix and still produces a unique number."""
    from app.models.order import Order
    from datetime import datetime

    app, db = _as(scm_app, "purchasing")
    with TestClient(app) as c:
        so = c.post("/api/v1/scm/sales-orders", json={
            "order_type": "dealer", "customer_code": CUSTOMER, "priority": "normal",
            "lines": [{"sku": SKU, "qty_ordered": 3, "uom": "PCS"}],
        }).json()
        base = f"DO-{so['so_number'].split('-', 1)[-1]}"
        # squat the derived base number so the service is forced to retry
        db.add(Order(order_number=base, order_date=datetime.utcnow(), is_cancelled=False))
        db.flush()

        res = c.post(f"/api/v1/scm/sales-orders/{so['id']}/create-do")
        assert res.status_code == 200, res.text
        do_number = res.json()["do_number"]
    assert do_number != base
    assert do_number.startswith(base)
    cnt = db.execute(
        text("SELECT COUNT(*) FROM orders WHERE order_number = :n"), {"n": do_number}
    ).scalar()
    assert cnt == 1


def test_create_do_read_only_user_denied(scm_app):
    app, _ = _as(scm_app, None)
    with TestClient(app) as c:
        res = c.post("/api/v1/scm/sales-orders/does-not-matter/create-do")
    assert res.status_code == 403, res.text


# --------------------------------------------------------------------------- #
# absorbed history is its own source, on the list and on the detail
# --------------------------------------------------------------------------- #

def test_absorbed_history_is_labelled_history_and_never_manual(scm_app):
    """`Manual` is the one source label that must never be wrong.

    It claims a person keyed the order. 11,006 of the sales orders in the book were read off
    a six-year AutoCount export by `so_history_service`, and a source added to the label
    function but forgotten in the filter map falls silently into Manual - so both halves are
    asserted here, on one row.
    """
    import uuid

    from app.models.order import SalesOrder
    from app.services.scm.sales_order_service import _SOURCE_SYSTEMS, _source_label

    app, db = _as(scm_app, "purchasing")
    number = f"ZZTSOH{uuid.uuid4().hex[:8]}".upper()
    db.add(SalesOrder(id=str(uuid.uuid4()), so_number=number, status="closed",
                      source_system="scm_so_history"))
    db.flush()

    assert _source_label("scm_so_history") == "history"
    # The filter map, so `?source=history` selects it rather than returning nothing.
    assert "scm_so_history" in _SOURCE_SYSTEMS["history"]

    row = db.query(SalesOrder).filter(SalesOrder.so_number == number).one()
    from app.services.scm.sales_order_service import SalesOrderService

    assert SalesOrderService(db).serialize(row)["source"] == "history"


def test_the_detail_payload_carries_what_the_detail_screen_reads(scm_app):
    """Per-line location, status and date, plus the two header counts.

    The detail page states them per LINE because one order routinely ships from two locations
    on two dates; folding either onto the header would state something the order never said.
    Asserted on the payload rather than in the component, because a component test would pass
    against a serializer that had quietly stopped sending them.
    """
    app, db = _as(scm_app, "purchasing")
    payload = {
        "order_type": "dealer",
        "customer_code": CUSTOMER,
        "priority": "normal",
        "lines": [{"sku": SKU, "qty_ordered": 5, "uom": "PCS"}],
    }
    created = TestClient(app).post("/api/v1/scm/sales-orders", json=payload)
    assert created.status_code == 201, created.text
    so_id = created.json()["id"]

    got = TestClient(app).get(f"/api/v1/scm/sales-orders/{so_id}")

    assert got.status_code == 200, got.text
    body = got.json()
    assert body["line_count"] == 1
    assert body["open_line_count"] == 1
    line = body["lines"][0]
    for field in ("warehouse_code", "line_status", "required_date"):
        assert field in line, f"the detail screen reads {field} and the payload omits it"
    assert line["line_status"] == "open"


def test_line_warehouse_code_reflects_the_assigned_warehouse(scm_app):
    """A line carrying `warehouse_id` must return that warehouse's CODE, not a blank, and
    OPEN lines must list before CLOSED ones regardless of insertion order or date.

    The detail screen's Location column reads `warehouse_code` straight off this payload, so
    a serializer that dropped the join or a query that forgot to eager-load it would render
    "-" against a line that IS assigned a location - indistinguishable from a line that
    genuinely has none. Covers both the raw serializer and the route it backs, plus the
    open-first ordering `serialize()` now owns.
    """
    import uuid
    from datetime import date

    from app.models.inventory import Warehouse
    from app.models.order import SalesOrder as SalesOrderModel
    from app.models.order import SalesOrderLine
    from app.models.product import Product
    from app.services.scm.sales_order_service import SalesOrderService

    app, db = _as(scm_app, "purchasing")
    product = db.query(Product).filter(Product.product_code == SKU).one()
    wh = Warehouse(
        id=str(uuid.uuid4()),
        warehouse_code=f"ZZTSOWH{uuid.uuid4().hex[:6]}".upper(),
        warehouse_name="SCM test SO line warehouse",
        is_active=True,
    )
    db.add(wh)
    db.flush()

    order = SalesOrderModel(
        id=str(uuid.uuid4()), so_number=f"ZZTSO{uuid.uuid4().hex[:8]}".upper(), status="open",
    )
    db.add(order)
    db.flush()
    open_line = SalesOrderLine(
        id=str(uuid.uuid4()), sales_order_id=order.id, product_id=product.id,
        warehouse_id=wh.id, qty_ordered=10, qty_delivered=0, line_status="open",
    )
    # Inserted AFTER the open line and with an earlier required_date, so a naive
    # insertion-order or date-ascending read would place it first. It must not: closed
    # lines sort after every open one regardless of date.
    closed_line = SalesOrderLine(
        id=str(uuid.uuid4()), sales_order_id=order.id, product_id=product.id,
        warehouse_id=None, qty_ordered=5, qty_delivered=5, line_status="closed",
        required_date=date(2020, 1, 1),
    )
    db.add_all([open_line, closed_line])
    db.flush()

    payload = SalesOrderService(db).serialize(order)
    assert payload["lines"][0]["warehouse_code"] == wh.warehouse_code
    assert wh.warehouse_code in payload["stock_locations"]

    # Open first, closed after - the ordering `serialize()` now owns so every consumer
    # (this detail read, the list, create/update responses) agrees on it.
    line_ids = [ln["id"] for ln in payload["lines"]]
    assert line_ids == [open_line.id, closed_line.id]
    assert payload["lines"][0]["line_status"] == "open"
    assert payload["lines"][1]["line_status"] == "closed"

    got = TestClient(app).get(f"/api/v1/scm/sales-orders/{order.id}")
    assert got.status_code == 200, got.text
    got_lines = got.json()["lines"]
    assert got_lines[0]["warehouse_code"] == wh.warehouse_code
    assert [ln["id"] for ln in got_lines] == [open_line.id, closed_line.id]
