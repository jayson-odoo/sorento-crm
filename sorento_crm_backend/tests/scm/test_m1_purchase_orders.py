"""SCM M1 — purchase-order read-only list (Postgres-backed, rolled back)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.scm.conftest import as_user, requires_pg, seed_user

pytestmark = requires_pg


def _as(scm_app, role_slug):
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, role_slug)
    as_user(app, gcu, gcuak, uid)
    return app, db


def test_list_shape_and_lines(scm_app):
    app, _ = _as(scm_app, "purchasing")
    with TestClient(app) as c:
        res = c.get("/api/v1/scm/purchase-orders", params={"limit": 50})
    assert res.status_code == 200, res.text
    body = res.json()
    assert set(body) == {"data", "empty", "pagination"}
    assert body["pagination"]["total"] >= 4  # seed has 4 demo POs
    po = next(p for p in body["data"] if p["po_number"] == "PO-2026/07-0029")
    assert po["status"] == "active"
    assert po["supplier_code"]
    assert po["supplier_name"]
    assert po["expected_date"] == "2026-08-04"
    assert po["line_count"] == 1
    assert po["total_qty"] == 500
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
