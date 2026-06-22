"""TCK-2026-000030 — conversation SLA daily summary via WhatsApp.

Covers AC-30-F1/F2 (whatsapp delivery when opted-in + linked / skip otherwise),
F4 (notify_whatsapp_summary independent of email subscription), F3 (self-scoped —
counts per user), S1 (one delivery per user per run).

Run: pytest tests/test_sla_daily_summary_whatsapp.py -v
"""
from __future__ import annotations

import types
import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON as GenericJSON

from app.database import Base
from app.models.access import RespondContact
from app.models.lookup import LookupBinding
from app.models.notification import Notification, NotificationDelivery
from app.models.sla import ConversationSLATracking, ConversationSLAEventLog
from app.models.user import User, UserStatus
from app.services.user_sla_daily_summary_service import run_user_sla_daily_summary


def _sqlite_safe(*tables):
    for t in tables:
        for col in list(t.columns):
            if isinstance(col.type, JSONB):
                col.type = GenericJSON()
                col.server_default = None


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    _sqlite_safe(
        RespondContact.__table__, Notification.__table__, NotificationDelivery.__table__,
        ConversationSLATracking.__table__, ConversationSLAEventLog.__table__,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            RespondContact.__table__, Notification.__table__, NotificationDelivery.__table__,
            ConversationSLATracking.__table__, ConversationSLAEventLog.__table__,
            User.__table__, LookupBinding.__table__,
        ],
    )
    s = sessionmaker(bind=engine)()
    try:
        yield s
    finally:
        s.close()


def _user(db, *, email_sub, wa_sub, with_contact):
    uid = str(uuid.uuid4())
    cid = None
    if with_contact:
        cid = str(uuid.uuid4())
        db.add(RespondContact(id=cid, phone_number=f"60{uid[:9].replace('-','')[:9]}", name="C", respond_io_id=f"io-{uid[:6]}", session_vars={}))
    db.add(User(
        id=uid, email=f"{uid[:8]}@t.com", name="U", status=UserStatus.ACTIVE.value,
        is_trashed=False, daily_sla_summary_subscribed=email_sub,
        notify_whatsapp_summary=wa_sub, respond_contact_id=cid,
    ))
    db.commit()
    return uid


def _add_outstanding(db, uid):
    """Give the user one unresolved conversation SLA tracker so the summary sends
    (the digest is skipped entirely when outstanding == 0)."""
    db.add(ConversationSLATracking(
        id=str(uuid.uuid4()),
        policy_id=str(uuid.uuid4()),
        respond_contact_id=None,
        assigned_to_id=uid,
        current_tier=1,
        due_at=datetime.utcnow(),
        initiated_at=datetime.utcnow(),
        is_resolved=False,
        source_entity_type=None,
    ))
    db.commit()


def _channels(db, uid):
    notif = db.query(Notification).filter(Notification.user_id == uid).first()
    if not notif:
        return set()
    return {d.channel for d in db.query(NotificationDelivery).filter(NotificationDelivery.notification_id == notif.id)}


def _run(db):
    task = types.SimpleNamespace(metadata_={"send_in_app": True, "send_email": True})
    return run_user_sla_daily_summary(db, task)


def test_email_subscriber_no_whatsapp(db):
    uid = _user(db, email_sub=True, wa_sub=False, with_contact=True)
    _add_outstanding(db, uid)
    _run(db)
    chans = _channels(db, uid)
    assert "in_app" in chans and "email" in chans and "whatsapp" not in chans


def test_zero_outstanding_skipped(db):
    """No outstanding conversations => no summary on any channel (don't annoy)."""
    uid = _user(db, email_sub=True, wa_sub=True, with_contact=True)
    res = _run(db)
    assert _channels(db, uid) == set()
    assert res["skipped_no_outstanding"] >= 1


def test_whatsapp_subscriber_gets_only_whatsapp(db):
    """AC-30-F4: notify_whatsapp_summary independent — WhatsApp-only user gets
    whatsapp delivery and NOT email/in-app (not subscribed to those)."""
    uid = _user(db, email_sub=False, wa_sub=True, with_contact=True)
    _add_outstanding(db, uid)
    res = _run(db)
    chans = _channels(db, uid)
    assert chans == {"whatsapp"}
    assert res["queued_whatsapp"] >= 1


def test_whatsapp_subscriber_without_contact_skipped(db):
    uid = _user(db, email_sub=False, wa_sub=True, with_contact=False)
    _add_outstanding(db, uid)
    _run(db)
    # no resolvable contact + not email-subscribed -> nothing sent
    assert _channels(db, uid) == set()


def test_both_subscriptions_all_channels(db):
    uid = _user(db, email_sub=True, wa_sub=True, with_contact=True)
    _add_outstanding(db, uid)
    _run(db)
    chans = _channels(db, uid)
    assert {"in_app", "email", "whatsapp"} <= chans


def test_idempotent_no_duplicate_whatsapp_on_rerun(db):
    uid = _user(db, email_sub=False, wa_sub=True, with_contact=True)
    _add_outstanding(db, uid)
    _run(db)
    _run(db)  # same day rerun -> idempotent notification, no second delivery
    notifs = db.query(Notification).filter(Notification.user_id == uid).all()
    assert len(notifs) == 1
    wa = [
        d for d in db.query(NotificationDelivery).filter(
            NotificationDelivery.notification_id == notifs[0].id,
            NotificationDelivery.channel == "whatsapp",
        )
    ]
    assert len(wa) == 1
