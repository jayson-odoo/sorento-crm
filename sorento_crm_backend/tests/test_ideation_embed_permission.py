"""Ideation embed route permission gate tests.

Verifies that the ``/api/v1/integrations/ideation/embed-session`` endpoint is
gated on ``ideation.board.view`` (Slice 1, module-access-gates plan).

- A user WITHOUT ``ideation.board.view`` gets 403 with detail containing the slug.
- A user WITH the permission passes the dependency (the route answers normally).
- The slug is registered in ``PERMISSION_REGISTRY``.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.rbac.permission_registry import PERMISSION_REGISTRY


_USER = {"id": str(uuid.uuid4()), "email": "zzt-ideation-perm@zzt.test", "name": "ZZT"}
_EMBED_URL = "/api/v1/integrations/ideation/embed-session"
_SLUG = "ideation.board.view"


# ------------------------------------------------------------------ registry
def test_ideation_board_view_slug_registered():
    """The slug must exist in the central permission registry."""
    slugs = {entry["slug"] for entry in PERMISSION_REGISTRY}
    assert _SLUG in slugs


# -------------------------------------------------------- route-level 403/200
@pytest.fixture()
def api(monkeypatch):
    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    allow: set[str] = set()

    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: dict(_USER)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(_USER)
    app.dependency_overrides[apply_company_scope] = lambda: None

    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in allow,
    )

    client = TestClient(app)
    try:
        yield client, allow
    finally:
        app.dependency_overrides.clear()


def test_embed_session_403_without_ideation_board_view(api):
    """A user who lacks the permission gets 403 naming the slug."""
    client, _allow = api
    # allow set is empty: user has NO permissions
    resp = client.post(_EMBED_URL, json={})
    assert resp.status_code == 403, resp.text
    assert "ideation.board.view" in resp.json()["detail"]


def test_embed_session_passes_with_ideation_board_view(api, monkeypatch):
    """A user who holds the permission passes the gate (route runs normally)."""
    client, allow = api
    allow.add(_SLUG)

    # Stub the service so the route does not require real config
    import app.api.v1.integrations.ideation_embed as route_mod

    monkeypatch.setattr(
        route_mod,
        "create_embed_session",
        lambda db, user, *, idea_id=None: {
            "iframe_url": "https://shared.test/embed/ideas",
            "token": "t",
            "expires_at": "2099-01-01T00:00:00+00:00",
        },
    )
    resp = client.post(_EMBED_URL, json={})
    assert resp.status_code == 200, resp.text
