"""S4 - the two write-side guards, and the scope filter actually isolating teams.

Both guards protect things that fail silently otherwise: a cross-company parent
hands one brand's staff the other brand's work through the descendant chain, and a
member with no company grant gets assigned work in a company they cannot open.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.access import AgentTeam, Team, TeamMember
from app.models.base import UNSET, set_company_scope
from app.models.company import Company, UserCompany
from app.models.user import User
from app.services.error_handler import AppException
from app.services.user_service import TeamService
from tests._pg_fixture import blank_session, unique_code


SORENTO = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def db():
    with blank_session() as session:
        set_company_scope(session, frozenset({SORENTO}))
        yield session


def _company(db) -> Company:
    c = Company(
        id=str(uuid.uuid4()), name="ZZT Mocha", code=unique_code("MCH"), is_active=True
    )
    db.add(c)
    db.flush()
    return c


def _team(db, name: str, company_id: str, parent_team_id: str | None = None) -> Team:
    t = Team(
        id=str(uuid.uuid4()), name=name, company_id=company_id, parent_team_id=parent_team_id
    )
    db.add(t)
    db.flush()
    return t


def _user(db, *, grant_company_id: str | None = None) -> User:
    u = User(
        id=str(uuid.uuid4()),
        email=f"zzt-{uuid.uuid4().hex[:8]}@test.local",
        name="ZZT User",
    )
    db.add(u)
    db.flush()
    if grant_company_id:
        db.add(
            UserCompany(
                id=str(uuid.uuid4()), user_id=str(u.id), company_id=str(grant_company_id)
            )
        )
        db.flush()
    return u


# ------------------------------------------------------------ parent guard


def test_parent_team_in_another_company_is_rejected(db):
    """AC-C7 - a parent's members can act on every descendant at any depth."""
    mocha = _company(db)
    mocha_parent = _team(db, "ZZT Mocha Directors", str(mocha.id))
    sorento_child = _team(db, "ZZT Sorento Marketing", SORENTO)

    with pytest.raises(AppException, match="same company"):
        TeamService(db)._guard_parent_team_company(SORENTO, str(mocha_parent.id))

    # And the same-company case is still allowed.
    sorento_parent = _team(db, "ZZT Sorento Directors", SORENTO)
    TeamService(db)._guard_parent_team_company(SORENTO, str(sorento_parent.id))
    assert sorento_child.company_id == SORENTO


def test_missing_parent_team_is_rejected(db):
    with pytest.raises(AppException, match="not found"):
        TeamService(db)._guard_parent_team_company(SORENTO, str(uuid.uuid4()))


def test_no_parent_is_always_fine(db):
    TeamService(db)._guard_parent_team_company(SORENTO, None)


# ------------------------------------------------------------- grant guard


def test_member_without_a_company_grant_is_rejected(db):
    """AC-G1 - membership drives assignment, so it must follow the grant."""
    mocha = _company(db)
    mocha_team = _team(db, "ZZT Mocha CS", str(mocha.id))
    ungranted = _user(db, grant_company_id=SORENTO)

    with pytest.raises(AppException, match="no access"):
        TeamService(db)._guard_member_company_grant(str(mocha_team.id), str(ungranted.id))


def test_member_with_the_grant_is_allowed(db):
    mocha = _company(db)
    mocha_team = _team(db, "ZZT Mocha CS", str(mocha.id))
    granted = _user(db, grant_company_id=str(mocha.id))

    TeamService(db)._guard_member_company_grant(str(mocha_team.id), str(granted.id))


def test_add_team_member_enforces_the_grant(db):
    """The guard is wired into the write path, not just callable."""
    mocha = _company(db)
    mocha_team = _team(db, "ZZT Mocha CS", str(mocha.id))
    ungranted = _user(db, grant_company_id=SORENTO)

    # Act as an admin whose active company IS Mocha, so add_team_member's own scoped
    # get_team() can see the team; the grant guard is what must reject the user.
    set_company_scope(db, frozenset({str(mocha.id)}))
    with pytest.raises(AppException, match="no access"):
        TeamService(db).add_team_member(str(mocha_team.id), str(ungranted.id))


# ------------------------------------------------------------- scope filter


def test_teams_are_filtered_by_the_active_company(db):
    """AC-F1 / D7 - the Teams page follows the company switcher."""
    mocha = _company(db)
    _team(db, "ZZT Sorento Only", SORENTO)
    _team(db, "ZZT Mocha Only", str(mocha.id))

    set_company_scope(db, frozenset({SORENTO}))
    names = {t.name for t in db.query(Team).filter(Team.name.like("ZZT%")).all()}
    assert "ZZT Sorento Only" in names
    assert "ZZT Mocha Only" not in names

    set_company_scope(db, frozenset({str(mocha.id)}))
    names = {t.name for t in db.query(Team).filter(Team.name.like("ZZT%")).all()}
    assert "ZZT Mocha Only" in names
    assert "ZZT Sorento Only" not in names


def test_agent_teams_are_filtered_by_the_active_company(db):
    """AC-E5c - the backstop for ad-hoc AgentTeam queries a kwarg cannot reach."""
    from app.models.access import AccessAgent

    mocha = _company(db)
    agent = AccessAgent(
        id=str(uuid.uuid4()), code=unique_code("agent"), name="ZZT Agent", is_active=True
    )
    db.add(agent)
    sorento_team = _team(db, "ZZT S Team", SORENTO)
    mocha_team = _team(db, "ZZT M Team", str(mocha.id))
    db.flush()
    for team, company_id in ((sorento_team, SORENTO), (mocha_team, str(mocha.id))):
        db.add(
            AgentTeam(
                id=str(uuid.uuid4()),
                agent_id=str(agent.id),
                code="zzt_shared_code",
                team_id=str(team.id),
                tier=1,
                company_id=company_id,
            )
        )
    db.flush()

    set_company_scope(db, frozenset({SORENTO}))
    rows = db.query(AgentTeam).filter(AgentTeam.code == "zzt_shared_code").all()
    assert [str(r.team_id) for r in rows] == [str(sorento_team.id)]

    set_company_scope(db, frozenset({str(mocha.id)}))
    rows = db.query(AgentTeam).filter(AgentTeam.code == "zzt_shared_code").all()
    assert [str(r.team_id) for r in rows] == [str(mocha_team.id)]


def test_unset_scope_hides_every_team(db):
    """Why S1 had to land first: a scopeless background session sees nothing."""
    _team(db, "ZZT Hidden", SORENTO)

    set_company_scope(db, UNSET)
    assert db.query(Team).filter(Team.name == "ZZT Hidden").count() == 0

    set_company_scope(db, None)
    assert db.query(Team).filter(Team.name == "ZZT Hidden").count() == 1
