"""FILTER-MULTISELECT PR2: SLA list filters take several values (OR within a filter, AND across).

Conversation SLA ``assigned_to``; event logs ``event_type`` / ``assigned_to_id`` (the detail Event
log table and Escalation logs); Team pending ``assignee`` / ``team``. Red first; Postgres only; every
row is seeded here into a blank schema.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import text

from app.models.access import Team, TeamMember
from app.models.sla import ConversationSLAEventLog, ConversationSLATracking, SLAPolicy
from app.models.user import User
from app.services.user_service import UserPermissionService
from tests import _pg_fixture
from tests._multi_filter_client import get, ok_ids, open_client
from tests._pg_fixture import blank_session, unique_code

SLA = "/api/v1/sla-management/conversation-sla-tracking/"
EVENT_LOGS = "/api/v1/sla-management/conversation-sla-tracking/event-logs"
TEAM_PENDING = "/api/v1/sla-management/conversation-sla-tracking/team-pending"


@pytest.fixture
def db():
    with blank_session() as session:
        blank = _pg_fixture._BLANK["name"]
        # descendant_team_ids() uses raw SQL the schema translate map does not rewrite
        session.execute(text(f'SET LOCAL search_path TO "{blank}", "{blank}_scm"'))
        yield session


@pytest.fixture
def ctx(db, monkeypatch):
    # the event-log route checks an any-of slug set through get_user_role_slugs, not the patched check
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: {"admin"})
    with open_client(db, monkeypatch) as (c, actor):
        yield c, actor


def _user(db, label):
    code = unique_code(label)
    row = User(id=str(uuid.uuid4()), email=f"{code}@example.com".lower(), name=f"ZZT {code}",
               status="ACTIVE", respond_user_id=f"resp-{uuid.uuid4().hex[:10]}")
    db.add(row)
    db.flush()
    return row


def _policy(db):
    row = SLAPolicy(id=str(uuid.uuid4()), code=unique_code("pol"), name="ZZT policy")
    db.add(row)
    db.flush()
    return row


def _track(db, policy, assignee=None):
    row = ConversationSLATracking(
        id=str(uuid.uuid4()), policy_id=policy.id, current_tier=1,
        assigned_to_id=assignee.id if assignee else None,
        assigned_to=assignee.respond_user_id if assignee else None,
        current_tier_started_at=datetime(2026, 6, 1, 9, 0, 0),
        due_at=datetime(2026, 6, 1, 14, 0, 0), due_at_resolution=datetime(2026, 6, 2, 9, 0, 0),
        is_resolved=False,
    )
    db.add(row)
    db.flush()
    return row


def _log(db, tracking, event_type, assignee=None):
    row = ConversationSLAEventLog(
        id=str(uuid.uuid4()), sla_tracking_id=tracking.id, event_type=event_type,
        assigned_to_id=assignee.id if assignee else None,
        assigned_to=assignee.respond_user_id if assignee else None,
        event_at=datetime(2026, 6, 1, 10, 0, 0),
    )
    db.add(row)
    db.flush()
    return row


def _team(db, name):
    row = Team(id=str(uuid.uuid4()), name=f"ZZT {name} {unique_code('t')}")
    db.add(row)
    db.flush()
    return row


def _member(db, team, user):
    db.add(TeamMember(id=str(uuid.uuid4()), team_id=team.id, user_id=user.id))
    db.flush()


# ---- Conversation SLA list: Assignee ---------------------------------------------------------

@pytest.fixture
def convo(db, ctx):
    pol = _policy(db)
    u1, u2, u3 = _user(db, "a"), _user(db, "b"), _user(db, "c")
    t1, t2, t3, t0 = _track(db, pol, u1), _track(db, pol, u2), _track(db, pol, u3), _track(db, pol)
    return dict(u1=u1, u2=u2, u3=u3, t1=t1, t2=t2, t3=t3, t0=t0)


def _convo(client, pairs):
    return ok_ids(get(client, SLA, [("limit", 200), *pairs]))


def test_conversation_assignee_two_values_are_the_union(ctx, convo):
    c, _ = ctx
    s = convo
    assert _convo(c, [("assigned_to", f"{s['u1'].id},{s['u2'].id}")]) == {s["t1"].id, s["t2"].id}


def test_conversation_assignee_accepts_respond_user_ids_too(ctx, convo):
    c, _ = ctx
    s = convo
    got = _convo(c, [("assigned_to", f"{s['u1'].respond_user_id},{s['u3'].id}")])
    assert got == {s["t1"].id, s["t3"].id}


def test_conversation_assignee_single_and_repeated(ctx, convo):
    c, _ = ctx
    s = convo
    assert _convo(c, [("assigned_to", s["u2"].id)]) == {s["t2"].id}
    got = _convo(c, [("assigned_to", s["u1"].id), ("assigned_to", s["u3"].id)])
    assert got == {s["t1"].id, s["t3"].id}


def test_conversation_assignee_filter_still_drops_unassigned(ctx, convo):
    c, _ = ctx
    s = convo
    assert s["t0"].id not in _convo(c, [("assigned_to", f"{s['u1'].id},{s['u2'].id}")])


# ---- Event logs: Event type + Assigned to ------------------------------------------------------

@pytest.fixture
def logs(db, ctx):
    pol = _policy(db)
    u1, u2, u3 = _user(db, "a"), _user(db, "b"), _user(db, "c")
    tr = _track(db, pol, u1)
    esc1 = _log(db, tr, "escalation", u1)
    esc2 = _log(db, tr, "escalation", u2)
    resp = _log(db, tr, "response", u1)
    res = _log(db, tr, "resolution", u3)
    return dict(u1=u1, u2=u2, u3=u3, tr=tr, esc1=esc1, esc2=esc2, resp=resp, res=res)


def _logs(client, pairs):
    return ok_ids(get(client, EVENT_LOGS, [("limit", 200), *pairs]))


def test_event_type_two_values_are_the_union(ctx, logs):
    c, _ = ctx
    s = logs
    assert _logs(c, [("event_type", "escalation,response")]) == {s["esc1"].id, s["esc2"].id, s["resp"].id}


def test_event_type_single_and_repeated(ctx, logs):
    c, _ = ctx
    s = logs
    assert _logs(c, [("event_type", "resolution")]) == {s["res"].id}
    got = _logs(c, [("event_type", "response"), ("event_type", "resolution")])
    assert got == {s["resp"].id, s["res"].id}


def test_event_log_assigned_to_two_values_are_the_union(ctx, logs):
    c, _ = ctx
    s = logs
    got = _logs(c, [("assigned_to_id", f"{s['u2'].id},{s['u3'].id}")])
    assert got == {s["esc2"].id, s["res"].id}


def test_event_log_assigned_to_single_and_repeated(ctx, logs):
    c, _ = ctx
    s = logs
    assert _logs(c, [("assigned_to_id", s["u1"].id)]) == {s["esc1"].id, s["resp"].id}
    got = _logs(c, [("assigned_to_id", s["u2"].id), ("assigned_to_id", s["u3"].id)])
    assert got == {s["esc2"].id, s["res"].id}


def test_escalation_logs_assigned_to_legacy_text_two_values_are_the_union(ctx, logs):
    # the Escalation logs screen sends the assignee's Respond id as assigned_to
    c, _ = ctx
    s = logs
    got = _logs(c, [("assigned_to", f"{s['u2'].respond_user_id},{s['u3'].respond_user_id}")])
    assert got == {s["esc2"].id, s["res"].id}
    got = _logs(c, [("assigned_to", s["u2"].respond_user_id), ("assigned_to", s["u3"].respond_user_id)])
    assert got == {s["esc2"].id, s["res"].id}
    assert _logs(c, [("assigned_to", s["u1"].respond_user_id)]) == {s["esc1"].id, s["resp"].id}


def test_event_log_filters_and_across_each_other(ctx, logs):
    c, _ = ctx
    s = logs
    got = _logs(c, [("event_type", "escalation,resolution"), ("assigned_to_id", f"{s['u1'].id},{s['u3'].id}")])
    assert got == {s["esc1"].id, s["res"].id}


def test_event_log_filters_on_one_tracking(ctx, logs):
    c, _ = ctx
    s = logs
    got = _logs(c, [("tracking_id", s["tr"].id), ("event_type", "escalation,response")])
    assert got == {s["esc1"].id, s["esc2"].id, s["resp"].id}


# ---- Team pending: Assignee + Team -------------------------------------------------------------

@pytest.fixture
def pending(db, ctx):
    _, actor = ctx
    pol = _policy(db)
    ta, tb = _team(db, "A"), _team(db, "B")
    a, b, c3 = _user(db, "a"), _user(db, "b"), _user(db, "c")
    for team, user in ((ta, actor), (tb, actor), (ta, a), (tb, b), (ta, c3)):
        _member(db, team, user)
    ra, rb, rc = _track(db, pol, a), _track(db, pol, b), _track(db, pol, c3)
    return dict(ta=ta, tb=tb, a=a, b=b, c=c3, ra=ra, rb=rb, rc=rc)


def _pending(client, pairs):
    return ok_ids(get(client, TEAM_PENDING, [("limit", 200), *pairs]))


def test_team_pending_assignee_two_values_are_the_union(ctx, pending):
    c, _ = ctx
    s = pending
    assert _pending(c, [("assignee", f"{s['a'].id},{s['b'].id}")]) == {s["ra"].id, s["rb"].id}


def test_team_pending_assignee_single_and_repeated(ctx, pending):
    c, _ = ctx
    s = pending
    assert _pending(c, [("assignee", s["c"].id)]) == {s["rc"].id}
    got = _pending(c, [("assignee", s["a"].id), ("assignee", s["b"].id)])
    assert got == {s["ra"].id, s["rb"].id}


def test_team_pending_team_two_values_are_the_union(ctx, pending):
    c, _ = ctx
    s = pending
    assert _pending(c, [("team", f"{s['ta'].id},{s['tb'].id}")]) == {s["ra"].id, s["rb"].id, s["rc"].id}


def test_team_pending_team_single_and_repeated(ctx, pending):
    c, _ = ctx
    s = pending
    assert _pending(c, [("team", s["tb"].id)]) == {s["rb"].id}
    got = _pending(c, [("team", s["ta"].id), ("team", s["tb"].id)])
    assert got == {s["ra"].id, s["rb"].id, s["rc"].id}


def test_team_pending_filters_and_across_each_other(ctx, pending):
    c, _ = ctx
    s = pending
    got = _pending(c, [("assignee", f"{s['a'].id},{s['b'].id}"), ("team", f"{s['ta'].id},{s['tb'].id}")])
    assert got == {s["ra"].id, s["rb"].id}
    got = _pending(c, [("assignee", f"{s['a'].id},{s['b'].id}"), ("team", s["ta"].id)])
    assert got == {s["ra"].id}
