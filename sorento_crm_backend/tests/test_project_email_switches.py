"""PROJECT-EMAIL-SWITCHES: each project-sales email has its own switch.

Before this lane three project-sales notifications had no entry in
`_NOTIFICATION_TYPE_TO_EVENT_KEY`, so their email lane fell back to the generic
`notification_delivery` event. That one switch on System Management > Email Event Configs
also governs unrelated mails, so the owner could not stop the below-minimum-price email
without stopping quotation approved / rejected, changes requested, PO mismatch and reassigned.

Pinned here, end to end through the real outbox and drainer on the blank schema:
  * each notification type resolves to its OWN registered event key, seeded enabled;
  * switching that key off cancels only its email, and the in-app Notification row stays;
  * switching the generic `notification_delivery` off no longer touches these three.

Plan: documentation/plans/project-sales/PLAN-project-email-switches-2nov.md

Run:
    venv/bin/pytest tests/test_project_email_switches.py -q
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from app.models.email_outbox import EmailEventConfig, EmailOutbox
from app.models.notification import Notification, NotificationDelivery
from app.services.email_event_registry import EMAIL_EVENT_REGISTRY, get_event_def
from app.tasks import email_outbox_tasks
from app.tasks.notification_tasks import _enqueue_email_for_delivery, _resolve_event_key
from tests._pg_fixture import blank_session

# notif_type as `project_notify_service._send` writes it -> the event key it must get.
# `_send` sets event_type to the notif_type itself, so the composite lookup misses and the
# plain type lookup is the one that decides.
PROJECT_EMAILS = {
    "project_price_floor_breach": "project_below_minimum_price",
    "project_quotation_approval_requested": "project_quotation_approval_requested",
    "project_interest_registered": "project_interest_registered",
}

# A project mail the lane deliberately leaves on the generic switch.
STILL_GENERIC = "project_reassigned"

USER_ID = "82dce68d-596c-5265-9263-07b67db11d44"


class _User:
    id = USER_ID
    email = "manager@example.com"


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _note(db, notif_type: str):
    n = Notification(
        id=str(uuid.uuid4()),
        user_id=USER_ID,
        type=notif_type,
        title="PRJ-0001 priced below minimum price",
        body="A line was priced below the minimum price.",
        data={"link": "/project-sales/x"},
        source_entity_type="project",
        source_entity_id=str(uuid.uuid4()),
        event_type=notif_type,
    )
    db.add(n)
    db.flush()
    d = NotificationDelivery(
        id=str(uuid.uuid4()), notification_id=n.id, channel="email", status="pending"
    )
    db.add(d)
    db.commit()
    return n, d


def _set_enabled(db, event_key: str, enabled: bool) -> None:
    evt = get_event_def(event_key)
    assert evt is not None, event_key
    cfg = db.query(EmailEventConfig).filter(EmailEventConfig.event_key == event_key).first()
    if cfg is None:
        cfg = EmailEventConfig(
            event_key=event_key,
            display_name=evt.display_name,
            description=evt.description,
            enabled=enabled,
        )
        db.add(cfg)
    cfg.enabled = enabled
    db.commit()


class _NoClose:
    """The drainer closes its session; the test still needs this one afterwards."""

    def __init__(self, s):
        self._s = s

    def __getattr__(self, name):
        return getattr(self._s, name)

    def close(self):
        pass


def _send_and_drain(db, notif_type: str):
    note, delivery = _note(db, notif_type)
    _enqueue_email_for_delivery(db, note, _User(), delivery, _resolve_event_key(note))
    db.commit()
    with patch.object(email_outbox_tasks, "SessionLocal", return_value=_NoClose(db)), patch.object(
        email_outbox_tasks, "send_mime_email"
    ):
        email_outbox_tasks.drain_email_outbox()
    row = (
        db.query(EmailOutbox)
        .filter(EmailOutbox.metadata_json["notification_delivery_id"].astext == str(delivery.id))
        .one()
    )
    db.refresh(delivery)
    return note, delivery, row


@pytest.mark.parametrize("notif_type,event_key", sorted(PROJECT_EMAILS.items()))
def test_each_project_email_resolves_to_its_own_registered_key(notif_type, event_key):
    from types import SimpleNamespace

    key = _resolve_event_key(SimpleNamespace(type=notif_type, event_type=notif_type))
    assert key == event_key
    assert key != "notification_delivery"
    evt = get_event_def(key)
    assert evt is not None
    # A clear on-screen name, not the raw key.
    assert evt.display_name and evt.display_name != key
    assert evt.description


def test_the_three_keys_are_distinct_registry_rows():
    keys = [e.event_key for e in EMAIL_EVENT_REGISTRY]
    for key in PROJECT_EMAILS.values():
        assert keys.count(key) == 1, key
    assert len(set(PROJECT_EMAILS.values())) == 3


def test_seed_creates_the_three_rows_enabled(db):
    from app.services.email_event_registry import seed_event_configs

    seed_event_configs(db)
    rows = {
        r.event_key: r
        for r in db.query(EmailEventConfig)
        .filter(EmailEventConfig.event_key.in_(list(PROJECT_EMAILS.values())))
        .all()
    }
    assert set(rows) == set(PROJECT_EMAILS.values())
    assert all(r.enabled for r in rows.values())


@pytest.mark.parametrize("notif_type,event_key", sorted(PROJECT_EMAILS.items()))
def test_switch_off_cancels_only_its_email_and_keeps_the_bell(db, notif_type, event_key):
    _set_enabled(db, event_key, False)

    note, delivery, row = _send_and_drain(db, notif_type)
    assert row.event_key == event_key
    assert row.status == "cancelled"
    assert row.cancel_reason == "event_disabled"
    assert delivery.status == "failed"
    assert delivery.error_message == "event_disabled"
    # The in-app notification is untouched by the email switch.
    assert db.query(Notification).filter(Notification.id == note.id).count() == 1

    # The other two project emails still go out.
    for other_type in PROJECT_EMAILS:
        if other_type == notif_type:
            continue
        _, _, other = _send_and_drain(db, other_type)
        assert other.cancel_reason is None, other_type
        assert other.status != "cancelled", other_type


@pytest.mark.parametrize("notif_type", sorted(PROJECT_EMAILS))
def test_generic_switch_no_longer_governs_these(db, notif_type):
    _set_enabled(db, "notification_delivery", False)

    _, _, row = _send_and_drain(db, notif_type)
    assert row.event_key == PROJECT_EMAILS[notif_type]
    assert row.status != "cancelled"
    assert row.cancel_reason is None


def test_generic_switch_still_governs_the_untouched_project_mails(db):
    """Control: the lane moves exactly three types, not every project mail."""
    _set_enabled(db, "notification_delivery", False)

    _, _, row = _send_and_drain(db, STILL_GENERIC)
    assert row.event_key == "notification_delivery"
    assert row.cancel_reason == "event_disabled"
