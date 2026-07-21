"""Email event registry coverage + end-to-end enqueue regression
(PLAN-sla-extend-deadline follow-up).

The original incident: `sla_deadline_extended` was NOT in EMAIL_EVENT_REGISTRY, so
`email_outbox_service.enqueue` raised UnknownEmailEvent and the email was silently
dropped (no outbox row, delivery marked failed). These tests pin:

  CHANGE 3 — registry coverage:
    * get_event_def("sla_deadline_extended") is not None.
    * GUARD: every target value in _NOTIFICATION_TYPE_TO_EVENT_KEY has a registry
      entry — catches any future notification key that lacks an email registry def.

  CHANGE 4 — end-to-end enqueue:
    * A registered key enqueues an EmailOutbox row + marks the delivery 'queued'.
    * An UNREGISTERED key raises UnknownEmailEvent (proves the guard is real — this
      is exactly what dropped the email before the registry fix).

Run:
    venv/bin/pytest tests/test_email_event_registry_coverage.py -q
"""
from __future__ import annotations

import uuid

import pytest

from app.models.email_outbox import EmailEventConfig, EmailOutbox
from app.models.notification import Notification, NotificationDelivery
from tests._pg_fixture import blank_session
from app.services import email_outbox_service
from app.services.email_event_registry import EMAIL_EVENT_REGISTRY, get_event_def
from app.services.email_outbox_service import UnknownEmailEvent
from app.tasks.notification_tasks import (
    _NOTIFICATION_TYPE_TO_EVENT_KEY,
    _enqueue_email_for_delivery,
    _resolve_event_key,
)


# ---------------------------------------------------------------------------
# CHANGE 3: registry coverage
# ---------------------------------------------------------------------------
def test_sla_deadline_extended_is_registered():
    """The event that caused the silent-drop incident must be in the registry."""
    assert get_event_def("sla_deadline_extended") is not None


def test_every_notification_event_key_target_has_registry_entry():
    """GUARD: every outbox key the notification resolver can emit is registered.

    'notification_delivery' is the registry's own fallback, so it is included by
    construction. Any value missing here would re-introduce the UnknownEmailEvent
    silent-drop class of bug."""
    missing = sorted(
        target
        for target in set(_NOTIFICATION_TYPE_TO_EVENT_KEY.values())
        if get_event_def(target) is None
    )
    assert missing == [], f"event keys missing from EMAIL_EVENT_REGISTRY: {missing}"


def test_fallback_event_key_is_registered():
    """The resolver's ultimate fallback ('notification_delivery') must be enqueueable."""
    assert get_event_def("notification_delivery") is not None


# ---------------------------------------------------------------------------
# CHANGE 4: end-to-end enqueue (the real regression)
# ---------------------------------------------------------------------------
@pytest.fixture
def db():
    # Previously an in-memory sqlite bind that had to downgrade EmailOutbox's and
    # Notification's JSONB columns to generic JSON in the shared model metadata --
    # a mutation that outlived this fixture. On the blank schema the real JSONB
    # DDL is used as-is.
    with blank_session() as s:
        yield s


class _FakeUser:
    def __init__(self, uid="u1", email="next@example.com"):
        self.id = uid
        self.email = email


def _build_notification(db, *, type_, event_type) -> Notification:
    n = Notification(
        id=str(uuid.uuid4()),
        user_id="u1",
        type=type_,
        title="SLA deadline extended: CMP-0001",
        body="The resolution deadline was extended. Reason: supplier.",
        data={},
        source_entity_type="form_sla_tracking",
        source_entity_id=str(uuid.uuid4()),
        event_type=event_type,
    )
    db.add(n)
    db.flush()
    delivery = NotificationDelivery(
        id=str(uuid.uuid4()),
        notification_id=n.id,
        channel="email",
        status="pending",
    )
    db.add(delivery)
    db.commit()
    db.refresh(n)
    db.refresh(delivery)
    return n, delivery


def test_enqueue_email_for_deadline_extended_creates_outbox_row(db):
    """CHANGE 4: a Notification(type='form_sla', event_type='deadline_extended:1')
    routes through _resolve_event_key -> 'sla_deadline_extended' and enqueues an
    EmailOutbox row; the delivery is marked 'queued', NOT dropped/failed."""
    note, delivery = _build_notification(db, type_="form_sla", event_type="deadline_extended:1")
    event_key = _resolve_event_key(note)
    assert event_key == "sla_deadline_extended"

    _enqueue_email_for_delivery(db, note, _FakeUser(), delivery, event_key)

    db.refresh(delivery)
    assert delivery.status == "queued"
    assert delivery.error_message is None

    rows = (
        db.query(EmailOutbox)
        .filter(EmailOutbox.event_key == "sla_deadline_extended")
        .all()
    )
    assert len(rows) == 1
    # enqueue auto-created the EmailEventConfig row (event is registered).
    cfg = (
        db.query(EmailEventConfig)
        .filter(EmailEventConfig.event_key == "sla_deadline_extended")
        .first()
    )
    assert cfg is not None


def test_enqueue_with_unregistered_key_raises_unknown_email_event(db):
    """CHANGE 4 (proves the guard is real): enqueueing an UNREGISTERED key raises
    UnknownEmailEvent — the exact failure that silently dropped deadline-extended
    emails before 'sla_deadline_extended' was added to the registry."""
    with pytest.raises(UnknownEmailEvent):
        email_outbox_service.enqueue(
            db,
            event_key="totally_unregistered_event",
            to="next@example.com",
            subject="x",
            body_text="x",
        )
    # No outbox row was created for the unregistered key.
    assert (
        db.query(EmailOutbox)
        .filter(EmailOutbox.event_key == "totally_unregistered_event")
        .count()
        == 0
    )


def test_enqueue_with_registered_key_does_not_raise(db):
    """CHANGE 4 control: the registered key enqueues cleanly (no exception)."""
    outbox_id = email_outbox_service.enqueue(
        db,
        event_key="sla_deadline_extended",
        to="next@example.com",
        subject="SLA deadline extended",
        body_text="body",
    )
    db.commit()
    assert outbox_id
    row = db.query(EmailOutbox).filter(EmailOutbox.id == outbox_id).first()
    assert row is not None
    assert row.event_key == "sla_deadline_extended"
    assert row.status == "pending"  # outbox starts pending; drainer sends later
