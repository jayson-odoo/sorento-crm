"""The escalation ladder follows the TRACKER's company, not the request's (AC-E3).

`AccessAgentService.get_team_id_by_tier` already takes an explicit, keyword-only
`company_id` - that argument is the authority on which ladder to read. But
`AgentTeam` / `Team` are also company-scoped models, so the ambient request scope
(the caller's ACTIVE company) is layered on top by `do_orm_execute`. When an admin
with grants to both companies is switched to company B and acts on a company-A
form, the two disagree and the ambient one wins: the explicit A filter matches
rows the loader criteria has already removed, the lookup returns None, and manual
escalation dies as "No higher-tier team configured; cannot escalate further" on a
ladder that is fully configured.

Found in a browser run: the SLA tab showed a Sorento tier-2 tracker, Escalate
returned 422, and the ladder was intact - the session's active company had drifted
to Mocha. The overdue scan never hit it because `scheduler_session` runs with scope
None.

Reading by an explicit company id is safe scope-free: the `company_id` predicate
pins exactly one company, so suspending the ambient filter cannot widen the result
beyond the company the caller named.
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.access import AccessAgent, AgentTeam, Team, TeamMember
from app.models.company import Company
from app.models.user import User
from app.services.company_scope import company_scope, register_company_scope_listeners
from app.services.user_service import AccessAgentService

register_company_scope_listeners()

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)

TEAM_SET = "zzt_ladder_set"


@pytest.fixture()
def db() -> Session:
    session = SessionLocal()
    session.begin_nested()  # SAVEPOINT rolled back at teardown
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def ladder(db: Session):
    """A two-tier ladder wholly inside company A, plus an unrelated company B.

    Seeds its own chain end to end (company -> team -> member -> agent -> agent_team)
    so it passes on an empty CI database.
    """
    suffix = uuid.uuid4().hex[:8]
    company_a = Company(id=str(uuid.uuid4()), name=f"ZZT ladder A {suffix}", code=f"ZLA{suffix}")
    company_b = Company(id=str(uuid.uuid4()), name=f"ZZT ladder B {suffix}", code=f"ZLB{suffix}")
    db.add_all([company_a, company_b])
    db.flush()

    user = User(
        id=str(uuid.uuid4()),
        email=f"zzt-ladder-{suffix}@example.com",
        name=f"ZZT Ladder {suffix}",
    )
    db.add(user)

    tier2 = Team(id=str(uuid.uuid4()), name=f"ZZT tier2 {suffix}", company_id=company_a.id)
    tier3 = Team(id=str(uuid.uuid4()), name=f"ZZT tier3 {suffix}", company_id=company_a.id)
    db.add_all([tier2, tier3])
    db.flush()
    db.add(TeamMember(team_id=tier3.id, user_id=user.id, sort_order=1))

    agent = AccessAgent(id=str(uuid.uuid4()), code=f"zzt_ladder_{suffix}", name="ZZT ladder agent")
    db.add(agent)
    db.flush()
    db.add_all(
        [
            AgentTeam(
                agent_id=agent.id,
                code=TEAM_SET,
                team_id=tier2.id,
                tier=2,
                company_id=company_a.id,
            ),
            AgentTeam(
                agent_id=agent.id,
                code=TEAM_SET,
                team_id=tier3.id,
                tier=3,
                company_id=company_a.id,
            ),
        ]
    )
    db.flush()
    seeded = {
        "a": company_a.id,
        "b": company_b.id,
        "agent_id": agent.id,
        "tier2_id": tier2.id,
        "tier3_id": tier3.id,
        "user_id": user.id,
    }
    try:
        yield seeded
    finally:
        # Belt AND braces: the SAVEPOINT above should undo everything, but a listener
        # that commits mid-flush (audit / company stamp) escapes it, and this suite
        # runs against a copy of production. A leaked `companies` row is not invisible
        # test litter either - it shows up in every user's company switcher. Delete by
        # id, children first, and commit.
        db.rollback()
        for sql, params in (
            ("DELETE FROM agent_teams WHERE agent_id = :a", {"a": seeded["agent_id"]}),
            (
                "DELETE FROM team_members WHERE team_id IN (:t2, :t3)",
                {"t2": seeded["tier2_id"], "t3": seeded["tier3_id"]},
            ),
            ("DELETE FROM teams WHERE id IN (:t2, :t3)", {"t2": seeded["tier2_id"], "t3": seeded["tier3_id"]}),
            ("DELETE FROM access_agents WHERE id = :a", {"a": seeded["agent_id"]}),
            ("DELETE FROM team_members WHERE user_id = :u", {"u": seeded["user_id"]}),
            ("DELETE FROM users WHERE id = :u", {"u": seeded["user_id"]}),
            (
                "DELETE FROM user_companies WHERE company_id IN (:ca, :cb)",
                {"ca": seeded["a"], "cb": seeded["b"]},
            ),
            ("DELETE FROM companies WHERE id IN (:ca, :cb)", {"ca": seeded["a"], "cb": seeded["b"]}),
        ):
            db.execute(sa_text(sql), params)
        db.commit()


def test_tier_lookup_follows_the_named_company_not_the_active_one(db: Session, ladder):
    """Company A's tier 3 resolves while the request is scoped to company B."""
    svc = AccessAgentService(db)
    with company_scope(db, frozenset({ladder["b"]})):
        team_id = svc.get_team_id_by_tier(
            ladder["agent_id"], 3, team_set_code=TEAM_SET, company_id=ladder["a"]
        )
    assert team_id == ladder["tier3_id"]


def test_tier_fallback_follows_the_named_company_not_the_active_one(db: Session, ladder):
    """The escalation entry point (`resolve_team_with_tier_fallback`) too - this is
    what `_escalate_tracker` calls, and returning None here is the 422."""
    svc = AccessAgentService(db)
    with company_scope(db, frozenset({ladder["b"]})):
        resolved = svc.resolve_team_with_tier_fallback(
            ladder["agent_id"], 3, TEAM_SET, company_id=ladder["a"]
        )
    assert resolved == (ladder["tier3_id"], 3)


def test_named_company_still_excludes_another_companys_ladder(db: Session, ladder):
    """Suspending the ambient filter must not widen the result: asking for company
    B's tier 3 returns nothing even though company A has one."""
    svc = AccessAgentService(db)
    with company_scope(db, None):
        team_id = svc.get_team_id_by_tier(
            ladder["agent_id"], 3, team_set_code=TEAM_SET, company_id=ladder["b"]
        )
    assert team_id is None


def test_round_robin_resolves_a_team_from_another_active_company(db: Session, ladder):
    """`get_next_assignee` takes an explicit team_id (already resolved for the
    tracker's company), so the agent-team link must be readable regardless of which
    company the caller is switched to - otherwise escalation swaps one misleading
    422 ("no higher tier") for another ("no available assignee")."""
    svc = AccessAgentService(db)
    with company_scope(db, frozenset({ladder["b"]})):
        assignee = svc.get_next_assignee(ladder["agent_id"], ladder["tier3_id"])
    assert assignee is not None
    assert str(assignee["id"]) == str(ladder["user_id"])
