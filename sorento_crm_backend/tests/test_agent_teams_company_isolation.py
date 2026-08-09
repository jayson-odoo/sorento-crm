"""S5 - saving one company's team sets must not touch the other company's.

The Team Sets screen edits the ACTIVE company only, so its payload never contains
the other company's rows. An unscoped replace would therefore delete them on every
save - silent, and it destroys live routing rather than just misrouting it.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.access import AccessAgent, AgentTeam, Team, TeamMember
from app.models.base import set_company_scope
from app.models.company import Company, UserCompany
from app.models.user import User
from app.services.user_service import AccessAgentService
from tests._pg_fixture import blank_session, unique_code


SORENTO = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def db():
    with blank_session() as session:
        set_company_scope(session, frozenset({SORENTO}))
        yield session


def _mocha(db) -> str:
    cid = str(uuid.uuid4())
    db.add(Company(id=cid, name="ZZT Mocha", code=unique_code("MCH"), is_active=True))
    db.flush()
    return cid


def _agent(db) -> str:
    aid = str(uuid.uuid4())
    db.add(AccessAgent(id=aid, code=unique_code("agent"), name="ZZT Agent", is_active=True))
    db.flush()
    return aid


def _team(db, name: str, company_id: str) -> str:
    tid = str(uuid.uuid4())
    db.add(Team(id=tid, name=name, company_id=company_id))
    db.flush()
    return tid


def _link(db, agent_id: str, team_id: str, company_id: str, code: str, tier: int) -> None:
    db.add(
        AgentTeam(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            code=code,
            team_id=team_id,
            tier=tier,
            company_id=company_id,
        )
    )
    db.flush()


def _rows(db, agent_id: str, company_id: str) -> list[AgentTeam]:
    from app.models.base import company_scope

    with company_scope(db, None):
        return (
            db.query(AgentTeam)
            .filter(AgentTeam.agent_id == agent_id, AgentTeam.company_id == company_id)
            .all()
        )


def test_saving_sorento_team_sets_leaves_mocha_alone(db):
    """The data-loss case: the payload only ever holds the active company's rows."""
    mocha = _mocha(db)
    agent_id = _agent(db)
    sorento_team = _team(db, "ZZT S Marketing", SORENTO)
    mocha_team = _team(db, "ZZT M Marketing", mocha)
    _link(db, agent_id, sorento_team, SORENTO, "zzt_marketing", 1)
    _link(db, agent_id, mocha_team, mocha, "zzt_marketing", 1)

    set_company_scope(db, frozenset({SORENTO}))
    AccessAgentService(db).set_agent_teams(
        agent_id,
        [{"code": "zzt_marketing", "team_id": sorento_team, "tier": 1}],
    )

    assert len(_rows(db, agent_id, SORENTO)) == 1
    surviving_mocha = _rows(db, agent_id, mocha)
    assert len(surviving_mocha) == 1, "saving Sorento deleted Mocha's team set"
    assert str(surviving_mocha[0].team_id) == mocha_team


def test_saved_rows_carry_the_active_company(db):
    mocha = _mocha(db)
    agent_id = _agent(db)
    mocha_team = _team(db, "ZZT M CS", mocha)

    set_company_scope(db, frozenset({mocha}))
    AccessAgentService(db).set_agent_teams(
        agent_id, [{"code": "zzt_cs", "team_id": mocha_team, "tier": 1}]
    )

    rows = _rows(db, agent_id, mocha)
    assert len(rows) == 1
    assert str(rows[0].company_id) == mocha
    assert _rows(db, agent_id, SORENTO) == []


def test_same_code_and_tier_in_both_companies_coexist(db):
    """What the pre-company unique keys made impossible."""
    mocha = _mocha(db)
    agent_id = _agent(db)
    sorento_team = _team(db, "ZZT S Promo", SORENTO)
    mocha_team = _team(db, "ZZT M Promo", mocha)

    set_company_scope(db, frozenset({SORENTO}))
    AccessAgentService(db).set_agent_teams(
        agent_id, [{"code": "zzt_promo", "team_id": sorento_team, "tier": 1}]
    )
    set_company_scope(db, frozenset({mocha}))
    AccessAgentService(db).set_agent_teams(
        agent_id, [{"code": "zzt_promo", "team_id": mocha_team, "tier": 1}]
    )

    assert len(_rows(db, agent_id, SORENTO)) == 1
    assert len(_rows(db, agent_id, mocha)) == 1


def test_tier1_invariant_does_not_fire_across_companies(db):
    """AC-H4 - one person can be tier 1 for Sorento AND tier 1 for Mocha.

    The invariant stops a user being tier-1 in two DIFFERENT tier-1 teams, because
    escalation could not then derive their team. Across companies that ambiguity
    does not exist: the two ladders are separate.
    """
    mocha = _mocha(db)
    agent_a = _agent(db)
    agent_b = _agent(db)
    sorento_team = _team(db, "ZZT S Team", SORENTO)
    mocha_team = _team(db, "ZZT M Team", mocha)

    user_id = str(uuid.uuid4())
    db.add(User(id=user_id, email=f"zzt-{uuid.uuid4().hex[:8]}@t.local", name="ZZT Dual"))
    db.flush()
    for company_id in (SORENTO, mocha):
        db.add(UserCompany(id=str(uuid.uuid4()), user_id=user_id, company_id=company_id))
    for team_id in (sorento_team, mocha_team):
        db.add(TeamMember(id=str(uuid.uuid4()), team_id=team_id, user_id=user_id))
    db.flush()

    # Agent A owns the Sorento ladder; agent B owns the Mocha one.
    set_company_scope(db, frozenset({SORENTO}))
    AccessAgentService(db).set_agent_teams(
        agent_a, [{"code": "zzt_conv", "team_id": sorento_team, "tier": 1}]
    )

    set_company_scope(db, frozenset({mocha}))
    AccessAgentService(db).set_agent_teams(
        agent_b, [{"code": "zzt_conv", "team_id": mocha_team, "tier": 1}]
    )

    assert len(_rows(db, agent_b, mocha)) == 1
