"""TCK-2026-000028 — form SLA auto-scan tier-progression fix + manual escalate.

Covers AC-28-F1 (tier2->3), F2 (self-idempotent), F3 (top-tier stop),
F4 (manual), F5 (422 guards + unchanged), F6/B1 (shape + trigger), D1 (trigger cols).

Assignee resolution (AccessAgentService) and _notify_assignee are monkeypatched —
this isolates the escalation/tier logic, which is what TCK-28 changes.

Run: pytest tests/test_form_sla_manual_escalate.py -v
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.models.access import AccessAgent, RespondContact
from app.models.sla import (
    ConversationSLAEventLog,
    ConversationSLATracking,
    SLAPolicy,
    SLAPolicyTier,
)
from app.models.user import User
import app.services.form_sla_service as fss
from app.services.form_sla_service import FormSLAOrchestrator, FormEscalationBlocked
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


@pytest.fixture
def seed(db):
    policy_id = str(uuid.uuid4())
    db.add(SLAPolicy(id=policy_id, code="FORM", name="Form"))
    for lvl in (1, 2, 3):
        db.add(SLAPolicyTier(
            id=str(uuid.uuid4()), policy_id=policy_id, tier_level=lvl,
            tier_name=f"Tier {lvl}", response_hours=4, resolution_hours=24,
        ))
    # agent_id on the tracker is a real FK to access_agents; Postgres enforces it,
    # so the parent row has to exist (sqlite let a loose UUID through).
    agent_id = str(uuid.uuid4())
    db.add(AccessAgent(id=agent_id, code="complaint", name="Complaint"))
    user_id = str(uuid.uuid4())
    db.add(User(id=user_id, email="lead@test.com", name="Lead", respond_user_id="rid-1"))
    actor_id = str(uuid.uuid4())
    db.add(User(id=actor_id, email="actor@test.com", name="Actor"))
    db.commit()
    return {"policy_id": policy_id, "user_id": user_id, "actor_id": actor_id, "agent_id": agent_id}


@pytest.fixture(autouse=True)
def _patch_assignee_and_notify(monkeypatch, seed):
    from app.services.user_service import AccessAgentService

    monkeypatch.setattr(AccessAgentService, "get_team_id_by_tier", lambda self, a, t, team_set_code=None: "team-1")
    monkeypatch.setattr(
        AccessAgentService, "get_next_assignee",
        lambda self, a, t: {"id": seed["user_id"], "respond_user_id": "rid-1"},
    )
    # Isolate from entity-number table lookups / notifications.
    monkeypatch.setattr(FormSLAOrchestrator, "_notify_assignee", lambda self, *a, **k: None)


def _tracker(db, seed, *, tier, overdue, resolved=False, entity="complaint"):
    now = datetime.utcnow()
    due = now - timedelta(hours=1) if overdue else now + timedelta(hours=10)
    t = ConversationSLATracking(
        id=str(uuid.uuid4()),
        policy_id=seed["policy_id"],
        current_tier=tier,
        initiated_at=now - timedelta(hours=5),
        current_tier_started_at=now - timedelta(hours=5),
        due_at=due,
        due_at_resolution=due,
        is_resolved=resolved,
        source_entity_type=entity,
        source_entity_id=str(uuid.uuid4()),
        agent_id=seed["agent_id"],
    )
    db.add(t)
    db.commit()
    return t


def _events(db, tid):
    return db.query(ConversationSLAEventLog).filter(
        ConversationSLAEventLog.sla_tracking_id == tid
    ).all()


def test_scan_escalates_tier2_to_tier3(db, seed):
    t = _tracker(db, seed, tier=2, overdue=True)
    res = FormSLAOrchestrator(db).scan_overdue_and_escalate()
    db.refresh(t)
    assert t.current_tier == 3
    assert res["escalated"] == 1
    logs = [e for e in _events(db, t.id) if e.event_type == "escalation"]
    assert len(logs) == 1 and logs[0].to_tier == 3 and logs[0].trigger == "auto"
    assert logs[0].triggered_by_id is None


def test_scan_idempotent_after_escalate(db, seed):
    t = _tracker(db, seed, tier=2, overdue=True)
    FormSLAOrchestrator(db).scan_overdue_and_escalate()  # -> tier 3, due pushed future
    res2 = FormSLAOrchestrator(db).scan_overdue_and_escalate()
    db.refresh(t)
    assert t.current_tier == 3
    assert res2["escalated"] == 0
    assert len([e for e in _events(db, t.id) if e.event_type == "escalation"]) == 1


def test_scan_top_tier_no_escalate(db, seed):
    t = _tracker(db, seed, tier=3, overdue=True)  # no tier 4
    res = FormSLAOrchestrator(db).scan_overdue_and_escalate()
    db.refresh(t)
    assert t.current_tier == 3
    assert res["escalated"] == 0 and res["skipped"] == 1


@pytest.mark.parametrize("entity", ["complaint", "stock_inquiry", "purchase_request", "sponsorship_form"])
def test_manual_escalate_all_form_types(db, seed, entity):
    t = _tracker(db, seed, tier=1, overdue=False, entity=entity)  # pre-breach
    out = FormSLAOrchestrator(db).escalate_form_tracking(
        t.id, reason="needs lead now", actor_user_id=seed["actor_id"]
    )
    assert out.current_tier == 2
    logs = [e for e in _events(db, t.id) if e.event_type == "escalation"]
    assert len(logs) == 1
    assert logs[0].trigger == "manual"
    assert logs[0].triggered_by_id == seed["actor_id"]
    assert (logs[0].reason or "").startswith("manual:")


def test_manual_top_tier_422(db, seed):
    t = _tracker(db, seed, tier=3, overdue=False)
    with pytest.raises(FormEscalationBlocked) as e:
        FormSLAOrchestrator(db).escalate_form_tracking(t.id, reason="x", actor_user_id=seed["actor_id"])
    assert e.value.reason_code == "top_tier"


def test_manual_resolved_422(db, seed):
    t = _tracker(db, seed, tier=1, overdue=False, resolved=True)
    with pytest.raises(FormEscalationBlocked) as e:
        FormSLAOrchestrator(db).escalate_form_tracking(t.id, reason="x", actor_user_id=seed["actor_id"])
    assert e.value.reason_code == "resolved"


def test_manual_no_assignee_unchanged(db, seed, monkeypatch):
    from app.services.user_service import AccessAgentService
    monkeypatch.setattr(AccessAgentService, "get_next_assignee", lambda self, a, t: None)
    t = _tracker(db, seed, tier=1, overdue=False)
    with pytest.raises(FormEscalationBlocked) as e:
        FormSLAOrchestrator(db).escalate_form_tracking(t.id, reason="x", actor_user_id=seed["actor_id"])
    assert e.value.reason_code == "no_assignee"
    db.refresh(t)
    assert t.current_tier == 1  # unchanged
    assert len(_events(db, t.id)) == 0


def test_manual_not_found_raises_lookup(db, seed):
    with pytest.raises(LookupError):
        FormSLAOrchestrator(db).escalate_form_tracking(str(uuid.uuid4()), reason="x", actor_user_id=seed["actor_id"])


def test_auto_and_manual_same_shape(db, seed):
    auto = _tracker(db, seed, tier=1, overdue=True)
    FormSLAOrchestrator(db).scan_overdue_and_escalate()
    manual = _tracker(db, seed, tier=1, overdue=False)
    FormSLAOrchestrator(db).escalate_form_tracking(manual.id, reason="r", actor_user_id=seed["actor_id"])
    al = [e for e in _events(db, auto.id) if e.event_type == "escalation"][0]
    ml = [e for e in _events(db, manual.id) if e.event_type == "escalation"][0]
    assert al.from_tier == ml.from_tier == 1 and al.to_tier == ml.to_tier == 2
    assert al.trigger == "auto" and ml.trigger == "manual"
