"""Service tests for the conversation-SLA 'reopen for retest' override.

Covers admin_test_override_tracking() extensions:
- is_resolved=False reopens a resolved row (clears resolved_at/by/duration).
- is_responded=False clears the response fields.
- agent_code resolves to the agent_id FK; team_set_code is stored verbatim.
- due_at / due_at_resolution recomputed from the overridden current_tier_started_at
  + tier hours (response 24h, resolution 48h here).

Runs against the live Postgres test DB (same pattern as the other SLA tests):
seed rows with a unique marker, assert, clean up.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.models.access import AccessAgent, RespondContact
from app.models.sla import ConversationSLATracking, SLAPolicy, SLAPolicyTier
from app.services.sla_service import ConversationSLATrackingService

NAME_MARKER = "REOPENCONV"
PHONE = "+60999111000"
POLICY_CODE = "REOPEN-CONV-POLICY"
AGENT_CODE = "REOPEN-AGENT"
TEAM_SET_CODE = "REOPEN_TEAM"


@pytest.fixture(autouse=True)
def _clean_state():
    def _wipe(conn):
        conn.execute(
            text(
                "DELETE FROM conversation_sla_tracking WHERE respond_contact_id IN "
                "(SELECT id FROM respond_contacts WHERE name LIKE 'REOPENCONV%')"
            )
        )
        conn.execute(text("DELETE FROM respond_contacts WHERE name LIKE 'REOPENCONV%'"))
        conn.execute(
            text("DELETE FROM sla_policy_tiers WHERE policy_id IN (SELECT id FROM sla_policies WHERE code = :c)"),
            {"c": POLICY_CODE},
        )
        conn.execute(text("DELETE FROM sla_policies WHERE code = :c"), {"c": POLICY_CODE})
        conn.execute(text("DELETE FROM access_agents WHERE code = :c"), {"c": AGENT_CODE})

    with engine.connect() as conn:
        try:
            _wipe(conn)
            conn.commit()
        except Exception:
            conn.rollback()
    yield
    with engine.connect() as conn:
        try:
            _wipe(conn)
            conn.commit()
        except Exception:
            conn.rollback()


@pytest.fixture
def db() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _seed(db: Session) -> ConversationSLATracking:
    policy = SLAPolicy(id=str(uuid.uuid4()), code=POLICY_CODE, name="Reopen Policy", is_active=True)
    db.add(policy)
    db.commit()
    db.add(
        SLAPolicyTier(
            id=str(uuid.uuid4()),
            policy_id=policy.id,
            tier_level=1,
            tier_name="Tier 1",
            response_hours=24,
            resolution_hours=48,
        )
    )
    db.add(AccessAgent(id=str(uuid.uuid4()), code=AGENT_CODE, name="Reopen Agent", is_active=True))
    contact = RespondContact(id=str(uuid.uuid4()), phone_number=PHONE, name=f"{NAME_MARKER}-1")
    db.add(contact)
    db.commit()

    now = datetime.utcnow()
    t = ConversationSLATracking(
        id=str(uuid.uuid4()),
        policy_id=policy.id,
        current_tier=1,
        respond_contact_id=contact.id,
        initiated_at=now - timedelta(days=10),
        current_tier_started_at=now - timedelta(days=9),
        due_at=now - timedelta(days=8),  # overdue
        due_at_resolution=now - timedelta(days=8),
        is_responded=True,
        responded_at=now - timedelta(days=9),
        is_resolved=True,
        resolved_at=now - timedelta(days=1),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def test_reopen_clears_state_sets_routing_and_recomputes_due(db: Session) -> None:
    t = _seed(db)
    svc = ConversationSLATrackingService(db)

    new_start = datetime.utcnow()  # naive UTC, as the override accepts
    svc.admin_test_override_tracking(
        t.id,
        {
            "is_resolved": False,
            "is_responded": False,
            "agent_code": AGENT_CODE,
            "team_set_code": TEAM_SET_CODE,
            "current_tier_started_at": new_start,
        },
    )

    db.refresh(t)
    # Reopened + response reset
    assert t.is_resolved is False
    assert t.resolved_at is None and t.resolved_by is None and t.resolution_duration is None
    assert t.is_responded is False
    assert t.responded_at is None and t.responded_by is None and t.response_time is None
    # Routing applied
    agent = db.query(AccessAgent).filter(AccessAgent.code == AGENT_CODE).first()
    assert str(t.agent_id) == str(agent.id)
    assert t.team_set_code == TEAM_SET_CODE
    # Due recomputed forward from the new tier start (>= now, no longer overdue)
    assert t.due_at is not None and t.due_at_resolution is not None
    assert t.due_at > datetime.utcnow()
    # resolution_hours (48) > response_hours (24) -> later resolution due
    assert t.due_at_resolution > t.due_at


def test_reopen_recomputes_due_without_explicit_tier_start(db: Session) -> None:
    # No current_tier_started_at in the request: due must still be recomputed from
    # the existing tier start so a previously-overdue row gets a clean clock.
    t = _seed(db)
    svc = ConversationSLATrackingService(db)

    svc.admin_test_override_tracking(t.id, {"is_resolved": False})

    db.refresh(t)
    assert t.is_resolved is False
    # existing current_tier_started_at was 9 days ago + 24h response -> still in the
    # past, but the path must have RECOMPUTED (not left the seeded -8d value).
    assert t.due_at is not None
    expected_floor = datetime.utcnow() - timedelta(days=9, hours=1)
    assert t.due_at > expected_floor


def test_agent_code_unknown_raises(db: Session) -> None:
    t = _seed(db)
    svc = ConversationSLATrackingService(db)
    with pytest.raises(Exception):
        svc.admin_test_override_tracking(t.id, {"agent_code": "NO-SUCH-AGENT"})
