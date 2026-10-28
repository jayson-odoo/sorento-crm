"""A TestClient for the FILTER-MULTISELECT list-filter tests.

One caller who passes every permission check, one Postgres session that rolls back, the company scope
pinned to ``SORENTO``. Each test file seeds its own rows through ``blank_session`` and asserts through
HTTP. ``open_client`` is a context manager so a file's fixture stays three lines.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager

from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.models.base import set_company_scope
from app.models.user import User
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.company_scope_resolver import apply_company_scope
from app.services.user_service import UserPermissionService

SORENTO = DEFAULT_COMPANY_ID


class _EverySlug(frozenset):
    """A slug set that holds every slug: ``require_any_permission`` reads the user's slug set
    rather than ``check_user_has_permission`` (the parties list moved onto it in #1957)."""

    def __contains__(self, _slug):
        return True


@contextmanager
def open_client(db, monkeypatch, scope=frozenset({SORENTO})):
    actor = User(id=str(uuid.uuid4()), email=f"zzt-{uuid.uuid4().hex[:8]}@test.com", name="ZZT Actor")
    db.add(actor)
    db.flush()
    principal = {"id": actor.id, "email": actor.email}
    set_company_scope(db, scope)

    def _override_db():
        yield db

    async def _override_scope():
        set_company_scope(db, scope)
        return scope

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: principal
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
    app.dependency_overrides[apply_company_scope] = _override_scope
    monkeypatch.setattr(UserPermissionService, "check_user_has_permission", lambda self, uid, slug: True)
    monkeypatch.setattr(UserPermissionService, "get_user_permission_slugs", lambda self, uid: _EverySlug())
    try:
        yield TestClient(app), actor
    finally:
        app.dependency_overrides.clear()


def ok_ids(resp, key: str = "id") -> set[str]:
    """The ``key`` of every row of a standard ``{data: [...]}`` list envelope."""
    assert resp.status_code == 200, resp.text
    return {row[key] for row in resp.json()["data"]}


def get(client, url: str, pairs):
    """GET with params as pairs, so a key can repeat."""
    if isinstance(pairs, dict):
        pairs = list(pairs.items())
    return client.get(url, params=pairs)
