"""Form-banner person links — historical escalated-FROM backfill (UAC HIST-2).

The backfill sets each legacy escalation row's from_assigned_to_id to the
assigned_to_id of the immediately-prior event-log row (per tracking, by event_at);
escalation rows with no prior event stay NULL. Idempotent.

Run: pytest tests/test_escalation_backfill.py -v
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from app.models.sla import ConversationSLAEventLog, ConversationSLATracking, SLAPolicy
from app.models.user import User
from tests._pg_fixture import blank_schema_engine, blank_session, unique_code


@pytest.fixture
def db():
    with blank_session() as session:
        # The backfill is raw text() SQL, which schema_translate_map does not
        # rewrite -- an unqualified table name would resolve against search_path
        # and hit the real public table. Point search_path at the blank schema so
        # the script's SQL and the ORM see the same rows.
        blank = blank_schema_engine().get_execution_options()["schema_translate_map"][None]
        session.execute(text(f'SET search_path TO "{blank}"'))
        try:
            yield session
        finally:
            session.execute(text("RESET search_path"))


@pytest.fixture
def tracking(db):
    """A pair of real SLA trackers to hang event rows off.

    Postgres enforces conversation_sla_event_log.sla_tracking_id -> tracking and
    assigned_to_id -> users, which sqlite did not: the old fixture wrote bare
    uuids and the literal "user-1". Real parents now, so the FKs are exercised.
    """
    policy = SLAPolicy(code=unique_code("pol"), name="Backfill policy")
    db.add(policy)
    user = User(id=str(uuid.uuid4()), email=f"{unique_code('u')}@example.test", name="U1")
    db.add(user)
    db.flush()

    made = []
    for _ in range(2):
        t = ConversationSLATracking(
            policy_id=policy.id,
            current_tier=1,
            due_at=datetime(2026, 1, 2, 9, 0, 0),
        )
        db.add(t)
        made.append(t)
    db.flush()
    db.commit()
    return {"track_a": made[0].id, "track_b": made[1].id, "user_id": user.id}


def _event(db, tracking_id, event_type, event_at, assigned_to_id=None):
    eid = str(uuid.uuid4())
    db.add(ConversationSLAEventLog(
        id=eid,
        sla_tracking_id=tracking_id,
        event_type=event_type,
        event_at=event_at,
        created_at=event_at,
        assigned_to_id=assigned_to_id,
    ))
    db.commit()
    return eid


def test_backfill_sets_prior_assignee_and_leaves_no_prior_null(db, tracking):
    import scripts.backfill_escalation_from_assignee as bf

    bf.SessionLocal = lambda: db
    orig_close = db.close
    db.close = lambda: None
    try:
        base = datetime(2026, 1, 1, 9, 0, 0)
        user_id = tracking["user_id"]
        # Tracking A: a prior 'response' event owned by U1, then an escalation (NULL from).
        track_a = tracking["track_a"]
        _event(db, track_a, "response", base, assigned_to_id=user_id)
        esc_a = _event(db, track_a, "escalation", base + timedelta(hours=2))
        # Tracking B: a lone escalation with no prior event.
        track_b = tracking["track_b"]
        esc_b = _event(db, track_b, "escalation", base)

        summary = bf.run()
        assert summary["from_assigned_to_id_set"] == 1
        assert summary["left_null_no_prior_assignee"] == 1

        assert db.query(ConversationSLAEventLog).get(esc_a).from_assigned_to_id == user_id
        assert db.query(ConversationSLAEventLog).get(esc_b).from_assigned_to_id is None

        # Idempotent: a second run sets nothing more.
        second = bf.run()
        assert second["from_assigned_to_id_set"] == 0
    finally:
        db.close = orig_close
