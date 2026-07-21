"""TCK-2026-000033 — web push: mirror in-app + prune dead subscriptions.

Covers AC-33-F4 (web_push delivery mirrors in-app when subscribed / skipped when not)
and AC-33-F3/S1 (expired endpoint pruned on HTTP 410).

Run: pytest tests/test_web_push.py -v
"""
from __future__ import annotations

import sys
import types
import uuid

import pytest

from app.models.notification import Notification, NotificationDelivery, PushSubscription
from app.models.user import User
from app.services.notification_service import NotificationService
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _user(db):
    uid = str(uuid.uuid4())
    db.add(User(id=uid, email=f"{uid[:8]}@t.com", name="U"))
    db.commit()
    return uid


def _sub(db, uid, endpoint="https://push.example/abc"):
    db.add(PushSubscription(user_id=uid, endpoint=endpoint, p256dh="k", auth="a"))
    db.commit()


def _channels(db, nid):
    return {d.channel for d in db.query(NotificationDelivery).filter(NotificationDelivery.notification_id == nid)}


def test_web_push_mirrors_in_app_when_subscribed(db):
    uid = _user(db)
    _sub(db, uid)
    n = NotificationService(db).create_with_channel_preferences(
        user_id=uid, type="form_sla", title="T", body="B",
        send_in_app=True, send_email=False, send_web_push=False,
    )
    assert "web_push" in _channels(db, n.id)


def test_no_web_push_without_subscription(db):
    uid = _user(db)
    n = NotificationService(db).create_with_channel_preferences(
        user_id=uid, type="form_sla", title="T", body="B",
        send_in_app=True, send_email=False, send_web_push=False,
    )
    assert "web_push" not in _channels(db, n.id)


def _install_fake_pywebpush(*, raise_status=None):
    fake = types.ModuleType("pywebpush")

    class WebPushException(Exception):
        def __init__(self, msg, response=None):
            super().__init__(msg)
            self.response = response

    def webpush(**kwargs):
        if raise_status is not None:
            raise WebPushException("err", response=types.SimpleNamespace(status_code=raise_status))
        return True

    fake.webpush = webpush
    fake.WebPushException = WebPushException
    sys.modules["pywebpush"] = fake


def test_prune_on_410(db, monkeypatch):
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "test-key")
    _install_fake_pywebpush(raise_status=410)
    uid = _user(db)
    _sub(db, uid)
    n = NotificationService(db).create_with_channel_preferences(
        user_id=uid, type="form_sla", title="T", body="B",
        send_in_app=True, send_email=False, send_web_push=True,
    )
    delivery = db.query(NotificationDelivery).filter(
        NotificationDelivery.notification_id == n.id, NotificationDelivery.channel == "web_push"
    ).first()
    from app.tasks.notification_tasks import _send_web_push_for_notification
    _send_web_push_for_notification(db, n, uid, delivery)
    # expired subscription pruned
    assert db.query(PushSubscription).filter(PushSubscription.user_id == uid).count() == 0
    db.refresh(delivery)
    assert delivery.status == "failed"


def test_send_success_marks_sent(db, monkeypatch):
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "test-key")
    _install_fake_pywebpush(raise_status=None)
    uid = _user(db)
    _sub(db, uid)
    n = NotificationService(db).create_with_channel_preferences(
        user_id=uid, type="form_sla", title="T", body="B",
        send_in_app=True, send_email=False, send_web_push=True,
    )
    delivery = db.query(NotificationDelivery).filter(
        NotificationDelivery.notification_id == n.id, NotificationDelivery.channel == "web_push"
    ).first()
    from app.tasks.notification_tasks import _send_web_push_for_notification
    _send_web_push_for_notification(db, n, uid, delivery)
    db.refresh(delivery)
    assert delivery.status == "sent"
    assert db.query(PushSubscription).filter(PushSubscription.user_id == uid).count() == 1
