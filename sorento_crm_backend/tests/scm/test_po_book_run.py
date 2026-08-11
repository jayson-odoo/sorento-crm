"""S15: the receipts behind "Use PO, don't order".

What is pinned: the endpoint's openness rule is EXACTLY scm.po_ordered_v's, so the
popup's receipts always sum to the Outstanding-PO column already on the row; and a draft
the plan itself proposed is never presented as something already ordered.
"""
from __future__ import annotations

import uuid
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.services.scm import po_book_service
from tests.scm.conftest import requires_pg, seed_user
from tests.scm.test_outstanding_import_routes import as_company_user

pytestmark = requires_pg

MARKER = "ZZTPBK"


def _u() -> str:
    return str(uuid.uuid4())


def _world(db, company_id=None):
    from app.models.product import Product, ProductCategory, UnitOfMeasure
    from tests._pg_fixture import unique_code

    cat = ProductCategory(id=_u(), category_code=unique_code(MARKER),
                          category_name=f"{MARKER} cat")
    uom = UnitOfMeasure(id=_u(), uom_code=unique_code("U")[:20], uom_name=f"{MARKER} u")
    db.add_all([cat, uom])
    db.flush()
    product = Product(id=_u(), product_code=unique_code("P"), product_name=f"{MARKER} p",
                      category_id=cat.id, base_uom_id=uom.id, list_price=0,
                      is_active=True, is_discontinued=False)
    db.add(product)
    db.flush()
    pid = str(product.id)

    wid = _u()
    db.execute(text(
        "INSERT INTO warehouses (id, warehouse_code, warehouse_name, counts_as_available"
        + (", company_id) VALUES (:id, :c, :c, true, :co)" if company_id
           else ") VALUES (:id, :c, :c, true)")),
        {"id": wid, "c": unique_code("W")[:20], **({"co": company_id} if company_id else {})})

    def add_po(number, status, qty, received, line_status="open", expected=None):
        poid = _u()
        db.execute(text(
            "INSERT INTO purchase_orders (id, po_number, status, expected_date, issue_date, "
            "currency, source_system) VALUES (:id, :n, :s, :e, :d, 'CNY', 'test')"),
            {"id": poid, "n": f"{MARKER}-{number}", "s": status, "e": expected,
             "d": date(2026, 7, 1)})
        db.execute(text(
            "INSERT INTO purchase_order_lines (id, purchase_order_id, product_id, "
            "warehouse_id, qty_ordered, qty_received, unit_cost, currency, line_status) "
            "VALUES (:id, :po, :p, :w, :q, :r, 10, 'CNY', :ls)"),
            {"id": _u(), "po": poid, "p": pid, "w": wid, "q": qty, "r": received,
             "ls": line_status})

    add_po("OPEN", "active", 504, 0, expected=date(2026, 8, 10))
    add_po("PART", "partial", 100, 40)
    # A draft this plan itself proposed is NOT something already ordered.
    add_po("DRAFT", "draft_recommendation", 162, 0)
    # A closed line is finished business even on an open order.
    add_po("DONE", "active", 50, 0, line_status="closed")

    run_id = _u()
    db.execute(text(
        "INSERT INTO scm.reorder_run (id, status" + (", company_id" if company_id else "")
        + ", created_at) VALUES (:id, 'completed'" + (", :co" if company_id else "")
        + ", now())"), {"id": run_id, **({"co": company_id} if company_id else {})})
    db.execute(text(
        "INSERT INTO scm.reorder_recommendation "
        "(id, run_id, product_id, warehouse_id, rec_type, rounded_qty"
        + (", company_id) VALUES (:id, :r, :p, :w, 'buy', 10, :co)" if company_id
           else ") VALUES (:id, :r, :p, :w, 'buy', 10)")),
        {"id": _u(), "r": run_id, "p": pid, "w": wid,
         **({"co": company_id} if company_id else {})})
    db.flush()
    return {"run_id": run_id, "product_id": pid, "warehouse_id": wid}


def test_the_receipts_match_the_outstanding_po_column_exactly():
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        w = _world(db)

        out = po_book_service.po_book_for_run(db, w["run_id"])
        receipts = out["po_book"][f"{w['product_id']}:{w['warehouse_id']}"]

        # OPEN 504 + PART 60. The draft and the closed line never appear.
        assert sorted(r["po_number"].split("-")[-1] for r in receipts) == ["OPEN", "PART"]
        assert sum(r["remaining"] for r in receipts) == 564.0

        column = db.execute(text(
            "SELECT ordered FROM scm.po_ordered_v WHERE product_id::text = :p "
            "AND warehouse_id::text = :w"),
            {"p": w["product_id"], "w": w["warehouse_id"]}).scalar()
        assert float(column) == 564.0

        dated = next(r for r in receipts if r["po_number"].endswith("OPEN"))
        assert dated["expected_date"] == "2026-08-10"


def test_the_endpoint_serves_it_and_rbac_holds(scm_app):
    app, db, gcu, gcuk = scm_app
    scope = as_company_user(app, db, gcu, gcuk)
    w = _world(db, company_id=next(iter(scope)))

    with TestClient(app) as c:
        r = c.get(f"/api/v1/scm/reorder-runs/{w['run_id']}/po-book")
        assert r.status_code == 200, r.text
        assert sum(x["remaining"]
                   for x in r.json()["po_book"][f"{w['product_id']}:{w['warehouse_id']}"]) == 564.0

    from app.dependencies import get_current_user, get_current_user_or_api_key
    nobody = seed_user(db, None)
    for dep in (gcu, gcuk):
        app.dependency_overrides[dep] = lambda: {"id": nobody, "email": "x@y", "roles": []}
    with TestClient(app) as c:
        denied = c.get(f"/api/v1/scm/reorder-runs/{w['run_id']}/po-book")
    assert denied.status_code == 403
