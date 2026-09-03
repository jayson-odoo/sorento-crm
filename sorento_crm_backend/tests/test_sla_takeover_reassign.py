"""Takeover (clock-preserving, team re-derived) and Reassign (team+clock kept)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

from app.models.access import (
    AccessAgent,
    AgentTeam,
    AgentTeamRoundRobinCursor,
    RespondContact,
    Team,
    TeamMember,
)
from app.models.integration import IntegrationLog
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
from tests import _pg_fixture
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as session:
        # descendant_team_ids() drops to raw text() SQL on Postgres ("FROM teams"),
        # which the engine's schema_translate_map does not rewrite -- unqualified
        # names would resolve against the real public schema and read live rows.
        # SET LOCAL is scoped to the outer transaction, so it unwinds with it.
        blank = _pg_fixture._BLANK["name"]
        session.execute(text(f'SET LOCAL search_path TO "{blank}", "{blank}_scm"'))
        yield session


def _user(db, name, respond_user_id=None) -> str:
    uid = str(uuid.uuid4())
    db.add(
        User(
            id=uid,
            email=f"{name}@x.com",
            name=name,
            status="ACTIVE",
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

    # FE passes the queue (assignee's) team_id - but the result must follow MY tier.
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


# The Respond assignee push is now async: takeover/reassign ENQUEUE a
# set_respond_conversation_assignee job on the respond_io queue (the actual Respond
# call + outbox log run on the worker - see test_respond_conversation_tasks.py).


@patch("app.services.sla_service.ConversationSLATrackingService._notify_reassignment")
def test_takeover_conversation_enqueues_respond_assignee(notify, db):
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

    with patch("app.services.queue_service.enqueue_job") as enqueue:
        ConversationSLATrackingService(db).takeover(tid, me, team)
    enqueue.assert_called_once()
    assert enqueue.call_args.args[0].__name__ == "set_respond_conversation_assignee"
    assert enqueue.call_args.args[1] == tid
    assert enqueue.call_args.args[2] == "r-me"  # the taker's respond_user_id
    assert enqueue.call_args.kwargs["queue_name"] == "respond_io"


@patch("app.services.sla_service.ConversationSLATrackingService._notify_reassignment")
def test_takeover_succeeds_even_if_enqueue_fails(notify, db):
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

    with patch("app.services.queue_service.enqueue_job", side_effect=RuntimeError("redis down")):
        tracking = ConversationSLATrackingService(db).takeover(tid, me, team)
        assert tracking.assigned_to_id == me  # no 500; takeover applied despite enqueue failure


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

    with patch("app.services.queue_service.enqueue_job") as enqueue:
        ConversationSLATrackingService(db).takeover(tid, me, team)
        enqueue.assert_not_called()  # form SLA -> no Respond conversation


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

    with patch("app.services.queue_service.enqueue_job") as enqueue:
        tracking = ConversationSLATrackingService(db).takeover(tid, me, team)
        enqueue.assert_not_called()  # skipped: no respond_user_id
        assert tracking.assigned_to_id == me


@patch("app.services.sla_service.ConversationSLATrackingService._notify_reassignment")
def test_takeover_dual_team_set_prefers_trackings_own_set(notify, db):
    """The taker holds a tier-1 link in BOTH team sets under the same agent - the
    per-team-set invariant allows this (PLAN-tier1-teamset-invariant). Deterministic
    (tier desc, code asc) ordering alone would pick 'set_p' (p < q alphabetically);
    the tracking's own team_set_code='set_q' must win instead, so takeover doesn't
    silently move the task to the wrong team/set."""
    pid = _policy(db)
    me = _user(db, "me", respond_user_id="r-me")
    peer = _user(db, "peer", respond_user_id="r-peer")
    team_p = _team(db, "Team P")
    team_q = _team(db, "Team Q")
    _member(db, team_p, me)
    _member(db, team_q, me)
    _member(db, team_q, peer)  # shared team with peer -> me can see peer's task
    agent_id = _agent(db)
    _agent_team(db, agent_id, team_p, code="set_p", tier=1)
    _agent_team(db, agent_id, team_q, code="set_q", tier=1)
    tid = _track(db, pid, assignee=peer, src="complaint")
    db.query(ConversationSLATracking).filter(ConversationSLATracking.id == tid).update(
        {"agent_id": agent_id, "team_set_code": "set_q", "current_tier": 1}
    )
    db.commit()

    tracking = ConversationSLATrackingService(db).takeover(tid, me, team_q)

    assert tracking.assigned_to_id == me
    assert tracking.team_set_code == "set_q", "must stay on the tracking's own team set"
    assert tracking.agent_id == agent_id
    cur = (
        db.query(AgentTeamRoundRobinCursor)
        .filter(
            AgentTeamRoundRobinCursor.agent_id == agent_id,
            AgentTeamRoundRobinCursor.team_id == team_q,
        )
        .first()
    )
    assert cur is not None and cur.last_assigned_user_id == me


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


@patch("app.services.sla_service.ConversationSLATrackingService._notify_reassignment")
def test_reassign_dual_team_set_prefers_trackings_own_set(notify, db):
    """The target holds a tier-1 link in BOTH team sets under the tracking's agent -
    per-team-set relaxation allows it. Deterministic (tier desc, code asc) ordering
    alone would flip the tracking to 'set_p'; passing the tracking's own
    team_set_code='set_q' must keep it there instead."""
    pid = _policy(db)
    me = _user(db, "me")
    target = _user(db, "tay", respond_user_id="r-tay")
    agent_id = _agent(db)
    team_p = _team(db, "Team P")
    team_q = _team(db, "Team Q")
    _member(db, team_p, me)       # me sees target via shared team_p membership (scope-B)
    _member(db, team_p, target)
    _member(db, team_q, target)
    _agent_team(db, agent_id, team_p, code="set_p", tier=1)
    _agent_team(db, agent_id, team_q, code="set_q", tier=1)
    tid = _track(db, pid, assignee=me, src="complaint")
    db.query(ConversationSLATracking).filter(ConversationSLATracking.id == tid).update(
        {"agent_id": agent_id, "team_set_code": "set_q", "current_tier": 1}
    )
    db.commit()

    tracking = ConversationSLATrackingService(db).reassign(tid, me, target)

    assert tracking.assigned_to_id == target
    assert tracking.team_set_code == "set_q", "must stay on the tracking's own team set"
    assert tracking.current_tier == 1
    assert tracking.agent_id == agent_id


def test_reassign_crosses_teams(db):
    """Hand-off may cross teams (decision 2026-09-03): the actor owns the task
    (passes the assignee-scope guard above), and the target belongs to SOME
    team (any team, not necessarily one shared with the actor), so the
    reassignment succeeds."""
    pid = _policy(db)
    me = _user(db, "me")
    outsider = _user(db, "outsider")
    my_team = _team(db, "Mine")
    other = _team(db, "Other")
    _member(db, my_team, me)
    _member(db, other, outsider)
    tid = _track(db, pid, assignee=me, src="complaint")

    tracking = ConversationSLATrackingService(db).reassign(tid, me, outsider)

    assert tracking.assigned_to_id == outsider


def test_reassign_rejects_user_with_no_team(db):
    """A target with no team membership at all has no SLA routing, so the
    hand-off is still rejected."""
    pid = _policy(db)
    me = _user(db, "me")
    outsider = _user(db, "no-team-outsider")
    my_team = _team(db, "Mine")
    _member(db, my_team, me)
    tid = _track(db, pid, assignee=me, src="complaint")

    with pytest.raises(AppException) as exc:
        ConversationSLATrackingService(db).reassign(tid, me, outsider)
    message = str(exc.value.detail.get("message", "")).lower()
    assert "not in any team" in message


# ---- admin bypass ---------------------------------------------------------
# An admin opening a form detail page sees the form AND its open SLA task, so
# refusing Reassign there (with a "not found, someone deleted it" message) reads
# as a bug. Admin / superadmin bypass the team-membership scope on both sides:
# the task's current assignee AND the hand-off target.


def _make_admin(db, user_id: str) -> None:
    """Give `user_id` the admin role slug."""
    from app.models.user import UserRole, UserRoleAssignment

    role_id = str(uuid.uuid4())
    db.add(UserRole(id=role_id, name="Admin", slug="admin"))
    db.flush()
    db.add(UserRoleAssignment(id=str(uuid.uuid4()), user_id=user_id, role_id=role_id))
    db.commit()


@patch("app.services.sla_service.ConversationSLATrackingService._notify_reassignment")
def test_reassign_allowed_when_assignee_is_outside_my_teams(notify, db):
    """Decision 2026-09-03: the actor gate no longer requires the assignee to be
    in the actor's visible scope. Any team member may reassign any unresolved
    task, so this used-to-be-denied scenario (me in Mine, assignee in Other)
    now succeeds, as long as the target belongs to some team."""
    pid = _policy(db)
    me = _user(db, "cs-agent")
    outsider = _user(db, "purchasing-owner")
    my_team = _team(db, "Mine")
    other = _team(db, "Other")
    _member(db, my_team, me)
    _member(db, other, outsider)
    tid = _track(db, pid, assignee=outsider, src="stock_inquiry")

    updated = ConversationSLATrackingService(db).reassign(tid, me, outsider)
    assert updated.assigned_to_id == outsider


@patch("app.services.sla_service.ConversationSLATrackingService._notify_reassignment")
def test_reassign_escalated_away_to_parent_team_still_reassignable(notify, db):
    """The real-world trigger for decision 2026-09-03: a ticket escalates to the
    assignee's manager (a PARENT team, outside the actor's downward scope) while
    the actor is mid-click on Reassign. The actor (in the child team) must still
    be able to hand it to a peer in her own team."""
    pid = _policy(db)
    child = _team(db, "CS Agents")
    parent = _team(db, "CS Managers", parent_id=None)
    # Reparent: child reports up to parent (mirrors how other tests link tiers).
    db.query(Team).filter(Team.id == child).update({"parent_team_id": parent})
    db.commit()
    me = _user(db, "agent")
    manager = _user(db, "manager")
    peer = _user(db, "peer")
    _member(db, child, me)
    _member(db, child, peer)
    _member(db, parent, manager)
    tid = _track(db, pid, assignee=manager, src="stock_inquiry")

    updated = ConversationSLATrackingService(db).reassign(tid, me, peer)
    assert updated.assigned_to_id == peer


def test_reassign_rejects_actor_with_no_team(db):
    """An actor with no team membership at all cannot own or hand off SLA
    tasks, admin bypass aside."""
    pid = _policy(db)
    no_team_actor = _user(db, "no-team-actor")
    assignee_team = _team(db, "Assignee Team")
    target_team = _team(db, "Target Team")
    assignee = _user(db, "some-assignee")
    target = _user(db, "some-target")
    _member(db, assignee_team, assignee)
    _member(db, target_team, target)
    tid = _track(db, pid, assignee=assignee, src="stock_inquiry")

    with pytest.raises(AppException) as exc:
        ConversationSLATrackingService(db).reassign(tid, no_team_actor, target)
    message = str(exc.value.detail.get("message", "")).lower()
    assert "not in any team" in message
    assert "deleted" not in message


@patch("app.services.sla_service.ConversationSLATrackingService._notify_reassignment")
def test_admin_can_reassign_a_task_owned_by_another_team(notify, db):
    pid = _policy(db)
    admin = _user(db, "admin-user")
    outsider = _user(db, "purchasing-owner")
    target = _user(db, "purchasing-peer")
    other = _team(db, "Purchasing")
    _member(db, other, outsider)
    _member(db, other, target)
    _make_admin(db, admin)
    tid = _track(db, pid, assignee=outsider, src="stock_inquiry")

    updated = ConversationSLATrackingService(db).reassign(tid, admin, target)
    assert str(updated.assigned_to_id) == target


def test_admin_picker_lists_users_outside_their_own_teams(db):
    admin = _user(db, "admin-user")
    outsider = _user(db, "purchasing-owner")
    _member(db, _team(db, "Purchasing"), outsider)
    _make_admin(db, admin)

    ids = {u["id"] for u in ConversationSLATrackingService(db).list_visible_users(admin)}
    # Admin sees everyone but themselves, so the picker matches what they can save.
    assert outsider in ids
    assert admin not in ids


def test_picker_lists_every_team_member_not_just_mine(db):
    """Reassign picker is any-user-in-any-team, not scoped to the actor's own
    teams (decision 2026-09-03): a peer AND an outsider in a different team
    both show up, but someone with no team membership at all is excluded
    (they have no SLA routing)."""
    me = _user(db, "cs-agent")
    peer = _user(db, "cs-peer")
    outsider = _user(db, "purchasing-owner")
    no_team = _user(db, "no-team-user")
    mine = _team(db, "Mine")
    _member(db, mine, me)
    _member(db, mine, peer)
    _member(db, _team(db, "Purchasing"), outsider)

    ids = {u["id"] for u in ConversationSLATrackingService(db).list_visible_users(me)}
    assert peer in ids
    assert outsider in ids
    assert no_team not in ids


def test_the_picker_says_who_is_respond_linked(db):
    """A reply sent by an unlinked user carries no real Respond sender identity,
    so the reassign dialog badges and filters on this (UAC AC-N7). Same notion
    of "linked" the send path uses: a mapping that is present AND is not a CRM
    users.id parked in the column."""
    me = _user(db, "cs-agent")
    linked = _user(db, "cs-linked", respond_user_id="900123")
    unlinked = _user(db, "cs-unlinked")
    mislinked = _user(db, "cs-mislinked", respond_user_id=str(uuid.uuid4()))
    mine = _team(db, "Mine")
    for uid in (me, linked, unlinked, mislinked):
        _member(db, mine, uid)

    rows = {u["id"]: u for u in ConversationSLATrackingService(db).list_visible_users(me)}
    assert rows[linked]["respond_linked"] is True
    assert rows[unlinked]["respond_linked"] is False
    # A CRM uuid in respond_user_id is not a Respond user id - n8n evaluates it
    # against Respond's own users and would never match.
    assert rows[mislinked]["respond_linked"] is False


def test_the_admin_picker_says_who_is_respond_linked_too(db):
    """The admin branch builds its own row list; it must not be the one that
    forgets the flag."""
    admin = _user(db, "admin-user")
    linked = _user(db, "purchasing-linked", respond_user_id="900456")
    unlinked = _user(db, "purchasing-unlinked")
    other = _team(db, "Purchasing")
    _member(db, other, linked)
    _member(db, other, unlinked)
    _make_admin(db, admin)

    rows = {u["id"]: u for u in ConversationSLATrackingService(db).list_visible_users(admin)}
    assert rows[linked]["respond_linked"] is True
    assert rows[unlinked]["respond_linked"] is False
