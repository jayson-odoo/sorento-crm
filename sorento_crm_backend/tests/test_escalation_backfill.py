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
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.sla import ConversationSLAEventLog


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[ConversationSLAEventLog.__table__])
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


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


def test_backfill_sets_prior_assignee_and_leaves_no_prior_null(db):
    import scripts.backfill_escalation_from_assignee as bf

    bf.SessionLocal = lambda: db
    orig_close = db.close
    db.close = lambda: None
    try:
        base = datetime(2026, 1, 1, 9, 0, 0)
        # Tracking A: a prior 'response' event owned by U1, then an escalation (NULL from).
        track_a = str(uuid.uuid4())
        _event(db, track_a, "response", base, assigned_to_id="user-1")
        esc_a = _event(db, track_a, "escalation", base + timedelta(hours=2))
        # Tracking B: a lone escalation with no prior event.
        track_b = str(uuid.uuid4())
        esc_b = _event(db, track_b, "escalation", base)

        summary = bf.run()
        assert summary["from_assigned_to_id_set"] == 1
        assert summary["left_null_no_prior_assignee"] == 1

        assert db.query(ConversationSLAEventLog).get(esc_a).from_assigned_to_id == "user-1"
        assert db.query(ConversationSLAEventLog).get(esc_b).from_assigned_to_id is None

        # Idempotent: a second run sets nothing more.
        second = bf.run()
        assert second["from_assigned_to_id_set"] == 0
    finally:
        db.close = orig_close
