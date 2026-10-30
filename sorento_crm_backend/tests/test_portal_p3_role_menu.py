"""PORTAL-P3-ROLE-MENU slice 1, backend half: P3-03 .. P3-06.

`home_path_for_user` and `GET /user-management/users/me` (a manual dict builder, so asserted
through HTTP: `response_model` drops undeclared fields). Postgres only, every row seeded here.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models.access import RespondContact
from app.models.price_tag import ContactPortalFormOverride
from app.models.respond_workspace import RespondWorkspace
from app.models.user import (
    User,
    UserPermission,
    UserRole,
    UserRoleAssignment,
    UserRolePermission,
)
from tests._pg_fixture import blank_session, unique_code

ME = "/api/v1/user-management/users/me"


def _digits() -> str:
    return "601" + f"{uuid.uuid4().int % 10**8:08d}"


def _chain(db):
    ws = RespondWorkspace(
        id=str(uuid.uuid4()),
        space_id=f"sp_{uuid.uuid4().hex[:8]}",
        name="ZZT WS",
        api_key_ciphertext="test-cipher",
    )
    db.add(ws)
    db.flush()
    contact = RespondContact(
        id=str(uuid.uuid4()), phone_number=_digits(), name="ZZT Contact", workspace_id=ws.id
    )
    db.add(contact)
    db.flush()
    return ws, contact


def _user(db, roles, *, contact=None, status="ACTIVE", trashed=False, perm=None):
    """roles: slugs. perm: a permission slug given to every role named in `perm_roles` (see below)."""
    u = User(
        id=str(uuid.uuid4()),
        email=f"{unique_code('p3')}@x.com".lower(),
        name="ZZT P3 User",
        status=status,
        is_trashed=trashed,
        contact_number=contact.phone_number if contact else None,
        respond_contact_id=contact.id if contact else None,
    )
    db.add(u)
    db.flush()
    for slug in roles:
        role = db.query(UserRole).filter(UserRole.slug == slug).first()
        if role is None:
            role = UserRole(
                id=str(uuid.uuid4()), slug=slug, name=slug, is_protected=False, is_default=False
            )
            db.add(role)
            db.flush()
            if slug not in {"salesperson", "portal_user"}:
                p = UserPermission(id=str(uuid.uuid4()), slug=f"zzt.{slug}.view", name=f"zzt.{slug}.view")
                db.add(p)
                db.flush()
                db.add(UserRolePermission(role_id=role.id, permission_id=p.id))
        db.add(UserRoleAssignment(user_id=u.id, role_id=role.id))
    db.commit()
    return u


def _portal_token(db, ws, contact) -> str:
    from unittest.mock import patch  # noqa: F401
    from app.services.portal_service import PortalService

    captured: dict = {}

    def _fake_task(otp_id, identifier, message_text, otp_code, space_id):
        captured["code"] = otp_code
        return {"status": "success"}

    PortalService(db).create_and_dispatch_otp(
        contact, ws.space_id, "code {code}", _fake_task, dispatch_inline=True
    )
    return captured["code"]


class _client_ctx:
    def __init__(self, db, actor_id=None):
        self.db, self.actor_id = db, actor_id

    def __enter__(self):
        from app.dependencies import get_current_user, get_current_user_or_api_key

        def _override_db():
            yield self.db

        app.dependency_overrides[get_db] = _override_db
        if self.actor_id:
            app.dependency_overrides[get_current_user] = lambda: {"id": self.actor_id}
            app.dependency_overrides[get_current_user_or_api_key] = lambda: {"id": self.actor_id}
        self._tc = TestClient(app)
        return self._tc.__enter__()

    def __exit__(self, *exc):
        from app.dependencies import get_current_user, get_current_user_or_api_key

        self._tc.__exit__(*exc)
        for dep in (get_db, get_current_user, get_current_user_or_api_key):
            app.dependency_overrides.pop(dep, None)


def _home(db, user) -> str:
    from app.services.phone_signin_service import home_path_for_user

    return home_path_for_user(db, user)


def _slug(db, contact) -> str:
    from app.services.portal_service import PortalService

    s = PortalService(db).get_or_create_slug(contact)
    db.commit()
    return s


# --------------------------------------------------------------------------- #
# P3-05: salesperson lands on /my-requests                                     #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("roles", [["salesperson"], ["salesperson", "portal_user"]])
def test_p3_05_salesperson_home_is_my_requests(roles):
    with blank_session() as db:
        _, contact = _chain(db)
        user = _user(db, roles, contact=contact)
        assert _home(db, user) == "/my-requests"


# --------------------------------------------------------------------------- #
# P3-06: everyone else unchanged (green pins)                                  #
# --------------------------------------------------------------------------- #
def test_p3_06_mixed_salesperson_plus_staff_role_keeps_todays_home():
    with blank_session() as db:
        _, contact = _chain(db)
        slug = _slug(db, contact)
        user = _user(db, ["salesperson", "purchasing"], contact=contact)
        assert _home(db, user) == f"/portal/c/{slug}"


@pytest.mark.parametrize("role", ["admin", "superadmin"])
def test_p3_06_admin_and_superadmin_land_on_crm_home(role):
    with blank_session() as db:
        user = _user(db, [role])
        assert _home(db, user) == "/"


def test_p3_06_staff_with_permission_lands_on_crm_home():
    with blank_session() as db:
        user = _user(db, ["purchasing"])
        assert _home(db, user) == "/"


def test_p3_06_portal_user_only_with_contact_lands_on_portal_home():
    with blank_session() as db:
        _, contact = _chain(db)
        slug = _slug(db, contact)
        user = _user(db, ["portal_user"], contact=contact)
        assert _home(db, user) == f"/portal/c/{slug}"


def test_p3_06_user_without_contact_lands_on_crm_root():
    with blank_session() as db:
        user = _user(db, ["salesperson"])
        assert _home(db, user) == "/"


@pytest.mark.parametrize("kw", [{"status": "INACTIVE"}, {"trashed": True}])
def test_p3_05_inactive_or_trashed_salesperson_is_not_sent_to_my_requests(kw):
    with blank_session() as db:
        _, contact = _chain(db)
        user = _user(db, ["salesperson"], contact=contact, **kw)
        assert _home(db, user) != "/my-requests"


# --------------------------------------------------------------------------- #
# P3-03 / P3-04: GET /users/me carries `salesperson`                           #
# --------------------------------------------------------------------------- #
def test_p3_03_me_carries_portal_kinds_equal_to_portal_me_and_slug():
    with blank_session() as db:
        ws, contact = _chain(db)
        slug = _slug(db, contact)
        # non-default visibility so a pass proves the same service, not a coincidence
        db.add(ContactPortalFormOverride(contact_id=contact.id, form_type="sample_request", is_enabled=True))
        db.add(ContactPortalFormOverride(contact_id=contact.id, form_type="purchase_request", is_enabled=False))
        user = _user(db, ["salesperson", "portal_user"], contact=contact)
        code = _portal_token(db, ws, contact)
        with _client_ctx(db, actor_id=user.id) as client:
            v = client.post(
                "/api/v1/public/portal/verify-otp",
                json={"contact_id": contact.id, "space_id": ws.space_id, "code": code},
            )
            assert v.status_code == 200, v.text
            portal = client.get("/api/v1/public/portal/me", headers={"X-Portal-Token": v.json()["token"]})
            assert portal.status_code == 200, portal.text
            r = client.get(ME)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "salesperson" in body, sorted(body)
        assert body["salesperson"] is not None
        assert body["salesperson"]["portal_slug"] == slug
        assert body["salesperson"]["portal_kinds"] == portal.json()["visible_form_types"]
        assert "sample_request" in body["salesperson"]["portal_kinds"]
        assert "purchase_request" not in body["salesperson"]["portal_kinds"]


@pytest.mark.parametrize(
    "roles,with_contact,kw",
    [
        (["purchasing"], False, {}),
        (["admin"], False, {}),
        (["superadmin"], True, {}),
        (["salesperson", "purchasing"], True, {}),
        (["salesperson"], False, {}),
        (["portal_user"], True, {}),
    ],
)
def test_p3_04_me_salesperson_is_null_for_everyone_else(roles, with_contact, kw):
    with blank_session() as db:
        _, contact = _chain(db)
        user = _user(db, roles, contact=contact if with_contact else None, **kw)
        with _client_ctx(db, actor_id=user.id) as client:
            r = client.get(ME)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "salesperson" in body, sorted(body)
        assert body["salesperson"] is None
