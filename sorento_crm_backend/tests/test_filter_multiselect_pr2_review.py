"""FILTER-MULTISELECT PR2 review round (red): the Team pending response lists every visible team, and
malformed ids on the multi filters are a 422 rather than a 500. Postgres only; rows seeded here.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.user import User
from tests._multi_filter_client import get, open_client
from tests._pg_fixture import blank_session, unique_code
from tests.test_sla_multi_filters import (  # noqa: F401  (fixtures + builders reused)
    EVENT_LOGS, TEAM_PENDING, _member, _policy, _team, _track, _user, ctx, db,
)

USERS = "/api/v1/user-management/users/"


@pytest.fixture
def two_teams(db, ctx):
    """Pending rows only in team A; team B is visible to the caller but has none; team C is not visible."""
    _, actor = ctx
    pol = _policy(db)
    ta, tb, tc = _team(db, "A"), _team(db, "B"), _team(db, "C")
    a, b, c = _user(db, "a"), _user(db, "b"), _user(db, "c")
    for team, user in ((ta, actor), (tb, actor), (ta, a), (tb, b), (tc, c)):
        _member(db, team, user)
    return dict(ta=ta, tb=tb, tc=tc, a=a, b=b, ra=_track(db, pol, a))


def _teams(resp):
    assert resp.status_code == 200, resp.text
    return resp.json()["teams"]


def test_response_lists_every_visible_team_even_those_without_rows(ctx, two_teams):
    c, _ = ctx
    s = two_teams
    teams = _teams(get(c, TEAM_PENDING, [("limit", 200)]))
    assert {t["id"] for t in teams} == {s["ta"].id, s["tb"].id}
    assert all(set(t) == {"id", "name"} for t in teams)
    assert [t["name"] for t in teams] == sorted(t["name"] for t in teams)


def test_teams_are_computed_before_the_team_filter(ctx, two_teams):
    c, _ = ctx
    s = two_teams
    resp = get(c, TEAM_PENDING, [("limit", 200), ("team", s["ta"].id)])
    assert {t["id"] for t in _teams(resp)} == {s["ta"].id, s["tb"].id}


def test_teams_are_computed_before_the_assignee_filter(ctx, two_teams):
    c, _ = ctx
    s = two_teams
    resp = get(c, TEAM_PENDING, [("limit", 200), ("assignee", s["a"].id)])
    assert {t["id"] for t in _teams(resp)} == {s["ta"].id, s["tb"].id}


def test_a_filter_matching_nothing_still_lists_the_teams(ctx, two_teams):
    c, _ = ctx
    s = two_teams
    resp = get(c, TEAM_PENDING, [("limit", 200), ("team", s["tb"].id)])
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == []
    assert {t["id"] for t in resp.json()["teams"]} == {s["ta"].id, s["tb"].id}


# ---- 422s (some may already pass: kept as guards) --------------------------------------------------

def test_team_pending_malformed_assignee_and_team_are_422(ctx, two_teams):
    c, _ = ctx
    s = two_teams
    assert get(c, TEAM_PENDING, [("assignee", "not-a-uuid")]).status_code == 422
    assert get(c, TEAM_PENDING, [("assignee", f"{s['a'].id},not-a-uuid")]).status_code == 422
    assert get(c, TEAM_PENDING, [("team", "not-a-uuid")]).status_code == 422
    assert get(c, TEAM_PENDING, [("team", f"{s['ta'].id},not-a-uuid")]).status_code == 422


def test_event_logs_malformed_assigned_to_id_is_422(ctx):
    c, _ = ctx
    assert get(c, EVENT_LOGS, [("assigned_to_id", "not-a-uuid")]).status_code == 422
    assert get(c, EVENT_LOGS, [("assigned_to_id", f"{uuid.uuid4()},not-a-uuid")]).status_code == 422


def test_users_malformed_role_id_is_422(db, monkeypatch):
    with open_client(db, monkeypatch) as (c, _actor):
        assert get(c, USERS, [("roleId", "not-a-uuid")]).status_code == 422
        assert get(c, USERS, [("roleId", f"{uuid.uuid4()},not-a-uuid")]).status_code == 422


# ---- Escalation logs "Assigned to" filters on the user id ------------------------------------------

def test_event_logs_match_either_picked_user_id_while_assigned_to_holds_a_name(ctx, db):
    from datetime import datetime

    from app.models.sla import ConversationSLAEventLog

    c, _ = ctx
    pol = _policy(db)
    u1, u2, u3 = _user(db, "a"), _user(db, "b"), _user(db, "c")
    tr = _track(db, pol, u1)
    rows = {}
    for key, user in (("l1", u1), ("l2", u2), ("l3", u3)):
        row = ConversationSLAEventLog(
            id=str(uuid.uuid4()), sla_tracking_id=tr.id, event_type="escalation", assigned_to_id=user.id,
            assigned_to=user.name, event_at=datetime(2026, 6, 1, 10, 0, 0),  # a display label, not a Respond id
        )
        db.add(row)
        db.flush()
        rows[key] = row
    resp = get(c, EVENT_LOGS, [("limit", 200), ("assigned_to_id", f"{u1.id},{u2.id}")])
    assert resp.status_code == 200, resp.text
    assert {r["id"] for r in resp.json()["data"]} == {rows["l1"].id, rows["l2"].id}
