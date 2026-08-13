"""The reorder-level upload endpoints: preview writes nothing, apply writes, RBAC holds.

Same savepoint-backed `scm_app` harness as the outstanding-import routes, and the same
test-owned principal + company, for the same reason: owned tables fail closed on company
scope, and a borrowed company makes the result depend on which database the test met.
"""
from __future__ import annotations

import io
import uuid

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import text

from tests.scm.conftest import as_user, requires_pg, seed_user
from tests.scm.test_outstanding_import_routes import as_company_user

pytestmark = requires_pg

MARKER = "ZZTRLR"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _workbook(rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(["Item Code", "Location", "Reorder Level", "Reorder Qty"])
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _upload(data: bytes):
    return {"file": ("reorder_levels.xlsx", data, _XLSX)}


def _seed(db, scope) -> tuple[str, str]:
    """A product and a warehouse of this test's own, stamped into the ACTIVE company.

    Raw SQL bypasses the ORM company stamp, and the route reads products and warehouses
    through the company-scoped ORM, which never sees a NULL-company row."""
    company_id = next(iter(scope))
    code = f"{MARKER}-P-{uuid.uuid4().hex[:6]}"
    wh = f"{MARKER}-W-{uuid.uuid4().hex[:6]}"[:20]
    cat_id, uom_id, pid, wid = (str(uuid.uuid4()) for _ in range(4))
    db.execute(text(
        "INSERT INTO product_categories (id, category_code, category_name) "
        "VALUES (:id, :c, :c)"), {"id": cat_id, "c": f"{MARKER}-{uuid.uuid4().hex[:6]}"})
    db.execute(text(
        "INSERT INTO units_of_measure (id, uom_code, uom_name) VALUES (:id, :c, :c)"),
        {"id": uom_id, "c": f"U{uuid.uuid4().hex[:8]}"})
    db.execute(text(
        "INSERT INTO products (id, product_code, product_name, category_id, base_uom_id, "
        "list_price, is_active, is_discontinued, company_id) "
        "VALUES (:id, :c, :c, :cat, :uom, 0, true, false, :co)"),
        {"id": pid, "c": code, "cat": cat_id, "uom": uom_id, "co": company_id})
    db.execute(text(
        "INSERT INTO warehouses (id, warehouse_code, warehouse_name, is_active, "
        "counts_as_available, company_id) VALUES (:id, :c, :c, true, true, :co)"),
        {"id": wid, "c": wh, "co": company_id})
    db.flush()
    return code, wh


def test_preview_reports_the_outcome_and_writes_nothing(scm_app):
    app, db, gcu, gcuk = scm_app
    scope = as_company_user(app, db, gcu, gcuk)
    code, wh = _seed(db, scope)

    before = db.execute(text("SELECT count(*) FROM scm.reorder_level")).scalar()
    r = TestClient(app).post("/api/v1/scm/reorder-levels/import/preview",
                             files=_upload(_workbook([[code, wh, 120, 40]])))
    after = db.execute(text("SELECT count(*) FROM scm.reorder_level")).scalar()

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["readable"] is True
    assert body["created"] == 1
    assert before == after, "preview must not write"


def test_apply_writes_the_level_with_autocount_ownership(scm_app):
    app, db, gcu, gcuk = scm_app
    scope = as_company_user(app, db, gcu, gcuk)
    code, wh = _seed(db, scope)

    r = TestClient(app).post("/api/v1/scm/reorder-levels/import/apply",
                             files=_upload(_workbook([[code, wh, 120, 40]])))

    assert r.status_code == 200, r.text
    assert r.json()["created"] == 1
    row = db.execute(text(
        "SELECT rl.level, rl.reorder_qty, rl.source FROM scm.reorder_level rl "
        "JOIN products p ON p.id = rl.product_id WHERE p.product_code = :c"),
        {"c": code}).mappings().first()
    assert row is not None
    assert float(row["level"]) == 120
    assert float(row["reorder_qty"]) == 40
    assert row["source"] == "autocount"


def test_a_user_without_the_planning_grant_cannot_upload_levels(scm_app):
    """Setting a level changes what the next plan buys - a planning action, same
    permission as launching a run. A principal with no grants gets 403 before the file
    is even read."""
    app, db, gcu, gcuk = scm_app
    as_user(app, gcu, gcuk, seed_user(db, None))   # no role, no grants

    r = TestClient(app).post("/api/v1/scm/reorder-levels/import/apply",
                             files=_upload(_workbook([["X", "Y", 1, 1]])))

    assert r.status_code == 403, r.text


def test_a_file_missing_the_level_column_is_named_not_half_applied(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)

    wb = Workbook()
    ws = wb.active
    ws.append(["Item Code", "Reorder Qty"])
    ws.append(["ANY", 4])
    buf = io.BytesIO()
    wb.save(buf)

    r = TestClient(app).post("/api/v1/scm/reorder-levels/import/apply",
                             files=_upload(buf.getvalue()))

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["readable"] is False
    assert "reorder_level" in body["missing_columns"]
    assert body["created"] == 0
