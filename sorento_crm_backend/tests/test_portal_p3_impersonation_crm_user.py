"""PORTAL-P3-ROLE-MENU round 6, B1 (P3-23, P3-27): the contact-impersonation start response carries
`crm_user_id`: the linked user's id when that user is an active, untrashed salesperson, else null.
Postgres only, every row seeded here."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.dependencies import get_current_user, get_current_user_or_api_key, get_real_user
from app.main import app
from tests._pg_fixture import blank_session
from tests.test_portal_p3_role_menu import _chain, _user

START = "/api/v1/user-management/contact-impersonation/start"


def _start(db, admin_id, contact_id):
    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    for dep in (get_real_user, get_current_user, get_current_user_or_api_key):
        app.dependency_overrides[dep] = lambda: {"id": admin_id}
    try:
        with TestClient(app) as tc:
            return tc.post(START, json={"contact_id": contact_id})
    finally:
        app.dependency_overrides.pop(get_db, None)
        for dep in (get_real_user, get_current_user, get_current_user_or_api_key):
            app.dependency_overrides.pop(dep, None)


def test_b1_linked_salesperson_user_id_is_returned():
    with blank_session() as db:
        _, contact = _chain(db)
        admin = _user(db, ["admin"])
        sp = _user(db, ["salesperson"], contact=contact)
        res = _start(db, admin.id, contact.id)
        assert res.status_code == 200, res.text
        assert res.json()["crm_user_id"] == sp.id
        assert "impersonation=1" in res.json()["portal_url"]


def test_b1_salesperson_with_portal_user_role_is_returned():
    with blank_session() as db:
        _, contact = _chain(db)
        admin = _user(db, ["admin"])
        sp = _user(db, ["salesperson", "portal_user"], contact=contact)
        res = _start(db, admin.id, contact.id)
        assert res.status_code == 200, res.text
        assert res.json()["crm_user_id"] == sp.id


def test_b1_no_linked_user_is_null_and_start_still_works():
    with blank_session() as db:
        _, contact = _chain(db)
        admin = _user(db, ["admin"])
        res = _start(db, admin.id, contact.id)
        assert res.status_code == 200, res.text
        assert "crm_user_id" in res.json()
        assert res.json()["crm_user_id"] is None


@pytest.mark.parametrize(
    "roles,kw",
    [
        (["salesperson", "purchasing"], {}),
        (["purchasing"], {}),
        (["salesperson"], {"status": "INACTIVE"}),
        (["salesperson"], {"trashed": True}),
    ],
    ids=["mixed_roles", "staff_only", "inactive", "trashed"],
)
def test_b1_linked_user_that_is_not_an_active_salesperson_is_null(roles, kw):
    with blank_session() as db:
        _, contact = _chain(db)
        admin = _user(db, ["admin"])
        _user(db, roles, contact=contact, **kw)
        res = _start(db, admin.id, contact.id)
        assert res.status_code == 200, res.text
        assert "crm_user_id" in res.json()
        assert res.json()["crm_user_id"] is None
