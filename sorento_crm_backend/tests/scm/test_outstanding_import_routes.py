"""The two endpoints: preview writes nothing, apply writes and commits, RBAC holds.

Uses the suite's savepoint-backed `scm_app` fixture, so everything the route commits is
rolled back on teardown.
"""
from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.inventory import Warehouse
from app.models.product import Product, ProductCategory, UnitOfMeasure
from tests.scm.conftest import as_user, requires_pg, seed_user

_FIX = Path(__file__).parent / "fixtures"
_ITEMS = ("SRTWC8613-RL", "SRTWT7408", "B2155-NL-BLUE", "C-FH24")
_LOCATIONS = ("BRW-BB", "BRW-SMC", "BRW-IB")

pytestmark = requires_pg


def _u() -> str:
    return str(uuid.uuid4())


def as_company_user(app, db, gcu, gcuk, role="purchasing"):
    """Authenticate AND give the session an active company.

    Owned tables are company-scoped and fail closed: with no active company the ORM
    refuses to stamp `company_id` and every insert is rejected. In a real request
    `apply_company_scope` resolves that from the caller's bearer token, which these tests
    replace with a dependency override - so the override has to supply the company too,
    or the route under test cannot write anything and the failure looks like a bug in the
    importer rather than a missing test principal.
    """
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    as_user(app, gcu, gcuk, seed_user(db, role))
    company = db.execute(text("SELECT id FROM companies ORDER BY name LIMIT 1")).scalar()
    if company is None:
        pytest.skip("no company row to scope the session to")
    scope = frozenset({str(company)})

    async def _scope():
        set_company_scope(db, scope)
        return scope

    app.dependency_overrides[apply_company_scope] = _scope
    return scope


def _seed_catalogue(db):
    if not db.execute(text("SELECT 1 FROM import_field_alias "
                           "WHERE doc_type = 'outstanding_so' LIMIT 1")).scalar():
        pytest.skip("no outstanding_so aliases seeded in this database")
    cat = ProductCategory(id=_u(), category_code=f"ZZR-{uuid.uuid4().hex[:6]}",
                          category_name="route test")
    uom = UnitOfMeasure(id=_u(), uom_code=f"ZR{uuid.uuid4().hex[:4]}", uom_name="pcs")
    db.add_all([cat, uom])
    db.flush()
    for code in _ITEMS:
        if not db.execute(text("SELECT 1 FROM products WHERE product_code = :c"),
                          {"c": code}).scalar():
            db.add(Product(id=_u(), product_code=code, product_name=code,
                           category_id=cat.id, base_uom_id=uom.id, list_price=0,
                           is_active=True, is_discontinued=False))
    for code in _LOCATIONS:
        if not db.execute(text("SELECT 1 FROM warehouses WHERE warehouse_code = :c"),
                          {"c": code}).scalar():
            db.add(Warehouse(id=_u(), warehouse_code=code, warehouse_name=code,
                             is_active=True))
    db.flush()


def _upload(name="outstanding_so_sample.xlsx"):
    return {"file": (name, (_FIX / name).read_bytes(),
                     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}


def test_preview_returns_the_diff_and_writes_nothing(scm_app):
    app, db, gcu, gcuk = scm_app
    _seed_catalogue(db)
    as_company_user(app, db, gcu, gcuk)

    before = db.execute(text("SELECT count(*) FROM sales_order_lines")).scalar()
    r = TestClient(app).post("/api/v1/scm/outstanding/sales-orders/preview",
                             files=_upload())
    after = db.execute(text("SELECT count(*) FROM sales_order_lines")).scalar()

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["counts"]["added"] == 5
    assert body["scope_documents"] == ["SO397450", "SO397512"]
    assert before == after, "preview must not write"


def test_apply_writes_the_lines(scm_app):
    app, db, gcu, gcuk = scm_app
    _seed_catalogue(db)
    as_company_user(app, db, gcu, gcuk)

    r = TestClient(app).post("/api/v1/scm/outstanding/sales-orders/apply", files=_upload())

    assert r.status_code == 200, r.text
    assert r.json()["applied"]["added"] == 5
    assert db.execute(text(
        "SELECT count(*) FROM sales_order_lines sol "
        "JOIN sales_orders so ON so.id = sol.sales_order_id "
        "WHERE so.so_number = 'SO397450'"
    )).scalar() == 3


def test_a_file_missing_a_required_column_explains_which_one(scm_app):
    """A 200 carrying ok:false, so the screen can name the column to add."""
    import openpyxl
    from io import BytesIO

    app, db, gcu, gcuk = scm_app
    _seed_catalogue(db)
    as_company_user(app, db, gcu, gcuk)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["S/O NO", "ITEM CODE", "QTY"])
    ws.append(["SO397450", "SRTWC8613-RL", 10])
    buf = BytesIO()
    wb.save(buf)

    r = TestClient(app).post(
        "/api/v1/scm/outstanding/sales-orders/preview",
        files={"file": ("bad.xlsx", buf.getvalue(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert "required_date" in r.json()["missing_columns"]


def test_apply_refuses_a_file_missing_a_required_column(scm_app):
    import openpyxl
    from io import BytesIO

    app, db, gcu, gcuk = scm_app
    _seed_catalogue(db)
    as_company_user(app, db, gcu, gcuk)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["S/O NO", "ITEM CODE", "QTY"])
    ws.append(["SO397450", "SRTWC8613-RL", 10])
    buf = BytesIO()
    wb.save(buf)

    r = TestClient(app).post(
        "/api/v1/scm/outstanding/sales-orders/apply",
        files={"file": ("bad.xlsx", buf.getvalue(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 400
    assert "required_date" in r.text


def test_a_non_excel_upload_is_rejected(scm_app):
    app, db, gcu, gcuk = scm_app
    _seed_catalogue(db)
    as_company_user(app, db, gcu, gcuk)

    r = TestClient(app).post(
        "/api/v1/scm/outstanding/sales-orders/preview",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 400


def test_an_unknown_document_type_is_a_404(scm_app):
    app, db, gcu, gcuk = scm_app
    _seed_catalogue(db)
    as_company_user(app, db, gcu, gcuk)

    r = TestClient(app).post("/api/v1/scm/outstanding/invoices/preview", files=_upload())
    assert r.status_code == 404


def test_a_user_without_the_operator_permission_is_denied(scm_app):
    """Uploading the open order book rewrites what the whole plan is computed from."""
    app, db, gcu, gcuk = scm_app
    _seed_catalogue(db)
    as_user(app, gcu, gcuk, seed_user(db, None))   # no role, no grants

    r = TestClient(app).post("/api/v1/scm/outstanding/sales-orders/preview",
                             files=_upload())
    assert r.status_code == 403
