"""Takeover (clock-preserving, team re-derived) and Reassign (team+clock kept)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.access import (
    AccessAgent,
    AgentTeam,
    AgentTeamRoundRobinCursor,
    RespondContact,
    Team,
    TeamMember,
)
from app.models.integration import IntegrationLog
from app.models.lookup import LookupBinding
from app.models.sla import (
    ConversationSLAEventLog,
    ConversationSLATracking,
    SlaTakeoverRequest,
    SLAPolicy,
    SLAPolicyTier,
)
from app.models.user import User
from app.services.error_handler import AppException
from app.services.sla_service import ConversationSLATrackingService


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from sqlalchemy import JSON

    for col in RespondContact.__table__.columns:
        if col.name == "session_vars":
            col.type = JSON()
            col.server_default = None
    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            AccessAgent.__table__,
            Team.__table__,
            TeamMember.__table__,
            AgentTeam.__table__,
            AgentTeamRoundRobinCursor.__table__,
            SLAPolicy.__table__,
            SLAPolicyTier.__table__,
            ConversationSLATracking.__table__,
            ConversationSLAEventLog.__table__,
            SlaTakeoverRequest.__table__,
            RespondContact.__table__,
            IntegrationLog.__table__,
            LookupBinding.__table__,
        ],
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _user(db, name, respond_user_id=None) -> str:
    uid = str(uuid.uuid4())
    db.add(
        User(
            id=uid,
            email=f"{name}@x.com",
            name=name,
            status="active",
            respond_user_id=respond_user_id,
        )
    )
    db.commit()
    return uid


def _team(db, name, parent_id=None) -> str:
    tid = str(uuid.uuid4())
    db.add(Team(id=tid, name=name, parent_team_id=parent_id))
    db.commit()
    return tid


def _member(db, team_id, user_id):
    db.add(TeamMember(id=str(uuid.uuid4()), team_id=team_id, user_id=user_id))
    db.commit()


def _agent(db) -> str:
    aid = str(uuid.uuid4())
    db.add(AccessAgent(id=aid, code="a", name="A"))
    db.commit()
    return aid


def _agent_team(db, agent_id, team_id, code="cs", tier=1):
    db.add(
        AgentTeam(id=str(uuid.uuid4()), agent_id=agent_id, code=code, team_id=team_id, tier=tier)
    )
    db.commit()


def _policy(db) -> str:
    pid = str(uuid.uuid4())
    db.add(SLAPolicy(id=pid, code="p", name="Policy"))
    db.commit()
    return pid


def _track(db, pid, *, assignee, src="stock_inquiry", contact_id=None):
    tid = str(uuid.uuid4())
    due = datetime(2026, 6, 1, 14, 0, 0)
    started = datetime(2026, 6, 1, 9, 0, 0)
    db.add(
        ConversationSLATracking(
            id=tid,
            policy_id=pid,
            current_tier=1,
            assigned_to_id=assignee,
            current_tier_started_at=started,
            due_at=due,
            due_at_resolution=datetime(2026, 6, 2, 9, 0, 0),
            is_resolved=False,
            source_entity_type=src,
            source_entity_id=str(uuid.uuid4()),
            respond_contact_id=contact_id,
        )
    )
    db.commit()
    return tid


def _logs(db, tid):
    return db.query(ConversationSLAEventLog).filter(
        ConversationSLAEventLog.sla_tracking_id == tid
    ).all()


# ---- takeover -------------------------------------------------------------

@patch("app.services.sla_service.ConversationSLATrackingService._notify_reassignment")
def test_takeover_assigns_me_rederives_team_keeps_clock(notify, db):
    pid = _policy(db)
    me = _user(db, "me", respond_user_id="r-me")
    peer = _user(db, "peer", respond_user_id="r-peer")
    team = _team(db, "Product")
    _member(db, team, me)
    _member(db, team, peer)
    agent_id = _agent(db)
    _agent_team(db, agent_id, team, code="product_set", tier=2)
    tid = _track(db, pid, assignee=peer, src="complaint")  # form -> no Respond push

    svc = ConversationSLATrackingService(db)
    tracking = svc.takeover(tid, me, team)

    assert tracking.assigned_to_id == me
    assert tracking.assigned_to == "r-me"
    assert tracking.agent_id == agent_id
    assert tracking.team_set_code == "product_set"
    assert tracking.current_tier == 2  # re-derived from the team link tier
    # Clock unchanged
    assert tracking.due_at == datetime(2026, 6, 1, 14, 0, 0)
    assert tracking.current_tier_started_at == datetime(2026, 6, 1, 9, 0, 0)
    # reassignment log, manual, triggered/assigned = me, reason takeover
    logs = _logs(db, tid)
    assert len(logs) == 1
    assert logs[0].event_type == "reassignment"
    assert logs[0].trigger == "manual"
    assert logs[0].triggered_by_id == me
    assert logs[0].assigned_to_id == me
    assert logs[0].reason == "takeover"
    # RR cursor advanced to me
    cur = (
        db.query(AgentTeamRoundRobinCursor)
        .filter(
            AgentTeamRoundRobinCursor.agent_id == agent_id,
            AgentTeamRoundRobinCursor.team_id == team,
        )
        .first()
    )
    assert cur is not None and cur.last_assigned_user_id == me


@patch("app.services.sla_service.ConversationSLATrackingService._notify_reassignment")
def test_takeover_uses_takers_own_tier_in_agent_chain(notify, db):
    """A tier-3 approver who takes over a tier-1 task gets it at tier 3 (their own
    standing in the agent chain), NOT the queue team's tier-1. Regression for the
    'takeover dropped me to tier 1' report."""
    pid = _policy(db)
    me = _user(db, "ck", respond_user_id="r-ck")        # tier-3 approver
    peer = _user(db, "abdul", respond_user_id="r-abdul")  # tier-1 handler
    agent_id = _agent(db)
    queue_team = _team(db, "Project Sales Manager")       # tier-1 queue (assignee's)
    ck_team = _team(db, "PR Approvers")                   # tier-3 (taker's)
    _member(db, queue_team, peer)
    _member(db, queue_team, me)   # shared team -> me can see peer's task (visibility)
    _member(db, ck_team, me)
    # Distinct codes per tier: sqlite ignores the partial unique predicate and would
    # reject two same-code rows (prod/postgres allows them). The fix keys on
    # agent_id + team_id, not code, so this still proves taker-tier selection.
    _agent_team(db, agent_id, queue_team, code="pr_t1", tier=1)
    _agent_team(db, agent_id, ck_team, code="pr_appr", tier=3)
    # task currently at tier 1 under the queue team, in this agent's chain
    tid = _track(db, pid, assignee=peer, src="purchase_request")
    db.query(ConversationSLATracking).filter(ConversationSLATracking.id == tid).update(
        {"agent_id": agent_id, "current_tier": 1}
    )
    db.commit()

    # FE passes the queue (assignee's) team_id — but the result must follow MY tier.
    tracking = ConversationSLATrackingService(db).takeover(tid, me, queue_team)

    assert tracking.assigned_to_id == me
    assert tracking.current_tier == 3, "taker's tier-3 standing should win, not queue tier-1"
    assert tracking.team_set_code == "pr_appr"
    assert tracking.agent_id == agent_id
    # RR cursor advanced on the taker's resolved team, not the queue team
    cur = (
        db.query(AgentTeamRoundRobinCursor)
        .filter(
            AgentTeamRoundRobinCursor.agent_id == agent_id,
            AgentTeamRoundRobinCursor.team_id == ck_team,
        )
        .first()
    )
    assert cur is not None and cur.last_assigned_user_id == me


@patch("app.services.sla_service.ConversationSLATrackingService._notify_reassignment")
def test_takeover_conversation_pushes_respond_and_logs_success(notify, db):
    pid = _policy(db)
    me = _user(db, "me", respond_user_id="r-me")
    peer = _user(db, "peer")
    team = _team(db, "T")
    _member(db, team, me)
    _member(db, team, peer)
    agent_id = _agent(db)
    _agent_team(db, agent_id, team)
    contact = RespondContact(
        id=str(uuid.uuid4()), phone_number="+601", respond_io_id="rio-1", session_vars={}
    )
    db.add(contact)
    db.commit()
    tid = _track(db, pid, assignee=peer, src=None, contact_id=contact.id)

    with patch("app.services.integration_service.RespondClient.for_identifier") as fi:
        client = MagicMock()
        fi.return_value = client
        ConversationSLATrackingService(db).takeover(tid, me, team)
        client.set_conversation_assignee.assert_called_once_with("rio-1", "r-me")

    log = db.query(IntegrationLog).filter(IntegrationLog.business_id == tid).first()
    assert log is not None
    assert log.status == "success"
    assert log.integration_channel == "respond_io"


@patch("app.services.sla_service.ConversationSLATrackingService._notify_reassignment")
def test_takeover_conversation_respond_failure_still_succeeds_logs_failure(notify, db):
    pid = _policy(db)
    me = _user(db, "me", respond_user_id="r-me")
    peer = _user(db, "peer")
    team = _team(db, "T")
    _member(db, team, me)
    _member(db, team, peer)
    agent_id = _agent(db)
    _agent_team(db, agent_id, team)
    contact = RespondContact(
        id=str(uuid.uuid4()), phone_number="+602", respond_io_id="rio-2", session_vars={}
    )
    db.add(contact)
    db.commit()
    tid = _track(db, pid, assignee=peer, src=None, contact_id=contact.id)

    with patch("app.services.integration_service.RespondClient.for_identifier") as fi:
        client = MagicMock()
        client.set_conversation_assignee.side_effect = RuntimeError("401 unauthorized")
        fi.return_value = client
        tracking = ConversationSLATrackingService(db).takeover(tid, me, team)
        assert tracking.assigned_to_id == me  # no 500; takeover applied

    log = db.query(IntegrationLog).filter(IntegrationLog.business_id == tid).first()
    assert log is not None and log.status == "failed"
    assert "401" in (log.error_message or "")


@patch("app.services.sla_service.ConversationSLATrackingService._notify_reassignment")
def test_takeover_form_skips_respond_push(notify, db):
    pid = _policy(db)
    me = _user(db, "me", respond_user_id="r-me")
    peer = _user(db, "peer")
    team = _team(db, "T")
    _member(db, team, me)
    _member(db, team, peer)
    agent_id = _agent(db)
    _agent_team(db, agent_id, team)
    tid = _track(db, pid, assignee=peer, src="purchase_request")

    with patch("app.services.integration_service.RespondClient.for_identifier") as fi:
        ConversationSLATrackingService(db).takeover(tid, me, team)
        fi.assert_not_called()
    assert db.query(IntegrationLog).filter(IntegrationLog.business_id == tid).count() == 0


@patch("app.services.sla_service.ConversationSLATrackingService._notify_reassignment")
def test_takeover_taker_without_respond_id_skips_push(notify, db):
    pid = _policy(db)
    me = _user(db, "me", respond_user_id=None)  # no respond mapping
    peer = _user(db, "peer")
    team = _team(db, "T")
    _member(db, team, me)
    _member(db, team, peer)
    agent_id = _agent(db)
    _agent_team(db, agent_id, team)
    contact = RespondContact(
        id=str(uuid.uuid4()), phone_number="+603", respond_io_id="rio-3", session_vars={}
    )
    db.add(contact)
    db.commit()
    tid = _track(db, pid, assignee=peer, src=None, contact_id=contact.id)

    with patch("app.services.integration_service.RespondClient.for_identifier") as fi:
        tracking = ConversationSLATrackingService(db).takeover(tid, me, team)
        fi.assert_not_called()  # skipped: no respond_user_id
        assert tracking.assigned_to_id == me
    assert db.query(IntegrationLog).filter(IntegrationLog.business_id == tid).count() == 0


def test_takeover_blocked_when_not_visible(db):
    pid = _policy(db)
    me = _user(db, "me")
    outsider = _user(db, "outsider")
    my_team = _team(db, "Mine")
    other = _team(db, "Other")
    _member(db, my_team, me)
    _member(db, other, outsider)
    agent_id = _agent(db)
    _agent_team(db, agent_id, other)
    tid = _track(db, pid, assignee=outsider, src="complaint")

    with pytest.raises(AppException):
        ConversationSLATrackingService(db).takeover(tid, me, other)


# ---- reassign -------------------------------------------------------------

@patch("app.services.sla_service.ConversationSLATrackingService._notify_reassignment")
def test_reassign_keeps_team_tier_clock_when_target_not_in_agent_chain(notify, db):
    """Target not in the task's agent chain (or task has no agent) -> tier/team
    left as-is; only the assignee + clocks-preserved invariant hold."""
    pid = _policy(db)
    me = _user(db, "me")
    target = _user(db, "tay", respond_user_id="r-tay")
    team = _team(db, "T")
    _member(db, team, me)
    _member(db, team, target)
    tid = _track(db, pid, assignee=me, src="complaint")  # no agent_id on the task
    # seed a team_set/tier to assert it is unchanged
    t = db.query(ConversationSLATracking).filter(ConversationSLATracking.id == tid).first()
    t.team_set_code = "orig_set"
    t.current_tier = 2
    db.commit()

    tracking = ConversationSLATrackingService(db).reassign(tid, me, target)
    assert tracking.assigned_to_id == target
    assert tracking.assigned_to == "r-tay"
    assert tracking.team_set_code == "orig_set"
    assert tracking.current_tier == 2
    assert tracking.due_at == datetime(2026, 6, 1, 14, 0, 0)
    assert tracking.current_tier_started_at == datetime(2026, 6, 1, 9, 0, 0)

    logs = _logs(db, tid)
    assert len(logs) == 1
    assert logs[0].event_type == "reassignment"
    assert logs[0].trigger == "manual"
    assert logs[0].triggered_by_id == me
    assert logs[0].assigned_to_id == target
    assert logs[0].reason == "reassign"


@patch("app.services.sla_service.ConversationSLATrackingService._notify_reassignment")
def test_reassign_rederives_target_tier_in_agent_chain(notify, db):
    """Handing a tier-3 task to a tier-2 member moves it to tier 2 (target's own
    standing in the task's agent chain). Clocks preserved, same agent."""
    pid = _policy(db)
    me = _user(db, "me")
    target = _user(db, "baser", respond_user_id="r-baser")  # tier-2 in complaint agent
    agent_id = _agent(db)
    my_team = _team(db, "Approvers")          # tier-3 (current task tier)
    # tier-2 team is a CHILD of my team -> target is scope-B visible to me without
    # being in the tier-3 team (so their only standing in the agent is tier 2).
    baser_team = _team(db, "Complaint T2", parent_id=my_team)
    _member(db, my_team, me)
    _member(db, baser_team, target)
    # distinct codes per tier (sqlite ignores the partial-unique predicate)
    _agent_team(db, agent_id, my_team, code="cmp_t3", tier=3)
    _agent_team(db, agent_id, baser_team, code="cmp_t2", tier=2)
    tid = _track(db, pid, assignee=me, src="complaint")
    db.query(ConversationSLATracking).filter(ConversationSLATracking.id == tid).update(
        {"agent_id": agent_id, "current_tier": 3, "team_set_code": "cmp_t3"}
    )
    db.commit()

    tracking = ConversationSLATrackingService(db).reassign(tid, me, target)
    assert tracking.assigned_to_id == target
    assert tracking.current_tier == 2, "should follow the target's tier-2 standing"
    assert tracking.team_set_code == "cmp_t2"
    assert tracking.agent_id == agent_id
    # clocks preserved
    assert tracking.due_at == datetime(2026, 6, 1, 14, 0, 0)
    assert tracking.current_tier_started_at == datetime(2026, 6, 1, 9, 0, 0)


def test_reassign_scope_b_enforced(db):
    pid = _policy(db)
    me = _user(db, "me")
    outsider = _user(db, "outsider")
    my_team = _team(db, "Mine")
    other = _team(db, "Other")
    _member(db, my_team, me)
    _member(db, other, outsider)
    tid = _track(db, pid, assignee=me, src="complaint")

    with pytest.raises(AppException):
        ConversationSLATrackingService(db).reassign(tid, me, outsider)
