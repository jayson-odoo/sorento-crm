"""PORTAL-P3-ROLE-MENU round 10, A: GET /public/portal/me carries `crm_user_id` for an IMPERSONATION
token whose contact has a linked active salesperson user, else null. Also pins that GET /users/me
returns the user's own `respond_contact_id` (the source MySlug uses to start a contact impersonation).
Postgres only, every row seeded here."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.dependencies import get_current_user, get_current_user_or_api_key
from app.main import app
from app.models.portal import PortalToken
from tests._pg_fixture import blank_session
from tests.test_portal_p3_impersonation_crm_user import _start
from tests.test_portal_p3_role_menu import _chain, _user

PORTAL_ME = "/api/v1/public/portal/me"


def _get(db, path, headers=None, actor_id=None):
    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    if actor_id:
        app.dependency_overrides[get_current_user] = lambda: {"id": actor_id}
        app.dependency_overrides[get_current_user_or_api_key] = lambda: {"id": actor_id}
    try:
        with TestClient(app) as tc:
            return tc.get(path, headers=headers or {})
    finally:
        for dep in (get_db, get_current_user, get_current_user_or_api_key):
            app.dependency_overrides.pop(dep, None)


def _impersonation_token(db, admin_id, contact_id) -> str:
    res = _start(db, admin_id, contact_id)
    assert res.status_code == 200, res.text
    return parse_qs(urlparse(res.json()["portal_url"]).query)["token"][0]


def _normal_token(db, ws, contact) -> str:
    now = datetime.utcnow()
    row = PortalToken(
        token=secrets.token_urlsafe(48),
        contact_id=contact.id,
        space_id=ws.space_id,
        expires_at=now + timedelta(days=1),
        verified_at=now,
        is_impersonation=False,
    )
    db.add(row)
    db.commit()
    return row.token


def _me(db, token):
    res = _get(db, PORTAL_ME, headers={"X-Portal-Token": token})
    assert res.status_code == 200, res.text
    return res.json()


def test_a_impersonation_token_of_a_salesperson_contact_carries_crm_user_id():
    with blank_session() as db:
        _, contact = _chain(db)
        admin = _user(db, ["admin"])
        sp = _user(db, ["salesperson"], contact=contact)
        assert _me(db, _impersonation_token(db, admin.id, contact.id))["crm_user_id"] == sp.id


def test_a_normal_token_of_the_same_contact_has_null():
    with blank_session() as db:
        ws, contact = _chain(db)
        _user(db, ["salesperson"], contact=contact)
        body = _me(db, _normal_token(db, ws, contact))
        assert "crm_user_id" in body
        assert body["crm_user_id"] is None


@pytest.mark.parametrize(
    "roles,kw",
    [
        (None, {}),
        (["purchasing"], {}),
        (["salesperson", "purchasing"], {}),
        (["salesperson"], {"status": "INACTIVE"}),
    ],
    ids=["no_linked_user", "staff_linked", "mixed_roles", "inactive"],
)
def test_a_impersonation_token_without_a_salesperson_user_has_null(roles, kw):
    with blank_session() as db:
        _, contact = _chain(db)
        admin = _user(db, ["admin"])
        if roles:
            _user(db, roles, contact=contact, **kw)
        body = _me(db, _impersonation_token(db, admin.id, contact.id))
        assert "crm_user_id" in body
        assert body["crm_user_id"] is None


def test_a_users_me_returns_the_linked_contact_id():
    with blank_session() as db:
        _, contact = _chain(db)
        sp = _user(db, ["salesperson"], contact=contact)
        res = _get(db, "/api/v1/user-management/users/me", actor_id=sp.id)
        assert res.status_code == 200, res.text
        assert res.json()["respond_contact_id"] == contact.id
