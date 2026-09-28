"""An undo puts the stage back with the clock it had, extension included (#1326).

Replays CMP26-0288 end to end at the service layer, through the real code paths:

  10:23  Magen extends the Tier 1 complaint clock by 30 working days
         (`ConversationSLATrackingService.extend_tracking`)
  11:42  Magen applies `cx.decide` = approved through the form-action dispatcher:
         the complaint stage resolves and a customer_service stage opens
  11:42  the decision is undone (`FormActionService.undo`): the customer_service
         stage is voided and the complaint stage reopened
  +3 wd  the form-SLA escalation job runs (`scan_overdue_and_escalate`)

Before the fix `reopen_tracker` rebuilt the reopened clock from now + the tier's
hours, so the 30-day extension vanished and the job escalated the complaint three
working days later (Tier 1 -> 2 -> 3, CK Lee).

The proven path is pinned beside it: a stage that was NEVER extended keeps today's
behaviour, the clock restarting from the undo moment against the stage's own hours
(AC-PGE-3 in documentation/plans/_archive/UAC-form-sla-undo.md).

Postgres only (`blank_session`): the outer transaction is rolled back, so the
commits made by the code under test are discarded.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from tests._pg_fixture import blank_session

MARKER = "zzt-undoext-"


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


def _user(db, name):
    from app.models.user import User

    user = User(
        id=str(uuid.uuid4()),
        email=f"{MARKER}{uuid.uuid4().hex[:8]}@example.test",
        name=name,
        status="ACTIVE",
    )
    db.add(user)
    db.commit()
    return user


def _chain(db):
    """Policy (Tier 1: 72h = 3 working days), agent, complaint stage -> customer_service."""
    from app.models.access import AccessAgent
    from app.models.sla import FormSLAConfig, SLAPolicy, SLAPolicyTier

    policy = SLAPolicy(id=str(uuid.uuid4()), code=MARKER + uuid.uuid4().hex[:8], name="p")
    db.add(policy)
    db.flush()
    for level in (1, 2, 3):
        db.add(
            SLAPolicyTier(
                id=str(uuid.uuid4()),
                policy_id=policy.id,
                tier_level=level,
                tier_name=f"Tier {level}",
                response_hours=72,
                resolution_hours=72,
            )
        )
    agent = AccessAgent(id=str(uuid.uuid4()), code=MARKER + "agent", name="agent")
    db.add(agent)
    db.flush()
    cs = FormSLAConfig(
        id=str(uuid.uuid4()),
        source_entity_type="complaint",
        stage_code=MARKER + "cs",
        policy_id=policy.id,
        agent_code=agent.code,
        team_set_code=MARKER + "cs",
        start_event="approved",
        resolve_event="resolved",
        is_active=True,
    )
    db.add(cs)
    db.flush()
    main = FormSLAConfig(
        id=str(uuid.uuid4()),
        source_entity_type="complaint",
        stage_code=MARKER + "main",
        policy_id=policy.id,
        agent_code=agent.code,
        team_set_code=MARKER + "tech",
        start_event="submit",
        resolve_event="approved,rejected",
        advance_on_event="approved",
        next_config_id=cs.id,
        is_active=True,
    )
    db.add(main)
    db.commit()
    return policy, agent, main


def _complaint_with_stage(db, *, policy, agent, main, magen):
    """A responded complaint whose Tier 1 technical stage is with Magen.

    The stage started an hour ago and is due in two days: the "25/09 08:00" the
    extension's `from_time` names on CMP26-0288.
    """
    from app.models.complaints import Complaint
    from app.models.sla import ConversationSLATracking

    complaint = Complaint(
        id=str(uuid.uuid4()),
        complaint_number=f"{MARKER}{uuid.uuid4().hex[:6]}",
        customer_name="ACME",
        status="responded",
    )
    db.add(complaint)
    db.commit()

    now = datetime.utcnow().replace(microsecond=0)
    tracker = ConversationSLATracking(
        id=str(uuid.uuid4()),
        policy_id=policy.id,
        current_tier=1,
        initiated_at=now - timedelta(hours=16),
        current_tier_started_at=now - timedelta(hours=1),
        due_at=now + timedelta(days=2),
        due_at_resolution=now + timedelta(days=2),
        is_responded=True,
        responded_by=magen.id,
        is_resolved=False,
        source_entity_type="complaint",
        source_entity_id=complaint.id,
        team_set_code=main.team_set_code,
        agent_id=agent.id,
        assigned_to_id=magen.id,
    )
    db.add(tracker)
    db.commit()
    return complaint, tracker


def _route_next_stage_to(monkeypatch, user):
    """The customer_service stage lands on `user` without seeding a team roster:
    team resolution is not what this test is about."""
    from app.services.user_service import AccessAgentService

    monkeypatch.setattr(
        AccessAgentService,
        "resolve_team_with_tier_fallback",
        lambda self, agent_id, tier, **kw: (str(uuid.uuid4()), tier),
    )
    monkeypatch.setattr(
        AccessAgentService,
        "get_next_assignee",
        lambda self, agent_id, team_id: {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "respond_user_id": None,
        },
    )


def _decide_then_undo(db, complaint, magen):
    import app.services.form_actions  # noqa: F401 - registers cx.decide
    from app.models.sla import FORM_ACTION_CHANNEL_IMMEDIATE, SlaFormAction
    from app.services.form_action_service import FormActionService

    svc = FormActionService(db)
    svc.dispatch(
        action_key="cx.decide",
        entity_type="complaint",
        entity_id=complaint.id,
        payload={
            "complaint_id": complaint.id,
            "decision": "approved",
            "respond_user_id": "magen-respond-id",
            "crm_sender_user_id": magen.id,
        },
        actor_id=magen.id,
        channel=FORM_ACTION_CHANNEL_IMMEDIATE,
        grace_seconds=0,
    )
    row = (
        db.query(SlaFormAction)
        .filter(SlaFormAction.source_entity_id == complaint.id)
        .one()
    )
    svc.undo(
        source_entity_type="complaint",
        source_entity_id=complaint.id,
        actor_id=magen.id,
        reason="Technician to attend",
        has_permission=True,
    )
    return row


def _escalations_after(db, monkeypatch, *, days):
    """Run the real escalation job `days` from now; return the trackers it escalated.

    The job's rules are untouched: only its clock is moved forward, and the tier
    move itself is recorded instead of performed.
    """
    from app.services import form_sla_service as fss

    later = datetime.utcnow() + timedelta(days=days)
    monkeypatch.setattr(fss, "_utc_naive_now", lambda: later)
    escalated: list[str] = []
    monkeypatch.setattr(
        fss.FormSLAOrchestrator,
        "_escalate_tracker",
        lambda self, tracker, **kw: escalated.append(str(tracker.id)),
    )
    fss.FormSLAOrchestrator(db).scan_overdue_and_escalate()
    return escalated


def test_cmp26_0288_undo_keeps_the_extended_clock(db, monkeypatch):
    """The owner's report, replayed: extend, decide, undo, then the job runs."""
    from app.models.sla import ConversationSLAEventLog, ConversationSLATracking
    from app.services.sla_service import ConversationSLATrackingService

    magen = _user(db, "Magen")
    agnes = _user(db, "Agnes")
    policy, agent, main = _chain(db)
    complaint, tracker = _complaint_with_stage(
        db, policy=policy, agent=agent, main=main, magen=magen
    )
    _route_next_stage_to(monkeypatch, agnes)

    # 10:23 - extend by 30 working days.
    ConversationSLATrackingService(db).extend_tracking(
        tracker.id, magen.id, days=30, reason="Technician to attend and check"
    )
    db.refresh(tracker)
    before = {
        "due_at": tracker.due_at,
        "due_at_resolution": tracker.due_at_resolution,
        "current_tier_started_at": tracker.current_tier_started_at,
        "extension_count": tracker.extension_count,
        "extension_days_total": float(tracker.extension_days_total or 0),
    }
    assert before["extension_count"] == 1
    assert before["due_at_resolution"] > datetime.utcnow() + timedelta(days=30)

    # 11:42 - decide, then undo.
    row = _decide_then_undo(db, complaint, magen)
    assert str(row.prior_tracking_id) == str(tracker.id)
    assert row.spawned_tracking_id, "the decision must have opened a customer_service stage"
    spawned = db.get(ConversationSLATracking, str(row.spawned_tracking_id))
    assert spawned.is_resolved is True, "the customer_service stage is voided by the undo"

    db.expire_all()
    reopened = db.get(ConversationSLATracking, str(tracker.id))
    assert reopened.is_resolved is False
    assert reopened.current_tier == 1
    assert str(reopened.assigned_to_id) == str(magen.id)
    after = {
        "due_at": reopened.due_at,
        "due_at_resolution": reopened.due_at_resolution,
        "current_tier_started_at": reopened.current_tier_started_at,
        "extension_count": reopened.extension_count,
        "extension_days_total": float(reopened.extension_days_total or 0),
    }
    assert after == before, "the undo must restore the clock the stage had before the action"

    events = [
        e.event_type
        for e in db.query(ConversationSLAEventLog)
        .filter(ConversationSLAEventLog.sla_tracking_id == str(tracker.id))
        .order_by(ConversationSLAEventLog.event_at)
    ]
    assert events == ["extend", "reopened"]

    # Three working days later (five calendar days covers any weekend) the job
    # must leave the extended complaint alone.
    assert str(tracker.id) not in _escalations_after(db, monkeypatch, days=5)


def test_undo_of_a_never_extended_stage_still_restarts_the_clock(db, monkeypatch):
    """Proven path, AC-PGE-3: "clock restarted from the undo moment against the
    stage's own hours". No extension, so the ruling stands and the fix must not
    change it."""
    from app.models.sla import ConversationSLATracking

    magen = _user(db, "Magen")
    agnes = _user(db, "Agnes")
    policy, agent, main = _chain(db)
    complaint, tracker = _complaint_with_stage(
        db, policy=policy, agent=agent, main=main, magen=magen
    )
    _route_next_stage_to(monkeypatch, agnes)
    old_started = tracker.current_tier_started_at

    undo_started = datetime.utcnow()
    _decide_then_undo(db, complaint, magen)

    db.expire_all()
    reopened = db.get(ConversationSLATracking, str(tracker.id))
    assert reopened.is_resolved is False
    assert reopened.current_tier_started_at != old_started
    assert reopened.current_tier_started_at >= undo_started.replace(microsecond=0)
    # 72h = 3 working days from the (working-window) restart: past two calendar days.
    assert reopened.due_at_resolution > reopened.current_tier_started_at + timedelta(days=2)
    assert (reopened.extension_count or 0) == 0


def test_an_extension_superseded_by_an_escalation_is_not_restored(db, monkeypatch):
    """Masking condition, disconfirming side: the extension only governs the clock
    while no escalation has replaced it. A stage extended at Tier 1 and then
    escalated to Tier 2 runs on the Tier 2 clock, so an undo restarts that clock
    exactly as a never-extended stage would."""
    from app.models.sla import ConversationSLAEventLog, ConversationSLATracking
    from app.services.form_action_undo import reopen_tracker
    from app.services.sla_service import ConversationSLATrackingService

    magen = _user(db, "Magen")
    policy, agent, main = _chain(db)
    _, tracker = _complaint_with_stage(
        db, policy=policy, agent=agent, main=main, magen=magen
    )
    ConversationSLATrackingService(db).extend_tracking(
        tracker.id, magen.id, days=30, reason="parts on order"
    )
    # An escalation after the extension: Tier 2, fresh clock.
    now = datetime.utcnow().replace(microsecond=0)
    tracker.current_tier = 2
    tracker.current_tier_started_at = now - timedelta(minutes=5)
    tracker.due_at_resolution = now - timedelta(minutes=1)
    tracker.escalated_at = now - timedelta(minutes=5)
    db.add(
        ConversationSLAEventLog(
            sla_tracking_id=str(tracker.id),
            event_type="escalation",
            from_tier=1,
            to_tier=2,
            event_at=now + timedelta(seconds=1),
            trigger="auto",
        )
    )
    tracker.is_resolved = True
    db.commit()

    reopen_tracker(db, str(tracker.id))

    db.expire_all()
    reopened = db.get(ConversationSLATracking, str(tracker.id))
    assert reopened.is_resolved is False
    assert reopened.due_at_resolution > datetime.utcnow() + timedelta(days=2)
    assert reopened.due_at_resolution < datetime.utcnow() + timedelta(days=10)
