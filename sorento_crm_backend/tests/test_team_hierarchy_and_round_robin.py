"""Team hierarchy (recursive descendants + cycle guard) and per-member round-robin opt-out."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.access import (
    AccessAgent,
    AgentTeam,
    AgentTeamRoundRobinCursor,
    Team,
    TeamMember,
)
from app.models.user import User
from app.schemas.user import TeamCreate, TeamUpdate
from app.services.user_service import (
    AccessAgentService,
    TeamService,
    descendant_team_ids,
)
from app.services.error_handler import AppException
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as session:
        # descendant_team_ids() runs a recursive CTE as raw text() SQL over an
        # unqualified `teams`, which schema_translate_map does not rewrite -- see
        # the note in test_coverage_hod_assign. Align search_path with the blank
        # schema so it reads this test's teams and not the real ones.
        schema = session.get_bind()._execution_options["schema_translate_map"][None]
        session.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        yield session


def _user(db, name) -> str:
    from app.models.company import UserCompany

    uid = str(uuid.uuid4())
    db.add(User(id=uid, email=f"{name}@x.com", name=name, status="ACTIVE"))
    db.flush()  # the grant below FKs to users.id
    # Team membership now requires a grant for the team's company (AC-G1), so a user
    # that can be added to a Sorento team must hold Sorento.
    db.add(
        UserCompany(
            id=str(uuid.uuid4()),
            user_id=uid,
            company_id="00000000-0000-0000-0000-000000000001",
        )
    )
    db.commit()
    return uid


def _team(db, name, parent_id=None) -> str:
    tid = str(uuid.uuid4())
    db.add(Team(id=tid, name=name, parent_team_id=parent_id))
    db.commit()
    return tid


def _member(db, team_id, user_id, *, rr=True, order=0):
    db.add(
        TeamMember(
            id=str(uuid.uuid4()),
            team_id=team_id,
            user_id=user_id,
            sort_order=order,
            include_in_round_robin=rr,
        )
    )
    db.commit()


# ---- hierarchy ------------------------------------------------------------

def test_descendant_team_ids_recursive_any_depth(db):
    mgr = _team(db, "Manager")
    product = _team(db, "Product", parent_id=mgr)
    sub = _team(db, "Sub-Product", parent_id=product)
    other = _team(db, "Unrelated")

    out = descendant_team_ids(db, [mgr])
    assert out == {mgr, product, sub}
    assert other not in out


def test_create_team_with_parent_persists(db):
    mgr = _team(db, "Manager")
    t = TeamService(db).create_team(TeamCreate(name="Product", parent_team_id=mgr))
    # create_team returns the TeamResponse dict shape (not the ORM row).
    assert t["parent_team_id"] == mgr
    assert t["member_count"] == 0 and t["members"] == []


def test_list_teams_includes_member_preview(db):
    """List payload carries member count + human-readable names (no UUID leak)."""
    svc = TeamService(db)
    tid = _team(db, "Complaint")
    u1 = _user(db, "Magen")
    u2 = _user(db, "Ziv")
    svc.add_team_member(tid, u1)
    svc.add_team_member(tid, u2)

    row = next(t for t in svc.list_teams() if t["id"] == tid)
    assert row["member_count"] == 2
    names = {m["name"] for m in row["members"]}
    assert names == {"Magen", "Ziv"}
    # names are display names, never the raw user UUID
    assert all(m["name"] != m["user_id"] for m in row["members"])


def test_team_responses_validate_no_relationship_collision(db):
    """Regression: TeamResponse.members must not coerce the ORM Team.members
    relationship (List[TeamMember], no `name`) — that 500'd create/update/get."""
    from app.schemas.user import TeamResponse

    svc = TeamService(db)
    tid = _team(db, "Marketing")
    svc.add_team_member(tid, _user(db, "Li Hua"))

    # All three single-team paths must round-trip through TeamResponse cleanly.
    TeamResponse(**svc.get_team_view(tid))
    TeamResponse(**svc.create_team(TeamCreate(name="Forms", parent_team_id=tid)))
    moved = svc.update_team(tid, TeamUpdate(description="x"))
    TeamResponse(**moved)
    assert moved["member_count"] == 1 and moved["members"][0]["name"] == "Li Hua"


def test_cycle_guard_self_parent(db):
    t = _team(db, "Marketing")
    with pytest.raises(AppException):
        TeamService(db).update_team(t, TeamUpdate(parent_team_id=t))


def test_cycle_guard_descendant_as_parent(db):
    mgr = _team(db, "Manager")
    product = _team(db, "Product", parent_id=mgr)
    # Setting Product (a child) as Manager's parent -> cycle.
    with pytest.raises(AppException):
        TeamService(db).update_team(mgr, TeamUpdate(parent_team_id=product))


# ---- round-robin opt-out --------------------------------------------------

def _agent_team(db, agent_id, team_id, code="cs", tier=1):
    db.add(
        AgentTeam(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            code=code,
            team_id=team_id,
            tier=tier,
        )
    )
    db.commit()


def test_rr_skips_excluded_member(db):
    agent_id = str(uuid.uuid4())
    db.add(AccessAgent(id=agent_id, code="a", name="A"))
    db.commit()
    team_id = _team(db, "CS")
    _agent_team(db, agent_id, team_id)
    a = _user(db, "agnes")
    b = _user(db, "bob")
    _member(db, team_id, a, rr=False, order=0)
    _member(db, team_id, b, rr=True, order=1)

    svc = AccessAgentService(db)
    picks = {svc.get_next_assignee(agent_id, team_id)["id"] for _ in range(4)}
    assert picks == {b}  # agnes never auto-selected


def test_rr_all_excluded_returns_none(db):
    agent_id = str(uuid.uuid4())
    db.add(AccessAgent(id=agent_id, code="a", name="A"))
    db.commit()
    team_id = _team(db, "CS")
    _agent_team(db, agent_id, team_id)
    _member(db, team_id, _user(db, "agnes"), rr=False)
    _member(db, team_id, _user(db, "bob"), rr=False)

    assert AccessAgentService(db).get_next_assignee(agent_id, team_id) is None


def test_rr_per_team_independence(db):
    agent_id = str(uuid.uuid4())
    db.add(AccessAgent(id=agent_id, code="a", name="A"))
    db.commit()
    team_a = _team(db, "A")
    team_b = _team(db, "B")
    _agent_team(db, agent_id, team_a, code="ta")
    _agent_team(db, agent_id, team_b, code="tb")
    u = _user(db, "carol")
    _member(db, team_a, u, rr=True)
    _member(db, team_b, u, rr=False)

    svc = AccessAgentService(db)
    assert svc.get_next_assignee(agent_id, team_a)["id"] == u  # eligible in A
    assert svc.get_next_assignee(agent_id, team_b) is None  # excluded in B
