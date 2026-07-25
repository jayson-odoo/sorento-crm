"""Form-banner person links — escalated-FROM snapshot on the event log (UAC ESC-1/ESC-2).

Both escalation write paths overwrite ``assigned_to_id`` before logging, so the
escalation event log must snapshot the PRIOR owner into the new
``from_assigned_to_id`` column BEFORE the overwrite:

- ESC-1: conversation path ``ConversationSLATrackingService.escalate_tracking``.
- ESC-2: form path ``FormSLAOrchestrator._escalate_tracker``.

Run: pytest tests/test_sla_escalation_from_snapshot.py -v
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.models.access import AccessAgent, RespondContact
from app.models.sla import (
    SLAPolicy,
    SLAPolicyTier,
    ConversationSLATracking,
    ConversationSLAEventLog,
)
from app.models.user import User
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _user(db, name):
    uid = str(uuid.uuid4())
    db.add(User(id=uid, email=f"{name}@t.com", name=name))
    db.commit()
    return uid


def _policy_with_tiers(db):
    pid = str(uuid.uuid4())
    db.add(SLAPolicy(id=pid, code=f"P-{pid[:6]}", name="Policy"))
    for lvl in (1, 2, 3):
        db.add(SLAPolicyTier(
            id=str(uuid.uuid4()),
            policy_id=pid,
            tier_level=lvl,
            tier_name=f"T{lvl}",
            response_hours=4,
            resolution_hours=24,
        ))
    db.commit()
    return pid


# ---- ESC-1 conversation path -------------------------------------------
def test_conversation_escalate_snapshots_prior_owner(db):
    from app.services.sla_service import ConversationSLATrackingService

    prev = _user(db, "tier1")
    nxt = _user(db, "tier2")
    cid = str(uuid.uuid4())
    db.add(RespondContact(id=cid, phone_number="60123456789", name="C", session_vars={}))
    pid = _policy_with_tiers(db)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    tid = str(uuid.uuid4())
    db.add(ConversationSLATracking(
        id=tid,
        policy_id=pid,
        current_tier=1,
        assigned_to_id=prev,
        due_at=now,
        respond_contact_id=cid,
        source_entity_type=None,  # conversation-scoped
    ))
    db.commit()

    svc = ConversationSLATrackingService(db)
    svc.escalate_tracking(
        respond_contact_id=cid,
        policy_id=pid,
        current_tier=2,
        assigned_to_id=nxt,
    )

    # New assignee applied on the tracker...
    db.refresh(db.query(ConversationSLATracking).get(tid))
    tracker = db.query(ConversationSLATracking).get(tid)
    assert tracker.assigned_to_id == nxt

    # ...but the escalation event log snapshots the PRIOR owner.
    esc = (
        db.query(ConversationSLAEventLog)
        .filter(
            ConversationSLAEventLog.sla_tracking_id == tid,
            ConversationSLAEventLog.event_type == "escalation",
        )
        .first()
    )
    assert esc is not None
    assert esc.from_assigned_to_id == prev
    assert esc.assigned_to_id == nxt


# ---- ESC-2 form path ----------------------------------------------------
def test_form_escalate_snapshots_prior_owner(db):
    from app.services import user_service as user_svc_mod
    from app.services import coverage_subscription_service as cov_mod
    from app.services.form_sla_service import FormSLAOrchestrator

    prev = _user(db, "form_prev")
    nxt = _user(db, "form_next")
    pid = _policy_with_tiers(db)
    # agent_id FKs to access_agents -- Postgres enforces it, so seed the parent.
    agent_id = str(uuid.uuid4())
    db.add(AccessAgent(id=agent_id, code=f"AG-{agent_id[:6]}", name="Agent"))
    db.commit()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    tid = str(uuid.uuid4())
    db.add(ConversationSLATracking(
        id=tid,
        policy_id=pid,
        current_tier=1,
        assigned_to_id=prev,
        due_at=now,
        source_entity_type="complaint",
        source_entity_id="1378f157-23bd-5ed3-8dd5-51b64b8a108d",
        agent_id=agent_id,
        team_set_code=None,
    ))
    db.commit()
    tracker = db.query(ConversationSLATracking).get(tid)

    orch = FormSLAOrchestrator(db)

    class _FakeAgentSvc:
        def __init__(self, *a, **k):
            pass

        def resolve_team_with_tier_fallback(self, agent_id, target_tier, team_set_code=None):
            return ("team-2", 2)

        def get_next_assignee(self, agent_id, team_id):
            return {"id": nxt, "respond_user_id": None, "name": "form_next"}

    with patch.object(user_svc_mod, "AccessAgentService", _FakeAgentSvc), patch.object(
        cov_mod, "resolve_assignee_with_coverage",
        lambda db_, a: (a, None),
    ), patch.object(orch, "_stage_notifies_on_escalation", return_value=False), patch.object(
        orch, "_notify_assignee", return_value=None
    ):
        orch._escalate_tracker(tracker, trigger="manual", reason="please escalate")

    db.commit()
    esc = (
        db.query(ConversationSLAEventLog)
        .filter(
            ConversationSLAEventLog.sla_tracking_id == tid,
            ConversationSLAEventLog.event_type == "escalation",
        )
        .first()
    )
    assert esc is not None
    assert esc.from_assigned_to_id == prev
    assert esc.assigned_to_id == nxt
    assert db.query(ConversationSLATracking).get(tid).assigned_to_id == nxt
