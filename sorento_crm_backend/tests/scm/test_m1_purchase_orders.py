"""SCM M1 — purchase-order read-only list (Postgres-backed, rolled back)."""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from tests.scm.conftest import (
    _REF_PRODUCT_CODE,
    _REF_WAREHOUSE_CODE,
    as_user,
    requires_pg,
    seed_user,
)

pytestmark = requires_pg


def _as(scm_app, role_slug):
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, role_slug)
    as_user(app, gcu, gcuak, uid)
    return app, db


def _seed_po(db) -> str:
    """A purchase order this test owns, with known figures. Returns its number.

    It used to read the shipped demo PO off page 1 of the list. That is two environment
    assumptions in one line - that the row exists, and that nothing newer has pushed it off
    the page - and both broke: CI has no demo data at all, and importing a year of purchase
    history filled the first fifty rows with orders created today.
    """
    from app.models.inventory import Warehouse
    from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
    from app.models.product import Product

    marker = f"ZZTM1PO-{uuid.uuid4().hex[:8]}"
    product = db.query(Product).filter(Product.product_code == _REF_PRODUCT_CODE).one()
    warehouse = (
        db.query(Warehouse).filter(Warehouse.warehouse_code == _REF_WAREHOUSE_CODE).one()
    )
    supplier = Supplier(
        id=str(uuid.uuid4()), supplier_code=marker[:30], supplier_name=f"{marker} supplier",
    )
    db.add(supplier)
    db.flush()
    po = PurchaseOrder(
        id=str(uuid.uuid4()), po_number=marker, supplier_id=str(supplier.id),
        status="active", issue_date=date(2026, 7, 16), expected_date=date(2026, 8, 4),
    )
    db.add(po)
    db.flush()
    db.add(PurchaseOrderLine(
        id=str(uuid.uuid4()), purchase_order_id=str(po.id), product_id=str(product.id),
        warehouse_id=str(warehouse.id), qty_ordered=500, qty_received=0,
        line_status="open", expected_date=date(2026, 8, 4),
    ))
    db.flush()
    return marker


def test_list_shape_and_lines(scm_app):
    app, db = _as(scm_app, "purchasing")
    number = _seed_po(db)

    with TestClient(app) as c:
        res = c.get("/api/v1/scm/purchase-orders", params={"query": number, "limit": 50})
    assert res.status_code == 200, res.text
    body = res.json()
    assert {"data", "empty", "pagination"} <= set(body)
    # Nobody asked for a product, so there is nothing to say about one price.
    assert body.get("product_cost") is None
    assert body["pagination"]["total"] >= 1

    po = next(p for p in body["data"] if p["po_number"] == number)
    assert po["status"] == "active"
    assert po["supplier_code"]
    assert po["supplier_name"]
    assert po["expected_date"] == "2026-08-04"
    assert po["line_count"] == 1
    assert po["total_qty"] == 500
    # Open, so what the order says and what is still coming agree. They part company on a
    # received or historical order, which is why they are two figures.
    assert po["open_qty"] == 500
    assert po["open_line_count"] == 1
    assert po["lines"][0]["sku"]
    assert po["lines"][0]["qty_ordered"] == 500


def test_status_filter(scm_app):
    app, _ = _as(scm_app, "purchasing")
    with TestClient(app) as c:
        res = c.get("/api/v1/scm/purchase-orders", params={"status": "active"})
    assert res.status_code == 200, res.text
    for po in res.json()["data"]:
        assert po["status"] == "active"


def test_no_write_route_exists(scm_app):
    # M1 PO surface is read-only — POST must not be routed (405).
    app, _ = _as(scm_app, "purchasing")
    with TestClient(app) as c:
        res = c.post("/api/v1/scm/purchase-orders", json={})
    assert res.status_code == 405, res.text


def test_rbac_denial(scm_app):
    app, _ = _as(scm_app, None)
    with TestClient(app) as c:
        res = c.get("/api/v1/scm/purchase-orders")
    assert res.status_code == 403, res.text


# ------------------------------------------------------- outstanding filter (20 Aug)
# "how do i know the open PO / outstanding PO" (the captain). `outstanding=true` mirrors
# `scm.po_ordered_v`: status in active/received/partial/closed AND an EXISTS open line
# with qty_ordered > qty_received. `outstanding=false` is the exact complement - nothing
# is dropped, every seeded PO lands in one bucket or the other.


def _seed_full_po(
    db,
    marker: str,
    suffix: str,
    *,
    status: str,
    issue_date=None,
    expected_date=None,
    line_qty_ordered=None,
    line_qty_received="0",
    line_status="open",
) -> str:
    """A purchase order this test owns end to end - header status, and (optionally) one
    line whose own qty/status decides whether it is still "open" by the EXISTS predicate.
    Returns the PO number so the test can identify it back out of the response.
    """
    from app.models.inventory import Warehouse
    from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
    from app.models.product import Product

    product = db.query(Product).filter(Product.product_code == _REF_PRODUCT_CODE).one()
    warehouse = db.query(Warehouse).filter(Warehouse.warehouse_code == _REF_WAREHOUSE_CODE).one()
    number = f"{marker}-{suffix}"
    supplier = Supplier(
        id=str(uuid.uuid4()), supplier_code=number[:30], supplier_name=f"{number} supplier",
    )
    db.add(supplier)
    db.flush()
    po = PurchaseOrder(
        id=str(uuid.uuid4()), po_number=number, supplier_id=str(supplier.id), status=status,
        issue_date=issue_date, expected_date=expected_date,
    )
    db.add(po)
    db.flush()
    if line_qty_ordered is not None:
        db.add(PurchaseOrderLine(
            id=str(uuid.uuid4()), purchase_order_id=str(po.id), product_id=str(product.id),
            warehouse_id=str(warehouse.id), qty_ordered=line_qty_ordered,
            qty_received=line_qty_received, line_status=line_status,
            expected_date=expected_date,
        ))
        db.flush()
    return number


def test_outstanding_true_returns_exactly_the_on_order_purchase_orders(scm_app):
    """Five statuses, one predicate. A draft never counts regardless of its lines; a
    cancelled PO never counts; an active PO fully received (no line left open) does not
    count even though its status is "on order"; but a CLOSED header carrying an open line
    still counts - the header status alone is not the whole story, matching the docstring
    on `_is_on_order` / `scm.po_ordered_v`."""
    app, db = _as(scm_app, "purchasing")
    marker = f"ZZTOUT-{uuid.uuid4().hex[:8]}"

    draft = _seed_full_po(
        db, marker, "draft", status="draft", line_qty_ordered=10, line_qty_received=0,
    )
    active_open = _seed_full_po(
        db, marker, "active-open", status="active", line_qty_ordered=10, line_qty_received=0,
    )
    active_full = _seed_full_po(
        db, marker, "active-full", status="active", line_qty_ordered=10, line_qty_received=10,
        line_status="received",
    )
    closed_open = _seed_full_po(
        db, marker, "closed-open", status="closed", line_qty_ordered=5, line_qty_received=2,
    )
    cancelled = _seed_full_po(
        db, marker, "cancelled", status="cancelled", line_qty_ordered=10, line_qty_received=0,
    )

    with TestClient(app) as c:
        outstanding = c.get(
            "/api/v1/scm/purchase-orders", params={"query": marker, "outstanding": "true", "limit": 50}
        )
        closed = c.get(
            "/api/v1/scm/purchase-orders", params={"query": marker, "outstanding": "false", "limit": 50}
        )
    assert outstanding.status_code == 200, outstanding.text
    assert closed.status_code == 200, closed.text

    outstanding_numbers = {po["po_number"] for po in outstanding.json()["data"]}
    closed_numbers = {po["po_number"] for po in closed.json()["data"]}

    assert outstanding_numbers == {active_open, closed_open}
    assert closed_numbers == {draft, active_full, cancelled}
    # Every seeded PO landed in exactly one of the two buckets - nothing dropped, nothing
    # counted twice.
    assert outstanding_numbers | closed_numbers == {
        draft, active_open, active_full, closed_open, cancelled,
    }


def test_outstanding_omitted_returns_every_status(scm_app):
    app, db = _as(scm_app, "purchasing")
    marker = f"ZZTOUTALL-{uuid.uuid4().hex[:8]}"
    draft = _seed_full_po(db, marker, "draft", status="draft", line_qty_ordered=10)
    active = _seed_full_po(db, marker, "active", status="active", line_qty_ordered=10)

    with TestClient(app) as c:
        res = c.get("/api/v1/scm/purchase-orders", params={"query": marker, "limit": 50})

    assert res.status_code == 200, res.text
    numbers = {po["po_number"] for po in res.json()["data"]}
    assert numbers == {draft, active}


def test_default_sort_is_issue_date_falling_back_to_expected_date_desc_nulls_last(scm_app):
    """Not `created_at` (the upload timestamp) - the order's OWN document date, so a bulk
    outstanding-book upload does not bury today's real activity under a stack of
    historical rows stamped with the same import minute."""
    app, db = _as(scm_app, "purchasing")
    marker = f"ZZTSORT-{uuid.uuid4().hex[:8]}"

    older = _seed_full_po(db, marker, "older", status="active", issue_date=date(2026, 1, 10))
    newer = _seed_full_po(db, marker, "newer", status="active", issue_date=date(2026, 8, 15))
    # No issue_date at all - falls back to expected_date, and that is also absent, so it
    # must sort after both dated rows regardless of direction.
    undated = _seed_full_po(db, marker, "undated", status="active")

    with TestClient(app) as c:
        res = c.get("/api/v1/scm/purchase-orders", params={"query": marker, "limit": 50})

    assert res.status_code == 200, res.text
    numbers = [po["po_number"] for po in res.json()["data"]]
    assert numbers.index(newer) < numbers.index(older) < numbers.index(undated), (
        "default order must be newest document date first, undated rows last"
    )
