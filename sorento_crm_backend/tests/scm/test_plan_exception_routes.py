"""SCM S5 - the Plan Exception endpoints (UAC Group D).

Happy path, auth denial and validation for both routes, against Postgres with every row the
test needs seeded by the test.

The claim worth pinning at this level, over and above the service tests: the endpoints
COMPUTE nothing. The batch is frozen when the upload is confirmed, so a GET returns what was
written, and a reviewer's decision lands against the figures the engine actually saw.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.models.inventory import Stock, Warehouse
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.scm import PlanException
from app.services.scm import plan_exception_service as svc
from app.services.scm.plan_exception_engine import Position
from app.services.sla_service import MALAYSIA_TZ, to_naive_datetime
from tests.scm.conftest import as_user, requires_pg, seed_user

pytestmark = requires_pg

MARKER = "ZZTPEXR"


def _u() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:8]}".upper()


def _today() -> date:
    return to_naive_datetime(datetime.now(MALAYSIA_TZ)).date()


def _client(scm_app, role_slug: str):
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, role_slug)
    as_user(app, gcu, gcuak, uid)
    return app, db


def _world(db):
    cat = ProductCategory(id=_u(), category_code=_code("CAT")[:40], category_name=_code("cat"))
    uom = UnitOfMeasure(id=_u(), uom_name=_code("uom"), uom_code=_code("U")[:20])
    db.add_all([cat, uom])
    db.flush()

    wh = Warehouse(
        id=_u(), warehouse_code=_code("WH")[:30], warehouse_name=f"{MARKER} wh",
        is_active=True, counts_as_available=True,
    )
    db.add(wh)
    db.flush()
    wh.pool_warehouse_id = wh.id

    product = Product(
        id=_u(), product_code=_code("P"), product_name=f"{MARKER} product",
        category_id=cat.id, base_uom_id=uom.id, list_price=0,
        is_active=True, is_discontinued=True,
    )
    db.add(product)
    db.flush()
    db.add(Stock(id=_u(), product_id=product.id, warehouse_id=wh.id, quantity_on_hand=10))

    supplier = Supplier(id=_u(), supplier_code=_code("S")[:30],
                        supplier_name=f"{MARKER} supplier")
    db.add(supplier)
    db.flush()
    po = PurchaseOrder(id=_u(), po_number=_code("PO")[:50], supplier_id=supplier.id,
                       status="active", issue_date=_today() - timedelta(days=10))
    db.add(po)
    db.flush()
    db.add(PurchaseOrderLine(
        id=_u(), purchase_order_id=po.id, product_id=product.id, warehouse_id=wh.id,
        qty_ordered=240, qty_received=0, expected_date=_today() + timedelta(days=45),
        line_status="open",
    ))
    db.flush()
    return product, wh, po


def _batch_with_one_exception(db, product):
    pid = str(product.id)
    svc.generate_batch(
        db,
        before={pid: svc.Snapshot(position=Position(first_need_at=_today()), points=[])},
        after={pid: svc.Snapshot(position=Position(surplus_qty=500), points=[])},
        delta_count=412,
    )
    db.flush()
    return db.query(PlanException).order_by(PlanException.created_at.desc()).first()


def test_get_returns_the_frozen_batch_with_both_counts(scm_app):
    app, db = _client(scm_app, "purchasing")
    product, wh, po = _world(db)
    _batch_with_one_exception(db, product)

    with TestClient(app) as c:
        body = c.get("/api/v1/scm/plan-exceptions").json()

    assert body["counts"]["delta_count"] == 412
    assert body["counts"]["exception_count"] == 1
    assert body["counts"]["open_count"] == 1
    row = body["rows"][0]
    assert row["product_code"] == product.product_code
    assert row["po_number"] == po.po_number
    # Frozen with the row, not recomputed on read.
    assert row["reading"]["lifecycle"]["source"] == "products.is_discontinued"
    assert row["actions"][0]["rank"] == 1


def test_get_with_no_batch_is_an_empty_report_not_a_404(scm_app):
    app, db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        res = c.get("/api/v1/scm/plan-exceptions", params={"run_id": str(uuid.uuid4())})
    assert res.status_code == 200
    assert res.json()["rows"] == []


def test_get_rejects_a_status_that_is_not_one_of_the_three(scm_app):
    app, db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        res = c.get("/api/v1/scm/plan-exceptions", params={"status": "maybe"})
    assert res.status_code == 422


def test_get_is_denied_without_the_view_permission(scm_app):
    app, db = _client(scm_app, None)  # a user with no role at all
    with TestClient(app) as c:
        res = c.get("/api/v1/scm/plan-exceptions")
    assert res.status_code == 403


def test_decision_records_who_decided_what(scm_app):
    app, db = _client(scm_app, "purchasing")
    product, wh, po = _world(db)
    row = _batch_with_one_exception(db, product)
    first = row.actions_json[0]["code"]

    with TestClient(app) as c:
        res = c.post(
            f"/api/v1/scm/plan-exceptions/{row.id}/decision",
            json={"status": "approved", "action_code": first},
        )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "approved"
    assert body["decided_action"] == first
    # A human name, never a user id (the seeded user is named "SCM Test").
    assert body["decided_by"] == "SCM Test"


def test_decision_refuses_a_reject_with_no_reason(scm_app):
    app, db = _client(scm_app, "purchasing")
    product, wh, po = _world(db)
    row = _batch_with_one_exception(db, product)

    with TestClient(app) as c:
        res = c.post(
            f"/api/v1/scm/plan-exceptions/{row.id}/decision",
            json={"status": "rejected", "reason": "  "},
        )
    assert res.status_code == 422


def test_decision_refuses_an_action_this_exception_never_proposed(scm_app):
    app, db = _client(scm_app, "purchasing")
    product, wh, po = _world(db)
    row = _batch_with_one_exception(db, product)
    proposed = {a["code"] for a in row.actions_json}
    absent = next(c for c in svc.ACTION_CODES if c not in proposed)

    with TestClient(app) as c:
        res = c.post(
            f"/api/v1/scm/plan-exceptions/{row.id}/decision",
            json={"status": "approved", "action_code": absent},
        )
    assert res.status_code == 422


def test_deciding_an_exception_that_does_not_exist_is_a_404(scm_app):
    app, db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        res = c.post(
            f"/api/v1/scm/plan-exceptions/{uuid.uuid4()}/decision",
            json={"status": "approved", "action_code": "accept"},
        )
    assert res.status_code == 404


def test_decision_is_denied_without_the_run_permission(scm_app):
    """Reading the queue and changing a supplier's order are different rights."""
    app, db = _client(scm_app, None)
    product, wh, po = _world(db)
    row = _batch_with_one_exception(db, product)

    with TestClient(app) as c:
        res = c.post(
            f"/api/v1/scm/plan-exceptions/{row.id}/decision",
            json={"status": "approved", "action_code": "accept"},
        )
    assert res.status_code == 403
