"""S3 identity red tests (#1280): AC-56, AC-57, AC-58 - creating or linking a user

never sends anything, and sending an invitation is one deliberate, confirmed button.

Written against `documentation/plans/identity/s3-contract.md` sections 1.6, 1.8 and 3,
BEFORE any implementation exists. `app.services.respond_messaging_service.send_text_or_template`
and `app.services.queue_service.enqueue_job` are monkeypatched to fail the test if called,
so a regression that starts sending a WhatsApp message is caught even though none of
these actions is expected to reach that seam today.

Postgres only (`tests/_pg_fixture.py`), `blank_session()` per test, every test seeds its
own chain.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import get_db
from app.main import app
from app.models.access import RespondContact
from app.models.email_outbox import EmailOutbox
from app.models.notification import Notification
from app.models.user import User, UserRole, UserRoleAssignment
from tests._pg_fixture import blank_session, unique_code


def _phone() -> str:
    return f"+6011{uuid.uuid4().int % 10_000_000:07d}"


def _msisdn(raw: str) -> str:
    from app.services.phone_utils import normalize_msisdn

    return normalize_msisdn(raw)


def _seed_contact(db: Session, *, phone: str | None = None, name: str = "ZZT Contact") -> RespondContact:
    contact = RespondContact(id=str(uuid.uuid4()), phone_number=phone or _msisdn(_phone()), name=name)
    db.add(contact)
    db.flush()
    return contact


def _seed_admin_user(db: Session) -> User:
    role = UserRole(id=str(uuid.uuid4()), slug="admin", name="Admin", is_protected=False, is_default=False)
    db.add(role)
    db.flush()
    admin = User(id=str(uuid.uuid4()), email=f"{unique_code('admin')}@example.com".lower(), name="ZZT Admin", status="ACTIVE")
    db.add(admin)
    db.flush()
    db.add(UserRoleAssignment(user_id=admin.id, role_id=role.id))
    db.commit()
    return admin


def _seed_user(db: Session, *, name: str = "ZZT User", email: str | None = None, phone: str | None = None) -> User:
    if email is None and phone is None:
        email = f"{unique_code('u')}@x.com".lower()
    user = User(id=str(uuid.uuid4()), email=email, name=name, status="ACTIVE", contact_number=phone)
    db.add(user)
    db.flush()
    return user


@pytest.fixture()
def outbox_client(monkeypatch):
    """A TestClient over the real app as an admin, with the two send seams blocked -
    any call fails the test with a clear message instead of silently sending."""
    from app.dependencies import get_current_user

    def _blocked_send(*args, **kwargs):
        raise AssertionError("send_text_or_template must NOT be called by create/link/unlink/edit")

    def _blocked_enqueue(*args, **kwargs):
        raise AssertionError("enqueue_job must NOT be called by create/link/unlink/edit")

    monkeypatch.setattr("app.services.respond_messaging_service.send_text_or_template", _blocked_send)
    monkeypatch.setattr("app.services.queue_service.enqueue_job", _blocked_enqueue)

    with blank_session() as db:
        admin = _seed_admin_user(db)

        def _override_user():
            return {"id": admin.id, "email": admin.email, "name": admin.name, "status": "ACTIVE"}

        def _override_db():
            yield db

        app.dependency_overrides[get_current_user] = _override_user
        app.dependency_overrides[get_db] = _override_db
        with TestClient(app) as client:
            yield client, db, admin
        app.dependency_overrides.clear()


def _outbox_counts(db: Session) -> tuple[int, int]:
    return db.query(EmailOutbox).count(), db.query(Notification).count()


# --------------------------------------------------------------------------- #
# AC-56: create, link, unlink, role/company edits never send anything          #
# --------------------------------------------------------------------------- #
def test_ac56_create_with_email_only_sends_nothing(outbox_client):
    client, db, _admin = outbox_client
    before = _outbox_counts(db)

    resp = client.post(
        "/api/v1/user-management/users/",
        json={"email": f"{unique_code('e56')}@x.com".lower(), "name": "Email Only 56"},
    )
    assert resp.status_code == 201, resp.text
    assert _outbox_counts(db) == before


def test_ac56_create_with_phone_only_sends_nothing(outbox_client):
    client, db, _admin = outbox_client
    before = _outbox_counts(db)

    resp = client.post(
        "/api/v1/user-management/users/",
        json={"name": "Phone Only 56", "contact_number": _msisdn(_phone())},
    )
    assert resp.status_code == 201, resp.text
    assert _outbox_counts(db) == before


def test_ac56_create_with_both_sends_nothing(outbox_client):
    client, db, _admin = outbox_client
    before = _outbox_counts(db)

    resp = client.post(
        "/api/v1/user-management/users/",
        json={
            "email": f"{unique_code('b56')}@x.com".lower(),
            "name": "Both 56",
            "contact_number": _msisdn(_phone()),
        },
    )
    assert resp.status_code == 201, resp.text
    assert _outbox_counts(db) == before


def test_ac56_link_contact_sends_nothing(outbox_client):
    client, db, _admin = outbox_client
    contact = _seed_contact(db, name="Link Nothing Contact")
    target = _seed_user(db, name="Link Nothing Target")
    db.commit()
    before = _outbox_counts(db)

    resp = client.put(f"/api/v1/user-management/users/{target.id}", json={"respond_contact_id": contact.id})
    assert resp.status_code == 200, resp.text
    assert _outbox_counts(db) == before


def test_ac56_unlink_contact_sends_nothing(outbox_client):
    client, db, _admin = outbox_client
    contact = _seed_contact(db, name="Unlink Nothing Contact")
    target = _seed_user(db, name="Unlink Nothing Target")
    target.respond_contact_id = contact.id
    db.commit()
    before = _outbox_counts(db)

    resp = client.put(f"/api/v1/user-management/users/{target.id}", json={"respond_contact_id": None})
    assert resp.status_code == 200, resp.text
    assert _outbox_counts(db) == before


def test_ac56_put_roles_sends_nothing(outbox_client):
    client, db, _admin = outbox_client
    role = UserRole(id=str(uuid.uuid4()), slug=unique_code("r56").lower(), name="ZZT Role 56", is_protected=False, is_default=False)
    db.add(role)
    target = _seed_user(db, name="Roles Nothing Target")
    db.commit()
    before = _outbox_counts(db)

    resp = client.put(f"/api/v1/user-management/users/{target.id}/roles", json={"role_ids": [role.id]})
    assert resp.status_code == 200, resp.text
    assert _outbox_counts(db) == before


def test_ac56_put_companies_sends_nothing(outbox_client):
    from app.models.company import Company

    client, db, _admin = outbox_client
    company = Company(id=str(uuid.uuid4()), name="ZZT Co 56", code=unique_code("C56")[:20])
    db.add(company)
    target = _seed_user(db, name="Companies Nothing Target")
    db.commit()
    before = _outbox_counts(db)

    resp = client.put(f"/api/v1/user-management/users/{target.id}/companies", json={"company_ids": [company.id]})
    assert resp.status_code == 200, resp.text
    assert _outbox_counts(db) == before


def test_ac56_first_email_on_phone_only_user_sends_nothing(outbox_client):
    client, db, _admin = outbox_client
    phone_only = _seed_user(db, name="First Email 56", email=None, phone=_msisdn(_phone()))
    db.commit()
    before = _outbox_counts(db)

    resp = client.put(
        f"/api/v1/user-management/users/{phone_only.id}",
        json={"email": f"{unique_code('first56')}@x.com".lower()},
    )
    assert resp.status_code == 200, resp.text
    assert _outbox_counts(db) == before


# --------------------------------------------------------------------------- #
# AC-57: bulk resend skips users with no email and reports how many            #
# --------------------------------------------------------------------------- #
def test_ac57_bulk_resend_invite_skips_no_email_user_and_reports_skipped():
    from app.dependencies import get_current_user

    with blank_session() as db:
        admin = _seed_admin_user(db)
        with_email = _seed_user(db, name="Has Email 57", email=f"{unique_code('has57')}@x.com".lower())
        no_email = _seed_user(db, name="No Email 57", email=None, phone=_msisdn(_phone()))
        db.commit()

        def _override_user():
            return {"id": admin.id, "email": admin.email, "name": admin.name, "status": "ACTIVE"}

        def _override_db():
            yield db

        app.dependency_overrides[get_current_user] = _override_user
        app.dependency_overrides[get_db] = _override_db
        try:
            with TestClient(app) as client:
                resp = client.post(
                    "/api/v1/user-management/users/bulk",
                    json={"user_ids": [with_email.id, no_email.id], "action": "resend_invite"},
                )
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body.get("skipped") == 1, body
        assert "1 skipped (no email)" in (body.get("message") or ""), body


# --------------------------------------------------------------------------- #
# AC-58: the create-and-email path is gone                                     #
# --------------------------------------------------------------------------- #
def test_ac58_post_users_invite_does_not_create_a_user_or_answer_201(outbox_client):
    client, db, _admin = outbox_client
    before = db.query(User).count()

    resp = client.post(
        "/api/v1/user-management/users/invite",
        json={"email": f"{unique_code('inv58')}@x.com".lower(), "name": "Invite Gone"},
    )

    assert resp.status_code != 201, resp.text
    assert db.query(User).count() == before, "POST /users/invite must create no user"
