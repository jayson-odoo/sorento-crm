"""Regression: SLA event-log timestamps must not be shifted -8h.

`ConversationSLATracking` datetime columns (`due_at`, etc.) are stored as
NAIVE UTC. They are copied into event-log payloads and `create_event_log`
runs them through `_normalize_api_datetime_to_utc`, which treats a NAIVE
value as Asia/Kuala_Lumpur (UTC+8) and converts to UTC - i.e. it subtracts
8h from a naive-UTC instant. The call sites must therefore pass an
aware-UTC datetime (`_to_aware_utc(...)`) so the normalize step is a no-op,
not an 8h shift.

This test drives the assign-event write path of
`admin_test_override_tracking` (one of the fixed call sites) and asserts the
logged `due_at` equals the tracking row's original UTC instant.

Run: pytest tests/test_sla_event_log_timezone.py -v
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.access import AccessAgent, RespondContact
from app.models.sla import ConversationSLATracking, ConversationSLAEventLog, SLAPolicy
from app.models.user import User
from app.services.sla_service import ConversationSLATrackingService
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _as_naive_utc(dt: datetime) -> datetime:
    """Normalize a stored datetime (naive or aware) to a naive-UTC instant
    for comparison, mirroring how the DB stores TIMESTAMP WITHOUT TIME ZONE."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def test_assign_event_log_due_at_not_shifted(db):
    # Known naive-UTC deadline. The buggy path would store this as MYT and
    # shift it back 8h to the previous day (18:00). The fix keeps it at 02:00.
    naive_utc_due = datetime(2026, 6, 29, 2, 0, 0)

    pid = str(uuid.uuid4())
    db.add(SLAPolicy(id=pid, code="P", name="P"))

    new_assignee = str(uuid.uuid4())
    db.add(User(id=new_assignee, email="z@t.com", name="Zoe", respond_user_id="ru-zoe"))

    tracking_id = str(uuid.uuid4())
    db.add(
        ConversationSLATracking(
            id=tracking_id,
            policy_id=pid,
            current_tier=1,
            initiated_at=datetime(2026, 6, 28, 2, 0, 0),
            current_tier_started_at=datetime(2026, 6, 28, 2, 0, 0),
            due_at=naive_utc_due,
            is_responded=False,
            is_resolved=False,
        )
    )
    db.commit()

    svc = ConversationSLATrackingService(db)
    # Drives the assign_changed branch -> create_event_log(due_at=tracking.due_at)
    svc.admin_test_override_tracking(tracking_id, {"assigned_to_id": new_assignee})

    log = (
        db.query(ConversationSLAEventLog)
        .filter(
            ConversationSLAEventLog.sla_tracking_id == tracking_id,
            ConversationSLAEventLog.event_type == "assign",
        )
        .one()
    )

    assert log.due_at is not None
    logged = _as_naive_utc(log.due_at)
    # Correct: identical UTC instant.
    assert logged == naive_utc_due
    # Guard against the regression: NOT shifted -8h (would land on the 28th @ 18:00).
    assert logged != naive_utc_due - timedelta(hours=8)
