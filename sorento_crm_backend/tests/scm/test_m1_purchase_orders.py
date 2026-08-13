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
