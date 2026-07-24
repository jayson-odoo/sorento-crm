"""Regression: `list_my_pending` returns the user's FULL unresolved set, not just the
soonest-50.

Bug: the My Pending widget fetched the soonest-50 trackers only. That both
under-counted the badge and — because search filtered client-side over that page — hid
any match past the soonest-50 (a user with 50+ overdue items could never find a
later-due one by number). Fix: return everything (safety-capped), so the widget shows
an honest total and searches/paginates over the complete set.

Run: pytest tests/test_my_pending_server_search.py -v
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.access import AccessAgent, RespondContact
from app.models.sla import (
    ConversationSLAEventLog,
    ConversationSLATracking,
    SLAPolicy,
    SLAPolicyTier,
)
from app.models.user import User
from app.services.form_sla_service import _utc_naive_now
from app.services.sla_service import ConversationSLATrackingService

USER_ID = str(uuid.uuid4())


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.types import JSON as GenericJSON

    for col in list(RespondContact.__table__.columns):
        if isinstance(col.type, JSONB):
            col.type = GenericJSON()
            col.server_default = None

    Base.metadata.create_all(
        engine,
        tables=[
            SLAPolicy.__table__,
            SLAPolicyTier.__table__,
            ConversationSLATracking.__table__,
            ConversationSLAEventLog.__table__,
            User.__table__,
            RespondContact.__table__,
            AccessAgent.__table__,
        ],
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = SessionLocal()
    pid = str(uuid.uuid4())
    s.add(SLAPolicy(id=pid, code="NORMAL", name="Normal"))
    s.add(User(id=USER_ID, email="ck@test.com", name="CK Lee"))
    s.commit()
    try:
        yield s, pid
    finally:
        s.close()


def _add_tracker(db, pid, *, due_days: int, source_type="complaint"):
    now = _utc_naive_now()
    tid = str(uuid.uuid4())
    db.add(
        ConversationSLATracking(
            id=tid,
            policy_id=pid,
            current_tier=1,
            initiated_at=now - timedelta(days=10),
            current_tier_started_at=now - timedelta(days=10),
            due_at=now + timedelta(days=due_days),
            is_responded=False,
            is_resolved=False,
            assigned_to_id=USER_ID,
            source_entity_type=source_type,
            source_entity_id=tid,
        )
    )
    db.commit()
    return tid


def test_returns_full_set_not_just_soonest_window(db):
    """A later-due tracker must be present in the result (the old 50-cap dropped it,
    which is why search — filtering client-side over the page — could never find it)."""
    session, pid = db
    svc = ConversationSLATrackingService(session)

    for _ in range(60):  # more than the old hard cap of 50
        _add_tracker(session, pid, due_days=1)
    target = _add_tracker(session, pid, due_days=99)  # sorts last by due

    ids = [r["id"] for r in svc.list_my_pending(USER_ID)]
    assert len(ids) == 61
    assert target in ids  # would have been dropped under the old soonest-50 fetch


def test_soonest_due_first_order_preserved(db):
    session, pid = db
    svc = ConversationSLATrackingService(session)
    a = _add_tracker(session, pid, due_days=1)
    b = _add_tracker(session, pid, due_days=5)
    ids = [r["id"] for r in svc.list_my_pending(USER_ID)]
    assert ids.index(a) < ids.index(b)


def test_safety_cap_respected(db):
    session, pid = db
    svc = ConversationSLATrackingService(session)
    for _ in range(5):
        _add_tracker(session, pid, due_days=1)
    assert len(svc.list_my_pending(USER_ID, limit=3)) == 3
