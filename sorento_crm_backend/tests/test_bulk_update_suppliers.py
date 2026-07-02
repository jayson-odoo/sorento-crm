"""Whitelisted bulk-update — suppliers (`is_active`).

Verifies the safe bulk-edit contract:
  - happy path: N rows updated via the NORMAL service update path (audit fires
    for free because Supplier.__audit_track__ is on).
  - whitelist rejection: a field not on the per-resource allow-list -> 400.
  - value allow-list: a value not valid for the field -> 400.
  - partial success: not-found + a service-rejected row land in `skipped` with a
    human reason; the rest commit (never all-or-nothing).
  - selection bounds: empty and >500 ids -> 422.
  - auth denial: no principal -> 401.

Mirrors the dependency-override pattern from tests/test_email_outbox_bulk.py.
"""
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.dependencies import get_db, get_current_user, get_current_user_or_api_key
from app.services.user_service import UserPermissionService
from app.services.error_handler import AppException
from app.services.procurement_service import SupplierService
from app.services import bulk_update_registry as reg

BULK_URL = "/api/v1/procurement/suppliers/bulk-update"


class _Row:
    """Stand-in for a Supplier ORM row (only the attrs the registry touches)."""

    def __init__(self, rid: str, name: str):
        self.id = rid
        self.supplier_name = name
        self.supplier_code = f"SUP-{rid}"


@pytest.fixture
def client(monkeypatch):
    def _db():
        yield MagicMock()

    _user = {"id": "admin"}
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: _user
    app.dependency_overrides[get_current_user_or_api_key] = lambda: _user
    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda self, uid, slug: True
    )

    # Isolate the suppliers registration from a real DB: control which ids "exist"
    # and record every call to the normal service update path.
    existing = {"s1": _Row("s1", "Alpha Traders"), "s2": _Row("s2", "Beta Supplies")}
    res = reg.get_bulk_resource("suppliers")
    monkeypatch.setattr(res, "load_row", lambda db, rid: existing.get(rid))

    yield TestClient(app)
    app.dependency_overrides.clear()


def _spy_update(monkeypatch):
    """Patch the REAL single-record service update and return the recorded calls,
    proving bulk edits route through the normal (audited) path — not a raw write."""
    calls: list[tuple] = []

    def _update(self, supplier_id, supplier_data):
        calls.append((supplier_id, supplier_data))
        return MagicMock()

    monkeypatch.setattr(SupplierService, "update_supplier", _update)
    return calls


def test_bulk_update_happy_path(client, monkeypatch):
    calls = _spy_update(monkeypatch)
    r = client.post(BULK_URL, json={"ids": ["s1", "s2"], "field": "is_active", "value": "false"})
    assert r.status_code == 200
    body = r.json()
    assert body["updated"] == 2
    assert body["skipped"] == []
    # Went through the normal service update path (audit trail comes for free).
    assert [c[0] for c in calls] == ["s1", "s2"]
    assert all(c[1].is_active is False for c in calls)


def test_field_not_whitelisted_400(client, monkeypatch):
    _spy_update(monkeypatch)
    r = client.post(
        BULK_URL, json={"ids": ["s1"], "field": "supplier_name", "value": "Hacked Inc"}
    )
    assert r.status_code == 400
    assert "cannot be bulk-updated" in r.json()["message"]


def test_disallowed_value_400(client, monkeypatch):
    _spy_update(monkeypatch)
    r = client.post(BULK_URL, json={"ids": ["s1"], "field": "is_active", "value": "maybe"})
    assert r.status_code == 400
    assert "Active or Inactive" in r.json()["message"]


def test_partial_success_skips_bad_rows(client, monkeypatch):
    calls: list[str] = []

    def _update(self, supplier_id, supplier_data):
        calls.append(supplier_id)
        if supplier_id == "s2":
            raise AppException(status_code=400, message="Supplier is locked and cannot change.")
        return MagicMock()

    monkeypatch.setattr(SupplierService, "update_supplier", _update)

    r = client.post(
        BULK_URL,
        json={"ids": ["s1", "missing", "s2"], "field": "is_active", "value": "true"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["updated"] == 1  # only s1
    reasons = {s["id"]: s["reason"] for s in body["skipped"]}
    assert set(reasons) == {"missing", "s2"}
    assert reasons["missing"] == "Record not found."
    assert reasons["s2"] == "Supplier is locked and cannot change."
    # Labels are human-readable, never a raw id, for rows we could load.
    labels = {s["id"]: s["label"] for s in body["skipped"]}
    assert labels["s2"] == "Beta Supplies"
    # The failing row was actually attempted through the normal service path.
    assert "s2" in calls


def test_duplicate_ids_deduped(client, monkeypatch):
    calls = _spy_update(monkeypatch)
    r = client.post(
        BULK_URL, json={"ids": ["s1", "s1", "s1"], "field": "is_active", "value": "false"}
    )
    assert r.status_code == 200
    assert r.json()["updated"] == 1
    assert len(calls) == 1


def test_empty_ids_rejected(client):
    r = client.post(BULK_URL, json={"ids": [], "field": "is_active", "value": "false"})
    assert r.status_code == 422


def test_over_max_ids_rejected(client):
    r = client.post(
        BULK_URL,
        json={"ids": [f"id-{i}" for i in range(501)], "field": "is_active", "value": "false"},
    )
    assert r.status_code == 422


def test_auth_denied_without_principal():
    """No override of the auth deps -> real deps run -> 401 (no principal)."""
    app.dependency_overrides[get_db] = lambda: (_ for _ in [MagicMock()])
    try:
        c = TestClient(app)
        r = c.post(BULK_URL, json={"ids": ["s1"], "field": "is_active", "value": "false"})
        assert r.status_code in (401, 403)
    finally:
        app.dependency_overrides.clear()
