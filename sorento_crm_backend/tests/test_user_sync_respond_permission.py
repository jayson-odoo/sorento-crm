"""Permission gate on POST /users/{user_id}/sync-respond.

The route previously required only authentication (bare get_current_user), so any
authenticated user could trigger/overwrite any other user's Respond.io linkage.
It now requires user_management.users.edit, matching the sibling admin mutation
routes on the same router (update, restore, resend-invite, force-logout).

Dependency-override pattern copied from tests/test_product_specifications_routes.py
(overrides get_db / get_current_user, monkeypatches
UserPermissionService.check_user_has_permission against an `allow` set).

Run: pytest tests/test_user_sync_respond_permission.py -v
"""
from __future__ import annotations

import uuid

import pytest

from tests._pg_fixture import blank_session

_USER = {"id": str(uuid.uuid4()), "email": "sync-respond-caller@zzt.test"}


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


@pytest.fixture
def api(db, monkeypatch):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user
    from app.main import app
    from app.services.user_service import UserPermissionService

    allow: set[str] = set()

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: _USER
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in allow,
    )
    client = TestClient(app)
    try:
        yield client, allow
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


def _url(user_id: str) -> str:
    return f"/api/v1/user-management/users/{user_id}/sync-respond"


def test_sync_respond_denied_without_users_edit(api):
    """Authenticated but non-privileged caller gets 403, before any service work."""
    client, _allow = api
    resp = client.post(_url(str(uuid.uuid4())), json={"respond_user_id": "12345"})
    assert resp.status_code == 403
    assert "user_management.users.edit" in resp.json()["detail"]


def test_sync_respond_allowed_with_users_edit(api, monkeypatch):
    """Caller holding user_management.users.edit reaches the service and gets its result."""
    from app.services.user_service import UserService

    client, allow = api
    allow.add("user_management.users.edit")

    target_id = str(uuid.uuid4())
    calls: list[tuple] = []

    def _fake_sync(self, user_id, respond_user_id=None):
        calls.append((user_id, respond_user_id))
        return {"status": "successful", "message": "Respond user synced successfully."}

    monkeypatch.setattr(UserService, "sync_respond_user", _fake_sync)

    resp = client.post(_url(target_id), json={"respond_user_id": "12345"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "successful"
    assert calls == [(target_id, "12345")]
