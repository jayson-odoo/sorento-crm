"""Sub-plan D-2 - email-outbox bulk retry/cancel.

Partial success: a row that can't transition is reported in failed_ids, never
aborting the batch. Duplicates collapse. Selection size is bounded.
"""
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.dependencies import get_db, get_current_user, get_current_user_or_api_key
from app.services.user_service import UserPermissionService
import app.api.v1.system.email_outbox as mod


@pytest.fixture
def client(monkeypatch):
    def _db():
        yield MagicMock()

    _user = {"id": "admin"}
    app.dependency_overrides[get_db] = _db
    # The system router is mounted behind a module guard that runs
    # get_current_user_or_api_key; the route itself uses require_permission →
    # get_current_user. Satisfy both + pass the permission check.
    app.dependency_overrides[get_current_user] = lambda: _user
    app.dependency_overrides[get_current_user_or_api_key] = lambda: _user
    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda self, uid, slug: True
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_bulk_retry_partial_success(client, monkeypatch):
    # rows a,c succeed; b fails (not retryable).
    monkeypatch.setattr(mod, "retry_outbox", lambda db, rid: rid != "b")
    r = client.post("/api/v1/system/email-outbox/bulk-retry", json={"row_ids": ["a", "b", "c"]})
    assert r.status_code == 200
    body = r.json()
    assert body == {"requested": 3, "succeeded": 2, "failed": 1, "failed_ids": ["b"]}


def test_bulk_retry_dedups(client, monkeypatch):
    monkeypatch.setattr(mod, "retry_outbox", lambda db, rid: True)
    r = client.post("/api/v1/system/email-outbox/bulk-retry", json={"row_ids": ["a", "a", "a"]})
    assert r.json()["requested"] == 1
    assert r.json()["succeeded"] == 1


def test_bulk_retry_row_error_counted_failed_not_500(client, monkeypatch):
    def _boom(db, rid):
        if rid == "x":
            raise RuntimeError("db blip")
        return True
    monkeypatch.setattr(mod, "retry_outbox", _boom)
    r = client.post("/api/v1/system/email-outbox/bulk-retry", json={"row_ids": ["ok", "x"]})
    assert r.status_code == 200
    assert r.json()["failed_ids"] == ["x"]


def test_bulk_cancel_uses_cancel(client, monkeypatch):
    called = {}
    def _cancel(db, rid, reason=None):
        called["reason"] = reason
        return True
    monkeypatch.setattr(mod, "cancel_outbox", _cancel)
    r = client.post("/api/v1/system/email-outbox/bulk-cancel", json={"row_ids": ["a"]})
    assert r.status_code == 200
    assert r.json()["succeeded"] == 1
    assert called["reason"] == "cancelled_by_admin"


def test_bulk_empty_rejected(client):
    r = client.post("/api/v1/system/email-outbox/bulk-retry", json={"row_ids": []})
    assert r.status_code == 422


def test_bulk_over_max_rejected(client):
    r = client.post("/api/v1/system/email-outbox/bulk-retry", json={"row_ids": [str(i) for i in range(501)]})
    assert r.status_code == 422
