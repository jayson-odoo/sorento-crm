"""GET /api/v1/user-management/users/respond-users was previously gated only by
`Depends(get_current_user)` - any authenticated user, regardless of role or
permission, could list every Respond.io agent (id/name/email) for dropdown
selection. The route now requires `user_management.users.view` via
`Depends(require_permission(...))`, matching the rest of the user-management
surface. These tests cover the gate:

1. A caller without the permission gets 403 with the permission slug named in
   the error detail, and the Respond.io client is never constructed (no
   accidental network call before the permission check runs).
2. A caller with the permission gets 200 with the formatted Respond.io agent
   list (id/name/email), using a monkeypatched RespondClient so no real
   network call happens either way.

Both sentinels record instead of raise/assert internally: the route handler
wraps its body in `except Exception: return []`, so a bare `raise
AssertionError` (construction not expected) or `assert limit == 500` (call
argument check) inside the monkeypatched client would be swallowed into a
200 empty list and never surface with a useful failure message. Instead each
sentinel appends to a plain list (`constructed`, `captured_limits`) and the
test asserts on that list after the response check, outside the route's
except block.

Dependency-override pattern copied from tests/test_product_specifications_routes.py
(overrides get_db / get_current_user, monkeypatches
UserPermissionService.check_user_has_permission against an `allow` set of
granted slugs).

Run: pytest tests/test_user_respond_users_permission.py -v
"""
from __future__ import annotations

import uuid

import pytest

from tests._pg_fixture import blank_session

ENDPOINT = "/api/v1/user-management/users/respond-users"
PERMISSION = "user_management.users.view"
_USER = {"id": str(uuid.uuid4()), "email": "respond-users-caller@zzt.test"}


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


class _RespondClientNotConstructed:
    """Sentinel that records a construction attempt instead of raising. The
    route handler wraps its body in `except Exception: return []`, so a raise
    inside `__init__` would be swallowed into a 200 empty list and never
    surface with a useful message. Instead, construction appends to a shared
    `constructed` list, and the test asserts `constructed == []` after the
    response check - proving the permission check denied the request before
    the Respond.io client was ever built."""

    def __init__(self, constructed, *args, **kwargs):
        constructed.append(True)


def test_respond_users_denied_without_permission(api, monkeypatch):
    client, allow = api
    constructed: list = []
    monkeypatch.setattr(
        "app.services.integration_service.RespondClient",
        lambda *args, **kwargs: _RespondClientNotConstructed(constructed, *args, **kwargs),
    )

    resp = client.get(ENDPOINT)

    assert resp.status_code == 403
    assert PERMISSION in resp.json()["detail"]
    assert constructed == []


def test_respond_users_returns_formatted_list_with_permission(api, monkeypatch):
    client, allow = api
    allow.add(PERMISSION)

    raw_users = [
        {"id": 11, "name": "Agent A", "email": "a@x.test"},
        {"userId": "22", "displayName": "Agent B"},
        {"name": "no id"},
    ]
    captured_limits: list = []

    class _FakeRespondClient:
        def __init__(self, *args, **kwargs):
            pass

        def list_users(self, limit=500):
            captured_limits.append(limit)
            return raw_users

    monkeypatch.setattr(
        "app.services.integration_service.RespondClient",
        _FakeRespondClient,
    )

    resp = client.get(ENDPOINT)

    assert resp.status_code == 200
    assert resp.json() == [
        {"id": "11", "name": "Agent A", "email": "a@x.test"},
        {"id": "22", "name": "Agent B", "email": ""},
    ]
    assert captured_limits == [500]
