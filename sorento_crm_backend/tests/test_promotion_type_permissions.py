"""Permission gate on the promotion-type write routes.

These three routes decide what the WhatsApp bot says about an ended promotion:
flipping `special.show_expired` on makes expired specials serve again on both
n8n-facing surfaces. They previously required only authentication, so any
logged-in CRM account could change it. They now require
`marketing.promotion_types.{add,edit,delete}` (registered and granted from the
holders of `marketing.promotions.edit` in migration 362).

Reads stay open on purpose: the promotions edit form and the MCP surface both
need the vocabulary, and neither changes anything.

Dependency-override pattern copied from tests/test_user_sync_respond_permission.py.

Run: pytest tests/test_promotion_type_permissions.py -v
"""
from __future__ import annotations

import uuid

import pytest

from tests._pg_fixture import blank_session

_USER = {"id": str(uuid.uuid4()), "email": "promo-type-caller@zzt.test"}
_BASE = "/api/v1/marketing/promotion-types"


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


@pytest.fixture
def api(db, monkeypatch):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.user_service import UserPermissionService

    allow: set[str] = set()

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: _USER
    # The marketing router sits behind the module guard, which resolves the
    # principal through this dependency - without the override every request
    # 401s before the permission gate under test is ever reached.
    app.dependency_overrides[get_current_user_or_api_key] = lambda: _USER
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
        app.dependency_overrides.pop(get_current_user_or_api_key, None)


def _payload(code: str) -> dict:
    return {
        "type_code": code,
        "type_name": "ZZT Gate Type",
        "show_expired": True,
        "expired_valid_until_year_end": False,
        "expired_max_age_days": None,
        "match_markers": ["zzt-gate"],
        "match_priority": 90,
        "is_default": False,
        "sort_order": 0,
    }


def test_create_denied_without_add_permission(api):
    """A logged-in caller with no grant cannot introduce a type."""
    client, _allow = api
    resp = client.post(f"{_BASE}/", json=_payload("zzt_gate_create"))
    assert resp.status_code == 403
    assert "marketing.promotion_types.add" in resp.json()["detail"]


def test_update_denied_without_edit_permission(api):
    """The dangerous one: switching show_expired on needs the edit grant."""
    client, _allow = api
    resp = client.put(f"{_BASE}/{uuid.uuid4()}", json={"show_expired": True})
    assert resp.status_code == 403
    assert "marketing.promotion_types.edit" in resp.json()["detail"]


def test_delete_denied_without_delete_permission(api):
    """Deleting a type unclassifies its promotions, so it is gated too."""
    client, _allow = api
    resp = client.delete(f"{_BASE}/{uuid.uuid4()}")
    assert resp.status_code == 403
    assert "marketing.promotion_types.delete" in resp.json()["detail"]


def test_create_allowed_with_add_permission(api):
    """With the grant the request reaches the service and creates the row."""
    client, allow = api
    allow.add("marketing.promotion_types.add")

    resp = client.post(f"{_BASE}/", json=_payload("zzt_gate_allowed"))
    assert resp.status_code == 201, resp.text
    assert resp.json()["type_code"] == "zzt_gate_allowed"


def test_reads_stay_open_to_any_authenticated_caller(api):
    """No grant needed to LIST types - the promo form and MCP both read them."""
    client, _allow = api
    resp = client.get(f"{_BASE}/")
    assert resp.status_code == 200
    assert "data" in resp.json()
