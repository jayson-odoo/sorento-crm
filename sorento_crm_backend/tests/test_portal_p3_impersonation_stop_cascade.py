"""PORTAL-P3-ROLE-MENU round 8, S1: stopping a CRM impersonation of user X also ends the admin's
ACTIVE contact-impersonation session for X's linked contact and revokes its portal token. A session
for an unrelated contact stays active; a staff target without a linked contact behaves as today.
Postgres only, every row seeded here."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.database import get_db
from app.dependencies import get_current_user, get_current_user_or_api_key, get_real_user
from app.main import app
from app.models.impersonation import ContactImpersonationSession, ImpersonationSession
from app.models.portal import PortalToken
from tests._pg_fixture import blank_session
from tests.test_portal_p3_impersonation_crm_user import _start
from tests.test_portal_p3_role_menu import _chain, _user

STOP = "/api/v1/user-management/impersonation/stop"
DEPS = (get_real_user, get_current_user, get_current_user_or_api_key)


def _stop(db, admin_id):
    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    for dep in DEPS:
        app.dependency_overrides[dep] = lambda: {"id": admin_id}
    try:
        with TestClient(app) as tc:
            return tc.post(STOP)
    finally:
        app.dependency_overrides.pop(get_db, None)
        for dep in DEPS:
            app.dependency_overrides.pop(dep, None)


def _crm_session(db, admin_id, target_id):
    row = ImpersonationSession(admin_user_id=admin_id, target_user_id=target_id)
    db.add(row)
    db.commit()
    return row


def _contact_session(db, admin_id, contact_id):
    res = _start(db, admin_id, contact_id)
    assert res.status_code == 200, res.text
    db.expire_all()
    return (
        db.query(ContactImpersonationSession)
        .filter(ContactImpersonationSession.id == res.json()["session_id"])
        .one()
    )


def _token(db, session_row):
    return db.query(PortalToken).filter(PortalToken.id == session_row.portal_token_id).one()


def test_s1_stop_ends_the_linked_contact_session_and_revokes_its_token():
    with blank_session() as db:
        _, contact = _chain(db)
        admin = _user(db, ["admin"])
        target = _user(db, ["salesperson"], contact=contact)
        csess = _contact_session(db, admin.id, contact.id)
        _crm_session(db, admin.id, target.id)
        assert _stop(db, admin.id).json()["ended"] is True
        db.expire_all()
        csess = db.query(ContactImpersonationSession).filter_by(id=csess.id).one()
        assert csess.ended_at is not None
        assert _token(db, csess).revoked_at is not None


def test_s1_a_session_for_an_unrelated_contact_stays_active():
    with blank_session() as db:
        _, contact = _chain(db)
        _, other = _chain(db)
        admin = _user(db, ["admin"])
        target = _user(db, ["salesperson"], contact=contact)
        csess = _contact_session(db, admin.id, other.id)
        _crm_session(db, admin.id, target.id)
        assert _stop(db, admin.id).json()["ended"] is True
        db.expire_all()
        csess = db.query(ContactImpersonationSession).filter_by(id=csess.id).one()
        assert csess.ended_at is None
        assert _token(db, csess).revoked_at is None


def test_s1_staff_target_without_a_linked_contact_behaves_as_today():
    with blank_session() as db:
        _, other = _chain(db)
        admin = _user(db, ["admin"])
        target = _user(db, ["purchasing"])
        csess = _contact_session(db, admin.id, other.id)
        crm = _crm_session(db, admin.id, target.id)
        res = _stop(db, admin.id)
        assert res.status_code == 200 and res.json()["ended"] is True
        db.expire_all()
        assert db.query(ImpersonationSession).filter_by(id=crm.id).one().ended_at is not None
        csess = db.query(ContactImpersonationSession).filter_by(id=csess.id).one()
        assert csess.ended_at is None
        assert _token(db, csess).revoked_at is None
