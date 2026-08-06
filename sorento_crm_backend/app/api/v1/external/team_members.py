"""External endpoint for n8n: list active members of a team.

n8n calls this to get the roster (user_id + name) so it can store and later pass
preferred_assignee_id to /external/next-assignee (which then skips round-robin).
Team is resolved the same way as next-assignee: (agent_code/agent_id, team_code/team_id[, tier]).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.api.v1.external.next_assignee import _resolve_round_robin_team_id
from app.services.market_segment_service import MarketSegmentService
from app.services.user_service import AccessAgentService

router = APIRouter()


@router.get("")
def get_team_members(
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
        description="Respond.io space id (respond_workspaces.space_id) — optional, "
        "disambiguates contact_id across workspaces.",
    ),
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """
    Return active members of the resolved team, ordered by sort_order then user_id.

    Query (team): team_id, or team_code (+ tier when the same team_code spans SLA tiers).
    Query (agent): agent_id or agent_code — required to resolve a team_code via the agent link.
    Query (segment): contact_id (respond_io_id) [+ space_id] to filter by the contact's
    market segment(s). No filter when omitted / contact unknown / contact untagged.

    Response: [{user_id, name, respond_user_id, email, sort_order}] (active users only).
    """
    service = AccessAgentService(db)

    # Resolve agent_id from agent_code (needed when resolving a team via team_code).
    resolved_agent_id = agent_id
    if agent_code and not resolved_agent_id:
        resolved_agent_id = service.get_agent_id_by_code(agent_code)
        if not resolved_agent_id:
            raise HTTPException(status_code=404, detail=f"No agent found with code={agent_code!r}")

    # team_id given directly -> no agent needed; team_code path needs agent_id.
    if not (team_id and str(team_id).strip()) and not resolved_agent_id:
        raise HTTPException(
            status_code=400,
            detail="agent_id or agent_code is required to resolve team_code (or pass team_id directly).",
        )

    body = {
        "team_id": team_id,
        "team_code": team_code,
        "tier": tier,
    }
    resolved_team_id = _resolve_round_robin_team_id(
        service, str(resolved_agent_id).strip() if resolved_agent_id else "", body
    )

    # Opt-in market-segment filter. Unknown/untagged contact -> empty set -> no filter.
    # No contact_id -> call with the original arity (byte-identical to prior behaviour).
    if contact_id and contact_id.strip():
        contact_segments = MarketSegmentService(db).resolve_contact_segments(
            contact_id, space_id
        )
        if contact_segments:
            return service.list_active_team_members_detail(
                resolved_team_id, contact_segments
            )

    return service.list_active_team_members_detail(resolved_team_id)
