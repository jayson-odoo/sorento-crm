"""TCK-2026-000029 — WhatsApp notification delivery on escalation + assignment.

Covers AC-29-F1/F2 (delivery created when opted-in + linked), F3 (not for other
events), F5 (skip when opt-out / no contact), D1 (whatsapp channel), F4 + S2
(send-side text/template + best-effort failure).

Run: pytest tests/test_whatsapp_notifications.py -v
"""
from __future__ import annotations

import uuid

import pytest

from app.models.access import RespondContact
from app.models.notification import Notification, NotificationDelivery
from app.models.integration import IntegrationLog
from app.models.user import User
from app.services.notification_service import NotificationService
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _user(db, *, notify_whatsapp, with_contact):
    uid = str(uuid.uuid4())
    contact_id = None
    if with_contact:
        contact_id = str(uuid.uuid4())
        db.add(RespondContact(
            id=contact_id, phone_number="60123456789", name="C",
            respond_io_id="io-1", session_vars={},
        ))
    db.add(User(
        id=uid, email=f"{uid[:8]}@t.com", name="U",
        notify_whatsapp=notify_whatsapp, respond_contact_id=contact_id,
    ))
    db.commit()
    return uid


def _channels(db, notif_id):
    return {
        d.channel
        for d in db.query(NotificationDelivery).filter(
            NotificationDelivery.notification_id == notif_id
        )
    }


def _create(db, user_id, *, send_whatsapp, event_type="escalated"):
    return NotificationService(db).create_with_channel_preferences(
        user_id=user_id, type="form_sla", title="T", body="B",
        source_entity_type="form_sla_tracking", source_entity_id=str(uuid.uuid4()),
        event_type=event_type, send_in_app=True, send_email=True,
        send_web_push=False, send_whatsapp=send_whatsapp,
    )


def test_whatsapp_delivery_when_opted_in_and_linked(db):
    uid = _user(db, notify_whatsapp=True, with_contact=True)
    n = _create(db, uid, send_whatsapp=True)
    assert "whatsapp" in _channels(db, n.id)


def test_no_whatsapp_when_optout(db):
    uid = _user(db, notify_whatsapp=False, with_contact=True)
    n = _create(db, uid, send_whatsapp=True)
    chans = _channels(db, n.id)
    assert "whatsapp" not in chans and "in_app" in chans and "email" in chans


def test_no_whatsapp_when_no_contact(db):
    uid = _user(db, notify_whatsapp=True, with_contact=False)
    n = _create(db, uid, send_whatsapp=True)
    assert "whatsapp" not in _channels(db, n.id)


def test_no_whatsapp_for_other_events(db):
    """send_whatsapp defaults False (response/resolution/reminder) -> no whatsapp."""
    uid = _user(db, notify_whatsapp=True, with_contact=True)
    n = _create(db, uid, send_whatsapp=False, event_type="resolution")
    assert "whatsapp" not in _channels(db, n.id)


def test_send_side_marks_sent(db, monkeypatch):
    uid = _user(db, notify_whatsapp=True, with_contact=True)
    n = _create(db, uid, send_whatsapp=True)
    delivery = db.query(NotificationDelivery).filter(
        NotificationDelivery.notification_id == n.id,
        NotificationDelivery.channel == "whatsapp",
    ).first()
    import app.services.respond_messaging_service as rms
    calls = {}
    monkeypatch.setattr(
        rms, "send_text_or_template",
        lambda db, **kw: calls.update(kw) or {"sent_as": "template"},
    )
    from app.tasks.notification_tasks import _send_whatsapp_for_notification
    user = db.query(User).filter(User.id == uid).first()
    _send_whatsapp_for_notification(db, n, user, delivery)
    db.refresh(delivery)
    assert delivery.status == "sent"
    assert calls["identifier"] == "io-1" and calls["use_case"] == "sla_escalation"


def test_send_side_failure_is_best_effort(db, monkeypatch):
    uid = _user(db, notify_whatsapp=True, with_contact=True)
    n = _create(db, uid, send_whatsapp=True)
    delivery = db.query(NotificationDelivery).filter(
        NotificationDelivery.notification_id == n.id,
        NotificationDelivery.channel == "whatsapp",
    ).first()
    import app.services.respond_messaging_service as rms

    def _boom(db, **kw):
        raise RuntimeError("respond down")

    monkeypatch.setattr(rms, "send_text_or_template", _boom)
    from app.tasks.notification_tasks import _send_whatsapp_for_notification
    user = db.query(User).filter(User.id == uid).first()
    # must not raise
    _send_whatsapp_for_notification(db, n, user, delivery)
    db.refresh(delivery)
    assert delivery.status == "failed"
