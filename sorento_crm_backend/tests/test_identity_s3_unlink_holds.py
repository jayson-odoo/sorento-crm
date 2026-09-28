"""Identity S3 fix round 2, B1 (#1280): an owner's Unlink holds, and nothing
links a user to a WhatsApp contact by itself.

Reviewer pass at 6a7f0bcd, Blocking B1: `respond_link_service.resolve_user_respond_contact`
fell back to a unique phone match when `users.respond_contact_id` was null and wrote
that match back onto the user. So the owner unlinked a contact whose phone equals the
user's (the normal case, and exactly the S0 auto-links plan 6.5 says the owner rejects
"with the S3 Unlink"), and the next notification, SLA summary, banner or WhatsApp task
for that user re-linked it and sent to it anyway, with no audit row.

After the fix the link is the only way from a user to a contact (plan 6.5: the exact
phone link is made once, by the S0 migration; AC-43: nothing is linked by itself;
owner ruling Q3/Q4 26 Sep 2026 23:45 MYT: "it should be controlled by me"). Every
caller below honours it: no link, no contact.

One test per caller path the reviewer named: the resolver itself (which the SLA daily
summary calls directly), the notification channel gate, the WhatsApp delivery task and
the banner phone. Plus the AC-44 Respond.io-sync source the reviewer found untested.

Postgres only (`tests/_pg_fixture.py`), every test seeds its own chain.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import get_db
from app.main import app
from app.models.access import RespondContact
from app.models.user import User, UserRole, UserRoleAssignment
from tests._pg_fixture import blank_session, unique_code


def _msisdn() -> str:
    from app.services.phone_utils import normalize_msisdn

    return normalize_msisdn(f"+6011{uuid.uuid4().int % 10_000_000:07d}")


def _seed_contact(db: Session, phone: str, *, name: str = "ZZT B1 Contact") -> RespondContact:
    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=phone,
        name=name,
        respond_io_id=f"io-{uuid.uuid4().hex[:8]}",
        session_vars={},
    )
    db.add(contact)
    db.flush()
    return contact


def _seed_user(db: Session, phone: str, *, linked_contact_id: str | None = None) -> User:
    user = User(
        id=str(uuid.uuid4()),
        email=f"{unique_code('b1')}@x.com".lower(),
        name="ZZT B1 User",
        status="ACTIVE",
        contact_number=phone,
        respond_contact_id=linked_contact_id,
        notify_whatsapp=True,
        notify_whatsapp_summary=True,
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture()
def api_client():
    """Admin principal over a `blank_session`, as in test_identity_s3_create_link.py."""
    from app.dependencies import get_current_user

    with blank_session() as db:
        role = UserRole(id=str(uuid.uuid4()), slug="admin", name="Admin")
        admin = User(
            id=str(uuid.uuid4()),
            email=f"{unique_code('admin')}@example.com".lower(),
            name="ZZT Admin",
            status="ACTIVE",
        )
        db.add_all([role, admin])
        db.flush()
        db.add(UserRoleAssignment(user_id=admin.id, role_id=role.id))
        db.commit()

        app.dependency_overrides[get_current_user] = lambda: {
            "id": admin.id,
            "email": admin.email,
            "name": admin.name,
            "status": "ACTIVE",
        }

        def _override_db():
            yield db

        app.dependency_overrides[get_db] = _override_db
        with TestClient(app) as client:
            yield client, db
        app.dependency_overrides.clear()


def _linked_then_unlinked(client, db: Session) -> tuple[User, RespondContact]:
    """A user linked to the one contact with the same phone (an S0 auto-link),
    then unlinked by the owner through the S3 route."""
    phone = _msisdn()
    contact = _seed_contact(db, phone)
    user = _seed_user(db, phone, linked_contact_id=contact.id)

    resp = client.put(f"/api/v1/user-management/users/{user.id}", json={"respond_contact_id": None})
    assert resp.status_code == 200, resp.text
    db.refresh(user)
    assert user.respond_contact_id is None
    return user, contact


# --------------------------------------------------------------------------- #
# The resolver (the SLA daily summary calls `resolve_user_respond_io_id`       #
# directly, so this is its path too)                                           #
# --------------------------------------------------------------------------- #
def test_b1_after_unlink_resolver_returns_nothing_and_does_not_relink(api_client):
    from app.services.respond_link_service import (
        resolve_user_respond_contact,
        resolve_user_respond_io_id,
    )

    client, db = api_client
    user, _contact = _linked_then_unlinked(client, db)

    assert resolve_user_respond_io_id(db, user) is None
    assert resolve_user_respond_contact(db, user) is None
    db.refresh(user)
    assert user.respond_contact_id is None, "the owner's Unlink must hold"


def test_b1_never_linked_user_is_not_linked_by_a_phone_match():
    """AC-43: a user whose phone happens to equal one contact's is NOT linked (or
    sent to) by a runtime lookup; the owner links it, or the S0 migration did."""
    from app.services.respond_link_service import resolve_user_respond_io_id

    with blank_session() as db:
        phone = _msisdn()
        _seed_contact(db, phone)
        user = _seed_user(db, phone)

        assert resolve_user_respond_io_id(db, user) is None
        db.refresh(user)
        assert user.respond_contact_id is None


def test_b1_explicit_link_still_resolves():
    """Guard: honouring the link does not stop a linked user being reached."""
    from app.services.respond_link_service import resolve_user_respond_io_id

    with blank_session() as db:
        phone = _msisdn()
        contact = _seed_contact(db, phone)
        user = _seed_user(db, _msisdn(), linked_contact_id=contact.id)

        assert resolve_user_respond_io_id(db, user) == contact.respond_io_id


# --------------------------------------------------------------------------- #
# Notification channel gate (`NotificationService.create_with_channel_preferences`) #
# --------------------------------------------------------------------------- #
def test_b1_after_unlink_notification_creates_no_whatsapp_delivery(api_client):
    from app.models.notification import NotificationDelivery
    from app.services.notification_service import NotificationService

    client, db = api_client
    user, _contact = _linked_then_unlinked(client, db)

    with patch("app.services.queue_service.enqueue_job"):
        notification = NotificationService(db).create_with_channel_preferences(
            user_id=user.id,
            type="sla",
            title="ZZT B1 escalation",
            send_in_app=True,
            send_email=False,
            send_whatsapp=True,
        )

    channels = {
        d.channel
        for d in db.query(NotificationDelivery)
        .filter(NotificationDelivery.notification_id == notification.id)
        .all()
    }
    assert "whatsapp" not in channels
    db.refresh(user)
    assert user.respond_contact_id is None


# --------------------------------------------------------------------------- #
# WhatsApp delivery task (`notification_tasks._send_whatsapp_for_notification`) #
# --------------------------------------------------------------------------- #
def test_b1_after_unlink_whatsapp_task_sends_nothing_and_does_not_relink(api_client):
    from app.tasks.notification_tasks import _send_whatsapp_for_notification

    client, db = api_client
    user, _contact = _linked_then_unlinked(client, db)

    notification = SimpleNamespace(
        id=str(uuid.uuid4()),
        data={},
        event_type="escalated",
        title="ZZT B1",
        body="",
        source_entity_type="sla_tracking",
        source_entity_id=None,
    )
    delivery = SimpleNamespace(status="pending", error_message=None, sent_at=None)

    with patch("app.services.respond_messaging_service.send_text_or_template") as send:
        _send_whatsapp_for_notification(db, notification, user, delivery)

    send.assert_not_called()
    assert delivery.status == "failed"
    db.refresh(user)
    assert user.respond_contact_id is None


# --------------------------------------------------------------------------- #
# Form banners (`banner_person_service`)                                       #
# --------------------------------------------------------------------------- #
def test_b1_after_unlink_banner_has_no_wa_phone_and_does_not_relink(api_client):
    from app.services.banner_person_service import name_and_wa_phone_for_user_id

    client, db = api_client
    user, _contact = _linked_then_unlinked(client, db)

    name, phone = name_and_wa_phone_for_user_id(db, user.id)
    assert name == "ZZT B1 User"
    assert phone is None
    db.refresh(user)
    assert user.respond_contact_id is None


# --------------------------------------------------------------------------- #
# AC-44: a Respond.io sync creates no user and links nobody                    #
# --------------------------------------------------------------------------- #
def test_ac44_respond_contacts_sync_creates_no_user_and_links_nobody():
    from app.services import respond_sync_handler
    from app.services.respond_link_service import resolve_user_respond_io_id

    with blank_session() as db:
        phone = _msisdn()
        user = _seed_user(db, phone)
        before_users = db.query(User).count()
        before_assignments = db.query(UserRoleAssignment).count()

        class _FakeRespondClient:
            def list_contacts(self, body):
                return {"items": [{"phone": phone, "firstName": "Sync", "lastName": "Person", "id": 77}]}

            def get_contact_by_phone(self, _phone):
                return {}

            def update_contact(self, _identifier, _body):
                return {"ok": True}

        with patch.object(respond_sync_handler, "RespondClient", _FakeRespondClient):
            summary = respond_sync_handler.run_respond_contacts_sync(
                db, SimpleNamespace(id=str(uuid.uuid4()))
            )

        assert summary["created_local"] == 1
        assert db.query(RespondContact).filter(RespondContact.phone_number == phone).count() == 1
        assert db.query(User).count() == before_users
        assert db.query(UserRoleAssignment).count() == before_assignments
        db.refresh(user)
        assert user.respond_contact_id is None
        assert user.contact_number == phone

        # And no later send links it either.
        assert resolve_user_respond_io_id(db, user) is None
        db.refresh(user)
        assert user.respond_contact_id is None
