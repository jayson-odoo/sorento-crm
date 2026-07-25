"""Per-user pending SLA to-do query (dashboard widget backend)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.models.sla import ConversationSLATracking, SLAPolicy
from app.models.user import User
from app.services.sla_service import ConversationSLATrackingService
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _policy(db) -> str:
    pid = str(uuid.uuid4())
    db.add(SLAPolicy(id=pid, code="lead_time", name="Lead time"))
    db.commit()
    return pid


def _user(db, name) -> str:
    """A real users row -- assigned_to_id is a FK, so the old string
    placeholders ("me"/"other") only worked because sqlite ignored it."""
    uid = str(uuid.uuid4())
    db.add(User(id=uid, email=f"{name}@t.com", name=name))
    db.commit()
    return uid


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
    me, other = _user(db, "me"), _user(db, "other")
    _tracking(db, pid, assigned_to_id=me, is_resolved=False, due_in_h=10)
    _tracking(db, pid, assigned_to_id=me, is_resolved=False, due_in_h=2)
    _tracking(db, pid, assigned_to_id=me, is_resolved=True, due_in_h=1)   # resolved -> excluded
    _tracking(db, pid, assigned_to_id=other, is_resolved=False, due_in_h=1)  # not mine

    out = ConversationSLATrackingService(db).list_my_pending(me)

    assert [r["due_at"] for r in out] == [
        "2026-05-25T02:00:00",
        "2026-05-25T10:00:00",
    ]
    assert all(r["source_entity_type"] == "stock_inquiry" for r in out)
    assert out[0]["policy_name"] == "Lead time"


def test_includes_form_sla_types(db):
    """Form trackers (excluded from the conversation list) must appear here."""
    pid = _policy(db)
    me = _user(db, "me")
    _tracking(db, pid, assigned_to_id=me, is_resolved=False, due_in_h=1, src="complaint")
    out = ConversationSLATrackingService(db).list_my_pending(me)
    assert len(out) == 1
    assert out[0]["source_entity_type"] == "complaint"


def test_empty_when_none_assigned(db):
    _policy(db)
    assert ConversationSLATrackingService(db).list_my_pending("nobody") == []
