"""The two endpoints: preview writes nothing, apply writes and commits, RBAC holds.

Uses the suite's savepoint-backed `scm_app` fixture, so everything the route commits is
rolled back on teardown.

Like the service tests, the upload is GENERATED from codes this test owns
(`tests/scm/_outstanding_workbooks.py`) rather than read from the committed xlsx that names
the real extract's `BRW-BB` / `SRTWC8613-RL` / `SO397450`. Two things were wrong with the old
shape and both made the result depend on which database the test met:

* it seeded those literal codes (guarded by "insert only if absent", which is what made the
  collision survivable rather than fixed), and
* it scoped the request to `SELECT id FROM companies ORDER BY name LIMIT 1` while the
  catalogue it seeded was stamped with the test-default company. One company on an empty
  database, so they agreed; two on a prod copy, so the importer resolved nothing.

Now the principal comes first, carrying a company the test created, and everything is seeded
into that company.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.scm._outstanding_workbooks import (
    MARKER,
    make_codes,
    require_aliases,
    seed_catalogue,
    week1,
    workbook,
)
from tests.scm.conftest import as_user, requires_pg, seed_user

pytestmark = requires_pg

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def as_company_user(app, db, gcu, gcuk, role="purchasing"):
    """Authenticate AND give the session an active company of this test's own making.

    Owned tables are company-scoped and fail closed: with no active company the ORM refuses
    to stamp `company_id` and every insert is rejected. In a real request
    `apply_company_scope` resolves that from the caller's bearer token, which these tests
    replace with a dependency override - so the override has to supply the company too, or
    the route under test cannot write anything and the failure looks like a bug in the
    importer rather than a missing test principal.

    The company is CREATED here rather than borrowed with `ORDER BY name LIMIT 1`. Borrowing
    picks a different row depending on which companies the database happens to hold, and when
    that is not the company the catalogue was stamped with, the importer resolves nothing.
    The scope is also set on the session immediately, so rows seeded after this call land in
    the same company the route will read under.
    """
    from app.models.base import set_company_scope
    from app.models.company import Company
    from app.services.company_scope_resolver import apply_company_scope

    as_user(app, gcu, gcuk, seed_user(db, role))

    company_id = str(uuid.uuid4())
    db.add(Company(id=company_id, name=f"{MARKER} route company {company_id[:8]}",
                   code=f"{MARKER}-{uuid.uuid4().hex[:6]}".upper()[:50], is_active=True))
    db.flush()
    scope = frozenset({company_id})
    set_company_scope(db, scope)

    async def _scope():
        set_company_scope(db, scope)
        return scope

    app.dependency_overrides[apply_company_scope] = _scope
    return scope


def _seed(db):
    """This test's own codes, plus the products and warehouses its upload names."""
    codes = make_codes()
    seed_catalogue(db, codes)
    return codes


def _upload(data: bytes, name: str = "outstanding_so.xlsx"):
    return {"file": (name, data, _XLSX)}


def _missing_column_file(codes) -> bytes:
    """A file with no delivery-date column: a different report, which would wipe every date
    in scope if it were accepted."""
    return workbook([[codes.project_so, codes.item_rl, 10]],
                    headers=("S/O NO", "ITEM CODE", "QTY"))


def test_preview_returns_the_diff_and_writes_nothing(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    codes = _seed(db)

    before = db.execute(text("SELECT count(*) FROM sales_order_lines")).scalar()
    r = TestClient(app).post("/api/v1/scm/outstanding/sales-orders/preview",
                             files=_upload(week1(codes)))
    after = db.execute(text("SELECT count(*) FROM sales_order_lines")).scalar()

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["counts"]["added"] == 5
    assert body["scope_documents"] == list(codes.documents)
    assert before == after, "preview must not write"


def test_apply_writes_the_lines(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    codes = _seed(db)

    r = TestClient(app).post("/api/v1/scm/outstanding/sales-orders/apply",
                             files=_upload(week1(codes)))

    assert r.status_code == 200, r.text
    assert r.json()["applied"]["added"] == 5
    assert db.execute(text(
        "SELECT count(*) FROM sales_order_lines sol "
        "JOIN sales_orders so ON so.id = sol.sales_order_id "
        "WHERE so.so_number = :so"
    ), {"so": codes.project_so}).scalar() == 3


def test_a_file_missing_a_required_column_explains_which_one(scm_app):
    """A 200 carrying ok:false, so the screen can name the column to add."""
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    codes = _seed(db)

    r = TestClient(app).post(
        "/api/v1/scm/outstanding/sales-orders/preview",
        files=_upload(_missing_column_file(codes), "bad.xlsx"),
    )

    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert "required_date" in r.json()["missing_columns"]


def test_apply_refuses_a_file_missing_a_required_column(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    codes = _seed(db)

    r = TestClient(app).post(
        "/api/v1/scm/outstanding/sales-orders/apply",
        files=_upload(_missing_column_file(codes), "bad.xlsx"),
    )
    assert r.status_code == 400
    assert "required_date" in r.text


def test_a_non_excel_upload_is_rejected(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)

    r = TestClient(app).post(
        "/api/v1/scm/outstanding/sales-orders/preview",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 400


def test_an_unknown_document_type_is_a_404(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    codes = _seed(db)

    r = TestClient(app).post("/api/v1/scm/outstanding/invoices/preview",
                             files=_upload(week1(codes)))
    assert r.status_code == 404


def test_a_user_without_the_operator_permission_is_denied(scm_app):
    """Uploading the open order book rewrites what the whole plan is computed from."""
    app, db, gcu, gcuk = scm_app
    require_aliases(db)
    as_user(app, gcu, gcuk, seed_user(db, None))   # no role, no grants

    # No catalogue seeded on purpose: the denial must happen before the file is read.
    r = TestClient(app).post("/api/v1/scm/outstanding/sales-orders/preview",
                             files=_upload(week1(make_codes())))
    assert r.status_code == 403
