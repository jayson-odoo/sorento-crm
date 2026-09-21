"""Shared escalation-lane reference-data seed for `test_rearch_s3_team_pick_and_866.py`
(AC-1533, PLAN-chatbot-turn-rearch.md contract lines 106-113, ported `#866`).

`run_escalation_lane`'s live branch (`_assign`) calls the REAL `/external/next-assignee`
handler in-process (`escalation_services.production_services`), which requires
migration-seeded reference rows the blank scratch schema does not carry on its own: an SLA
policy named `NORMAL` (`escalation.py::NEXT_ASSIGNEE_POLICY_CODE`, a literal reproduced
here for the same reason it is a literal there - a change to it is a change to this file)
with a tier-1 row, and - once a turn resolves to a team - an access agent + team +
membership bound to that team's code.

Company id is the Sorento default (`00000000-0000-0000-0000-000000000001`, seeded into
every scratch schema by `tests/conftest.py`'s `after_create` hook on the companies table).
`next_assignee.py` resolves the routing company to this constant when nothing in the body
overrides it, and a company-scoped read is blind to a row whose own `company_id` is NULL or
any other company - so every row this module writes is stamped with it explicitly rather
than left to the auto-stamp default, which is what the read actually filters on.

Not itself a test file (no `test_` prefix - pytest never collects it).
"""
from __future__ import annotations

import uuid
from typing import Any

from app.models.access import AccessAgent, AgentTeam, Team, TeamMember
from app.models.sla import SLAPolicy, SLAPolicyTier
from app.models.user import User

SORENTO_COMPANY_ID = "00000000-0000-0000-0000-000000000001"

# Reproduced from `app/services/chatbot/lanes/escalation.py` (NEXT_ASSIGNEE_POLICY_CODE /
# NEXT_ASSIGNEE_TIER) - literals there, so literals here; a change to either is a change to
# both files and shows up in a diff.
NEXT_ASSIGNEE_POLICY_CODE = "NORMAL"
NEXT_ASSIGNEE_TIER = 1


def seed_next_assignee_policy(session_factory: Any) -> str:
    """The SLA policy `_next_assignee_body` always names, tier 1, in Sorento.

    Idempotent per test: a second call (e.g. from `seed_team_for_code`) reuses the row
    rather than colliding on `sla_policies`' (code, company_id) unique index.
    """
    db = session_factory()
    existing = (
        db.query(SLAPolicy)
        .filter(SLAPolicy.code == NEXT_ASSIGNEE_POLICY_CODE, SLAPolicy.company_id == SORENTO_COMPANY_ID)
        .first()
    )
    if existing is not None:
        return existing.id
    policy_id = str(uuid.uuid4())
    db.add(
        SLAPolicy(
            id=policy_id,
            code=NEXT_ASSIGNEE_POLICY_CODE,
            name="ZZT Normal",
            company_id=SORENTO_COMPANY_ID,
        )
    )
    db.add(
        SLAPolicyTier(
            id=str(uuid.uuid4()),
            policy_id=policy_id,
            tier_level=NEXT_ASSIGNEE_TIER,
            tier_name="Tier 1",
            response_hours=4,
            resolution_hours=24,
        )
    )
    db.commit()
    return policy_id


def seed_team_for_code(
    session_factory: Any, team_code: str, *, agent_code: str = "general_enquiries"
) -> dict[str, str]:
    """One access agent + team + one active team member, bound to `team_code` at tier 1.

    The access agent row is reused across calls in the same test (`AccessAgent.code` is
    globally unique), so seeding two team codes in one test does not collide.
    `respond_user_id` is set because the SLA comment / assignment actions read it off the
    drawn assignee.
    """
    db = session_factory()
    policy_id = seed_next_assignee_policy(session_factory)

    agent = db.query(AccessAgent).filter(AccessAgent.code == agent_code).first()
    if agent is None:
        agent = AccessAgent(id=str(uuid.uuid4()), code=agent_code, name=f"ZZT {agent_code}")
        db.add(agent)
        db.commit()

    user_id = str(uuid.uuid4())
    db.add(
        User(
            id=user_id,
            email=f"zzt-escalation-{uuid.uuid4().hex[:8]}@test.com",
            name="ZZT Escalation Agent",
            status="ACTIVE",
            respond_user_id=str(uuid.uuid4().int)[:10],
        )
    )
    team_id = str(uuid.uuid4())
    db.add(Team(id=team_id, name=f"ZZT {team_code}", company_id=SORENTO_COMPANY_ID))
    db.add(
        AgentTeam(
            id=str(uuid.uuid4()),
            agent_id=agent.id,
            code=team_code,
            team_id=team_id,
            tier=NEXT_ASSIGNEE_TIER,
            policy_id=policy_id,
            company_id=SORENTO_COMPANY_ID,
        )
    )
    db.add(TeamMember(id=str(uuid.uuid4()), team_id=team_id, user_id=user_id, sort_order=1))
    db.commit()
    return {"agent_id": agent.id, "team_id": team_id, "user_id": user_id}
