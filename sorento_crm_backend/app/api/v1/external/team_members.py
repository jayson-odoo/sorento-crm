"""External endpoint for n8n: list active members of a team.

n8n calls this to get the roster (user_id + name) so it can store and later pass
preferred_assignee_id to /external/next-assignee (which then skips round-robin).
Team is resolved the same way as next-assignee: (agent_code/agent_id, team_code/team_id[, tier]).

The resolution itself lives in `app/services/team_roster_service.py` because it has a
second caller from S2: the chatbot tail builds the numbered CS escalation offer in
process rather than over this endpoint (D1), and the two MUST resolve the same pool or a
member offered here would be rejected by next-assignee.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.services.team_roster_service import list_team_roster

router = APIRouter()


@router.get("")
async def get_team_members(
    team_code: Optional[str] = Query(None),
    team_id: Optional[str] = Query(None),
    agent_code: Optional[str] = Query(None),
    agent_id: Optional[str] = Query(None),
    tier: Optional[int] = Query(None),
    contact_id: Optional[str] = Query(
        None,
        description="Respond.io contact id (respond_io_id). When set, the roster is "
        "filtered to members serving the contact's market segment(s) (retail / project); "
        "untagged members serve all. Omit / unknown contact / untagged contact = full roster.",
    ),
    space_id: Optional[str] = Query(
        None,
        description="Respond.io space id (respond_workspaces.space_id) - optional, "
        "disambiguates contact_id across workspaces.",
    ),
    contact_phone_number: Optional[str] = Query(
        None,
        description="Contact phone. Resolves the same company and market segments as "
        "next-assignee does, so this roster and that endpoint agree.",
    ),
    company_code: Optional[str] = Query(
        None,
        description="Override the resolved company (tests / future use). Normally the "
        "company is derived from the contact.",
    ),
    company_id: Optional[str] = Query(
        None,
        description="Override the resolved company by id (companies.id). Takes "
        "precedence over company_code; an unknown id is ignored. Same field "
        "next-assignee accepts, so both resolve the same company.",
    ),
    brand_code: Optional[str] = Query(
        None,
        description="Brand of the item being routed (lower-case brands.brand_code). "
        "Filters the roster to members tagged with that brand plus members tagged "
        "with none - identical to the pool next-assignee draws from, so an id "
        "returned here is always accepted there.",
    ),
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """
    Return active members of the resolved team, ordered by sort_order then user_id.

    Query (team): team_id, or team_code (+ tier when the same team_code spans SLA tiers).
    Query (agent): agent_id or agent_code - required to resolve a team_code via the agent link.
    Query (segment): contact_id (respond_io_id) [+ space_id] to filter by the contact's
    market segment(s). No filter when omitted / contact unknown / contact untagged.
    Query (brand/company): brand_code and company_id - the same two axes next-assignee
    routes on, so this roster and that endpoint always resolve the same pool.

    Response: [{user_id, name, respond_user_id, email, sort_order}] (active users only).
    """
    return list_team_roster(
        db,
        team_code=team_code,
        team_id=team_id,
        agent_code=agent_code,
        agent_id=agent_id,
        tier=tier,
        contact_id=contact_id,
        space_id=space_id,
        contact_phone_number=contact_phone_number,
        company_code=company_code,
        company_id=company_id,
        brand_code=brand_code,
    )
