"""PORTAL-IMPERSONATION-ISOLATE: a view-as applies only to the requests that carry it.

The admin's browser holds ONE staff session token for every tab. Tab A (the one that started the
view-as) sends ``X-Impersonate-User-Id``; tab B sends the same token without it. These tests pin,
with a real ``user_sessions`` token and the real ``get_current_user`` / ``require_permission`` /
``ImpersonationEndedMiddleware``, that:

- tab B is the admin with full access while tab A is the salesperson (PII-1, PII-6);
- ending the view-as in A leaves B untouched and needs no re-login (PII-3, PII-4);
- a non-admin cannot start one and their header is ignored (PII-5);
- the audit actor is the target with the admin as real user (PII-7).

Postgres only (scratch schema, everything rolled back).
"""
from __future__ import annotations

import uuid

from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from app.api.v1.user_management import impersonation as impersonation_routes
from app.database import get_db
from app.dependencies import IMPERSONATE_HEADER, get_current_user, require_permission
from app.middleware.impersonation_ended_middleware import (
    IMPERSONATION_ENDED_HEADER,
    ImpersonationEndedMiddleware,
)
from app.models.impersonation import ImpersonationSession
from app.models.user import User, UserPermission, UserRole, UserRoleAssignment, UserRolePermission
from app.services.user_session_service import mint_session
from tests._pg_fixture import blank_session, unique_code

STAFF_PERM = "zzt.isolation.products.view"
IMP = "/impersonation"


def _role(db, slug, perms=()):
    role = db.query(UserRole).filter(UserRole.slug == slug).first()
    if role is None:
        role = UserRole(id=str(uuid.uuid4()), slug=slug, name=slug, is_protected=False, is_default=False)
        db.add(role)
        db.flush()
    for p_slug in perms:
        perm = db.query(UserPermission).filter(UserPermission.slug == p_slug).first()
        if perm is None:
            perm = UserPermission(id=str(uuid.uuid4()), slug=p_slug, name=p_slug)
            db.add(perm)
            db.flush()
        db.add(UserRolePermission(role_id=role.id, permission_id=perm.id))
        db.flush()
    return role


def _user(db, role):
    u = User(
        id=str(uuid.uuid4()),
        email=f"{unique_code('pii')}@x.test".lower(),
        name="ZZT PII User",
        status="ACTIVE",
    )
    db.add(u)
    db.flush()
    db.add(UserRoleAssignment(user_id=u.id, role_id=role.id))
    db.commit()
    return u


def _app(db):
    probe = FastAPI()
    probe.add_middleware(ImpersonationEndedMiddleware)
    probe.include_router(impersonation_routes.router, prefix=IMP)

    @probe.get("/probe/me")
    def me(request: Request, user: dict = Depends(get_current_user)):
        actor = getattr(request.state, "audit_actor", None)
        return {
            "id": user["id"],
            "real_id": request.state.real_user["id"],
            "actor_user_id": getattr(actor, "user_id", None),
            "actor_real_user_id": getattr(actor, "real_user_id", None),
            "actor_auth_method": getattr(actor, "auth_method", None),
        }

    @probe.get("/probe/products")
    def products(user: dict = Depends(require_permission(STAFF_PERM))):
        return {"ok": True}

    def _db():
        yield db

    probe.dependency_overrides[get_db] = _db
    return TestClient(probe)


def _world(db):
    admin = _user(db, _role(db, "admin"))
    sales = _user(db, _role(db, "salesperson"))
    staff = _user(db, _role(db, "zzt_pii_staff", perms=[STAFF_PERM]))
    return admin, sales, staff


def _bearer(db, user):
    return {"Authorization": f"Bearer {mint_session(db, str(user.id)).token}"}


def _tab_a(token_headers, target_id):
    return {**token_headers, IMPERSONATE_HEADER: str(target_id)}


def test_tab_b_stays_the_admin_while_tab_a_views_as_the_salesperson():
    with blank_session() as db:
        admin, sales, _ = _world(db)
        tc = _app(db)
        token = _bearer(db, admin)
        assert tc.post(f"{IMP}/start", json={"target_user_id": sales.id}, headers=token).status_code == 200

        a = tc.get("/probe/me", headers=_tab_a(token, sales.id))
        assert a.status_code == 200
        assert a.json()["id"] == str(sales.id)
        assert a.json()["real_id"] == str(admin.id)
        assert a.json()["actor_user_id"] == str(sales.id)
        assert a.json()["actor_real_user_id"] == str(admin.id)
        assert a.json()["actor_auth_method"] == "impersonation"

        b = tc.get("/probe/me", headers=token)
        assert b.status_code == 200
        assert b.json()["id"] == str(admin.id)
        assert b.json()["actor_user_id"] == str(admin.id)
        assert b.json()["actor_auth_method"] != "impersonation"
        assert IMPERSONATION_ENDED_HEADER not in b.headers


def test_staff_only_api_refuses_tab_a_and_serves_tab_b():
    with blank_session() as db:
        admin, sales, _ = _world(db)
        tc = _app(db)
        token = _bearer(db, admin)
        tc.post(f"{IMP}/start", json={"target_user_id": sales.id}, headers=token)

        assert tc.get("/probe/products", headers=_tab_a(token, sales.id)).status_code == 403
        assert tc.get("/probe/products", headers=token).status_code == 200


def test_ending_in_tab_a_leaves_tab_b_untouched_and_needs_no_relogin():
    with blank_session() as db:
        admin, sales, _ = _world(db)
        tc = _app(db)
        token = _bearer(db, admin)
        tc.post(f"{IMP}/start", json={"target_user_id": sales.id}, headers=token)

        # Exit is sent from tab A: the header does not let the view-as end itself as the target.
        stop = tc.post(f"{IMP}/stop", headers=_tab_a(token, sales.id))
        assert stop.status_code == 200 and stop.json()["ended"] is True

        # Tab A's next call is the admin again, told the view-as is over; same token, no 401.
        a = tc.get("/probe/me", headers=_tab_a(token, sales.id))
        assert a.status_code == 200
        assert a.json()["id"] == str(admin.id)
        assert a.headers.get(IMPERSONATION_ENDED_HEADER) == "1"

        b = tc.get("/probe/products", headers=token)
        assert b.status_code == 200
        assert IMPERSONATION_ENDED_HEADER not in b.headers


def test_starting_a_view_as_does_not_sign_the_admin_out():
    with blank_session() as db:
        admin, sales, _ = _world(db)
        tc = _app(db)
        token = _bearer(db, admin)
        assert tc.get("/probe/me", headers=token).status_code == 200
        tc.post(f"{IMP}/start", json={"target_user_id": sales.id}, headers=token)
        assert tc.get("/probe/me", headers=token).json()["id"] == str(admin.id)


def test_a_non_admin_cannot_start_and_their_header_is_ignored():
    with blank_session() as db:
        _, sales, staff = _world(db)
        tc = _app(db)
        token = _bearer(db, staff)
        assert tc.post(f"{IMP}/start", json={"target_user_id": sales.id}, headers=token).status_code == 403
        assert (
            db.query(ImpersonationSession)
            .filter(ImpersonationSession.admin_user_id == str(staff.id))
            .count()
            == 0
        )
        r = tc.get("/probe/me", headers=_tab_a(token, sales.id))
        assert r.status_code == 200
        assert r.json()["id"] == str(staff.id)
        assert r.headers.get(IMPERSONATION_ENDED_HEADER) == "1"


def test_header_without_an_open_row_is_ignored_even_for_an_admin():
    with blank_session() as db:
        admin, sales, _ = _world(db)
        tc = _app(db)
        token = _bearer(db, admin)
        r = tc.get("/probe/me", headers=_tab_a(token, sales.id))
        assert r.json()["id"] == str(admin.id)
        assert r.headers.get(IMPERSONATION_ENDED_HEADER) == "1"


def test_exit_in_a_stale_tab_does_not_end_another_tabs_newer_view_as():
    """Tab A viewed as X; tab C then started Y (which ends X). Exit in A names A's own session,
    so it must not end C's view-as of Y."""
    with blank_session() as db:
        admin, sales, _ = _world(db)
        other = _user(db, _role(db, "salesperson"))
        tc = _app(db)
        token = _bearer(db, admin)
        a_session = tc.post(f"{IMP}/start", json={"target_user_id": sales.id}, headers=token).json()["session_id"]
        tc.post(f"{IMP}/start", json={"target_user_id": other.id}, headers=token)

        stop = tc.post(f"{IMP}/stop", json={"session_id": a_session}, headers=_tab_a(token, sales.id))
        assert stop.status_code == 200 and stop.json()["ended"] is False

        c = tc.get("/probe/me", headers=_tab_a(token, other.id))
        assert c.json()["id"] == str(other.id)
        assert IMPERSONATION_ENDED_HEADER not in c.headers


def test_exit_naming_the_open_session_ends_it():
    with blank_session() as db:
        admin, sales, _ = _world(db)
        tc = _app(db)
        token = _bearer(db, admin)
        sid = tc.post(f"{IMP}/start", json={"target_user_id": sales.id}, headers=token).json()["session_id"]
        stop = tc.post(f"{IMP}/stop", json={"session_id": sid}, headers=_tab_a(token, sales.id))
        assert stop.json() == {"ended": True, "session_id": sid}
