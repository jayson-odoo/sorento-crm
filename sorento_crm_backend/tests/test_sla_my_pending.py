"""Per-user pending SLA to-do query (dashboard widget backend)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.sla import ConversationSLATracking, SLAPolicy
from app.services.sla_service import ConversationSLATrackingService


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine, tables=[SLAPolicy.__table__, ConversationSLATracking.__table__]
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _policy(db) -> str:
    pid = str(uuid.uuid4())
    db.add(SLAPolicy(id=pid, code="lead_time", name="Lead time"))
    db.commit()
    return pid


def _tracking(db, policy_id, *, assigned_to_id, is_resolved, due_in_h, src="stock_inquiry"):
    db.add(
        ConversationSLATracking(
            id=str(uuid.uuid4()),
            policy_id=policy_id,
            current_tier=1,
            assigned_to_id=assigned_to_id,
            due_at=datetime(2026, 5, 25) + timedelta(hours=due_in_h),
            is_resolved=is_resolved,
            source_entity_type=src,
            source_entity_id=str(uuid.uuid4()),
        )
    )
    db.commit()


def test_returns_only_my_unresolved_sorted_by_due(db):
    pid = _policy(db)
    _tracking(db, pid, assigned_to_id="me", is_resolved=False, due_in_h=10)
    _tracking(db, pid, assigned_to_id="me", is_resolved=False, due_in_h=2)
    _tracking(db, pid, assigned_to_id="me", is_resolved=True, due_in_h=1)   # resolved -> excluded
    _tracking(db, pid, assigned_to_id="other", is_resolved=False, due_in_h=1)  # not mine

    out = ConversationSLATrackingService(db).list_my_pending("me")

    assert [r["due_at"] for r in out] == [
        "2026-05-25T02:00:00",
        "2026-05-25T10:00:00",
    ]
    assert all(r["source_entity_type"] == "stock_inquiry" for r in out)
    assert out[0]["policy_name"] == "Lead time"


def test_includes_form_sla_types(db):
    """Form trackers (excluded from the conversation list) must appear here."""
    pid = _policy(db)
    _tracking(db, pid, assigned_to_id="me", is_resolved=False, due_in_h=1, src="complaint")
    out = ConversationSLATrackingService(db).list_my_pending("me")
    assert len(out) == 1
    assert out[0]["source_entity_type"] == "complaint"


def test_empty_when_none_assigned(db):
    _policy(db)
    assert ConversationSLATrackingService(db).list_my_pending("nobody") == []
