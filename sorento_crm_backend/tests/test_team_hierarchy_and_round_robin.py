"""Team hierarchy (recursive descendants + cycle guard) and per-member round-robin opt-out."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.access import (
    AccessAgent,
    AgentTeam,
    AgentTeamRoundRobinCursor,
    Team,
    TeamMember,
)
from app.models.lookup import LookupBinding  # listener-table workaround
from app.models.user import User
from app.schemas.user import TeamCreate, TeamUpdate
from app.services.user_service import (
    AccessAgentService,
    TeamService,
    descendant_team_ids,
)
from app.services.error_handler import AppException


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            AccessAgent.__table__,
            Team.__table__,
            TeamMember.__table__,
            AgentTeam.__table__,
            AgentTeamRoundRobinCursor.__table__,
            LookupBinding.__table__,
        ],
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _user(db, name) -> str:
    uid = str(uuid.uuid4())
    db.add(User(id=uid, email=f"{name}@x.com", name=name, status="active"))
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
    assert t.parent_team_id == mgr


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
