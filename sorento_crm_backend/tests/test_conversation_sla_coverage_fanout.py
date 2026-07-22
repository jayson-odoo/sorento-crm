"""Conversation-SLA assignment fans out coverage copies to notify-only coverers.

Regression family (the bug that bit us 3x): conversation create previously had NO
assignment notify at all, so notify-only coverage subscribers never heard about the
INITIAL assignment of a conversation SLA. `ConversationSLATrackingService.create_tracking`
now calls `_fan_out_assignment_coverage` on BOTH the new-row and overwrite-resolved
paths (NOT the idempotent already_active path).

This pins:
  1. New-row + overwrite-resolved fan out a coverage Notification + email delivery for
     a notify-only (redirect_assignments=False) subscriber; idempotent-active does NOT.
  2. Coverage copy WORDING is for the COVERER ("assigned to <covered>", "You're
     receiving this because you cover for <covered>", a "Take over: <base>/?team_task=<id>"
     deep link — NOT the detail page).
  3. Re-notify per assignment OCCURRENCE: two assignments of the SAME reused tracker
     with DIFFERENT current_tier_started_at => TWO distinct coverage Notifications
     (different event_type "assigned:<ts>"); same start-time dedups to one.
  4. The email event-key resolver strips the numeric occurrence suffix so
     event_type="assigned:1782282875" still resolves to a REGISTERED key.

Run:
    venv/bin/pytest tests/test_conversation_sla_coverage_fanout.py -q
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.models.access import RespondContact
from app.models.notification import (
    Notification,
    NotificationDelivery,
    NotificationSubscription,
)
from app.models.sla import (
    ConversationSLAEventLog,
    ConversationSLATracking,
    SLAPolicy,
    SLAPolicyTier,
)
from app.models.user import User
from app.schemas.sla import ConversationSLATrackingCreate
from app.services.sla_service import ConversationSLATrackingService
from tests._pg_fixture import blank_session

PHONE = "+60123456789"
COV_SOURCE = "coverage:conversation_sla_tracking"


@pytest.fixture
def db(monkeypatch):
    # The fan-out's last step enqueues an async delivery job. There is no Redis in the
    # unit harness; create_with_channel_preferences already swallows enqueue errors, but
    # stub it so the test never depends on a broker being up.
    import app.services.queue_service as queue_service

    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **k: None)

    with blank_session() as s:
        yield s


def _seed(db) -> dict:
    policy_id = str(uuid.uuid4())
    db.add(SLAPolicy(id=policy_id, code="NORMAL", name="Normal"))
    db.add(
        SLAPolicyTier(
            id=str(uuid.uuid4()),
            policy_id=policy_id,
            tier_level=1,
            tier_name="Tier 1",
            response_hours=4,
            resolution_hours=24,
        )
    )
    contact_id = str(uuid.uuid4())
    db.add(
        RespondContact(
            id=contact_id, phone_number=PHONE, name="Test Contact", session_vars={}
        )
    )
    assignee_id = str(uuid.uuid4())
    db.add(
        User(
            id=assignee_id,
            email="agent1@test.com",
            name="Agent One",
            respond_user_id="900001",
        )
    )
    # Coverer = notify-only subscriber of the assignee. Email defaults to True so the
    # email NotificationDelivery is created for the coverage copy.
    coverer_id = str(uuid.uuid4())
    db.add(
        User(
            id=coverer_id,
            email="coverer@test.com",
            name="The Coverer",
            notify_email_on_assignment=True,
        )
    )
    db.commit()
    return {
        "policy_id": policy_id,
        "contact_id": contact_id,
        "assignee_id": assignee_id,
        "coverer_id": coverer_id,
    }


def _notify_only_coverage(db, coverer_id, assignee_id):
    db.add(
        NotificationSubscription(
            id=str(uuid.uuid4()),
            subscriber_id=coverer_id,
            target_user_id=assignee_id,
            is_active=True,
            redirect_assignments=False,  # notify-only — no redirect
        )
    )
    db.commit()


def _payload(seed, *, message_id=None, started_at=None) -> ConversationSLATrackingCreate:
    return ConversationSLATrackingCreate(
        policy_id=seed["policy_id"],
        current_tier=1,
        assigned_to_id=seed["assignee_id"],
        contact_phone_number=PHONE,
        message_id=message_id,
        current_tier_started_at=started_at,
        initiated_at=started_at,
    )


def _coverage_notes(db, coverer_id) -> list[Notification]:
    return (
        db.query(Notification)
        .filter(
            Notification.user_id == coverer_id,
            Notification.source_entity_type == COV_SOURCE,
        )
        .order_by(Notification.event_type.asc())
        .all()
    )


def _deliveries(db, note_id) -> list[NotificationDelivery]:
    return (
        db.query(NotificationDelivery)
        .filter(NotificationDelivery.notification_id == note_id)
        .all()
    )


# ---------------------------------------------------------------------------
# CHANGE 1: fan-out on new-row + overwrite-resolved; NOT on idempotent active
# ---------------------------------------------------------------------------

def test_new_row_fans_out_coverage_copy_with_email_delivery(db):
    seed = _seed(db)
    _notify_only_coverage(db, seed["coverer_id"], seed["assignee_id"])
    service = ConversationSLATrackingService(db)

    tracking = service.create_tracking(_payload(seed, message_id=111))
    # Assignee unchanged (notify-only never redirects).
    assert str(tracking.assigned_to_id) == seed["assignee_id"]

    notes = _coverage_notes(db, seed["coverer_id"])
    assert len(notes) == 1, "notify-only coverer should get exactly one coverage copy"
    note = notes[0]
    assert note.type == "conversation_sla"
    assert note.source_entity_id == str(tracking.id)
    # In-app + email deliveries created (email pref defaults True).
    channels = {d.channel for d in _deliveries(db, note.id)}
    assert "in_app" in channels
    assert "email" in channels


def test_idempotent_active_does_not_fan_out(db):
    seed = _seed(db)
    _notify_only_coverage(db, seed["coverer_id"], seed["assignee_id"])
    service = ConversationSLATrackingService(db)

    first = service.create_tracking(_payload(seed, message_id=111))
    notes_after_first = _coverage_notes(db, seed["coverer_id"])
    assert len(notes_after_first) == 1

    # Second create hits the active conversation -> idempotent return, NO fan-out.
    second = service.create_tracking(_payload(seed, message_id=222))
    assert str(second.id) == str(first.id)
    assert bool(getattr(second, "_already_active", False)) is True

    notes_after_second = _coverage_notes(db, seed["coverer_id"])
    assert len(notes_after_second) == 1, "idempotent-active path must not re-fan-out"


def test_overwrite_resolved_fans_out_again(db):
    seed = _seed(db)
    _notify_only_coverage(db, seed["coverer_id"], seed["assignee_id"])
    service = ConversationSLATrackingService(db)

    t0 = datetime(2026, 6, 1, 8, 0, 0)
    first = service.create_tracking(_payload(seed, message_id=111, started_at=t0))
    assert len(_coverage_notes(db, seed["coverer_id"])) == 1

    # Resolve, then a new inbound conversation with a DIFFERENT start time overwrites
    # the resolved row in place -> fan-out fires again for the new occurrence.
    first.is_resolved = True
    first.resolved_at = datetime(2026, 6, 1, 10, 0, 0)
    db.commit()

    t1 = datetime(2026, 6, 2, 8, 0, 0)
    second = service.create_tracking(_payload(seed, message_id=222, started_at=t1))
    assert str(second.id) == str(first.id)
    assert bool(getattr(second, "_overwrote_resolved", False)) is True

    notes = _coverage_notes(db, seed["coverer_id"])
    assert len(notes) == 2, "overwrite-resolved must re-notify coverers (new occurrence)"


# ---------------------------------------------------------------------------
# CHANGE 2: coverage copy WORDING (worded for the coverer, not "to you")
# ---------------------------------------------------------------------------

def test_coverage_copy_wording_and_takeover_link(db, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "frontend_base_url", "https://crm.example.com")
    seed = _seed(db)
    _notify_only_coverage(db, seed["coverer_id"], seed["assignee_id"])
    service = ConversationSLATrackingService(db)

    tracking = service.create_tracking(_payload(seed, message_id=111))
    notes = _coverage_notes(db, seed["coverer_id"])
    assert len(notes) == 1
    note = notes[0]

    covered_name = "Agent One"
    assert note.title == f"SLA task assigned to {covered_name}"
    assert f"has been assigned to {covered_name}" in (note.body or "")
    assert (
        f"You're receiving this because you cover for {covered_name}"
        in (note.body or "")
    )
    # Take-over deep link points at the dashboard My Team widget (?team_task=<id>),
    # NOT the conversation detail page.
    assert f"Take over: https://crm.example.com/?team_task={tracking.id}" in (
        note.body or ""
    )
    assert "/sla-management/conversation-sla-tracking/" not in (note.body or "")


# ---------------------------------------------------------------------------
# CHANGE 3: re-notify per occurrence (dedup vs recurrence)
# ---------------------------------------------------------------------------

def test_two_occurrences_produce_two_distinct_coverage_notes(db):
    """Two assignments of the SAME reused tracker with DIFFERENT
    current_tier_started_at => two distinct coverage Notifications keyed off the
    occurrence (event_type 'assigned:<ts>'), each with its own deliveries."""
    seed = _seed(db)
    _notify_only_coverage(db, seed["coverer_id"], seed["assignee_id"])
    service = ConversationSLATrackingService(db)

    t0 = datetime(2026, 6, 1, 8, 0, 0)
    first = service.create_tracking(_payload(seed, message_id=111, started_at=t0))
    first.is_resolved = True
    db.commit()

    t1 = datetime(2026, 6, 5, 9, 30, 0)  # different occurrence
    service.create_tracking(_payload(seed, message_id=222, started_at=t1))

    notes = _coverage_notes(db, seed["coverer_id"])
    assert len(notes) == 2
    event_types = {n.event_type for n in notes}
    assert len(event_types) == 2, f"occurrences must differ: {event_types}"
    assert event_types == {
        f"assigned:{int(t0.timestamp())}",
        f"assigned:{int(t1.timestamp())}",
    }
    # Each occurrence got its own deliveries.
    for n in notes:
        chans = {d.channel for d in _deliveries(db, n.id)}
        assert "in_app" in chans and "email" in chans


def test_same_occurrence_dedups_to_one(db):
    """Re-running the SAME occurrence (same start-time) must dedup to ONE coverage
    note via create_with_channel_preferences' (user, source, event_type) idempotency."""
    seed = _seed(db)
    _notify_only_coverage(db, seed["coverer_id"], seed["assignee_id"])
    service = ConversationSLATrackingService(db)

    t0 = datetime(2026, 6, 1, 8, 0, 0)
    first = service.create_tracking(_payload(seed, message_id=111, started_at=t0))
    # Resolve then re-create with the SAME start time = same occurrence key.
    first.is_resolved = True
    db.commit()
    service.create_tracking(_payload(seed, message_id=222, started_at=t0))

    notes = _coverage_notes(db, seed["coverer_id"])
    assert len(notes) == 1, "same-occurrence start-time must dedup to one note"
    assert notes[0].event_type == f"assigned:{int(t0.timestamp())}"


# ---------------------------------------------------------------------------
# CHANGE 4: email event-key resolver strips the numeric occurrence suffix
# ---------------------------------------------------------------------------
# CHANGE 4 lives in tests/test_notification_event_key_resolution.py
# (test_assigned_occurrence_suffix_resolves_to_registered_key) — the dedicated home
# for _resolve_event_key cases. Kept there to avoid duplicating the same assertion
# across files; the event_type these tests emit ("assigned:<ts>") is verified here
# in test_two_occurrences_produce_two_distinct_coverage_notes.
