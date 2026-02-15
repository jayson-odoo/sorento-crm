"""External endpoint for n8n: get next assignee by round-robin for (agent_id, team_id)."""
from fastapi import APIRouter, Depends, HTTPException

from app.database import get_db
from app.dependencies import get_external_api_user
from app.services.user_service import AccessAgentService

router = APIRouter()


@router.post("")
async def post_next_assignee(
    body: dict,
    current_user: dict = Depends(get_external_api_user),
    db=Depends(get_db),
):
    """
    Return the next eligible assignee for the given agent and team (round-robin).
    Auth: X-API-Key header.
    Body: { "agent_id": "<uuid>", "team_id": "<uuid>" } or { "agent_id": "<uuid>", "code": "<code>" }
    If code is provided, team_id is resolved from the agent's assignments.
    """
    agent_id = body.get("agent_id")
    team_id = body.get("team_id")
    code = body.get("code")
    if not agent_id:
        raise HTTPException(status_code=400, detail="agent_id is required")
    service = AccessAgentService(db)
    if not team_id and code:
        team_id = service.get_team_id_by_code(agent_id, code)
        if not team_id:
            raise HTTPException(status_code=404, detail=f"No team found for agent and code={code}")
    if not team_id:
        raise HTTPException(status_code=400, detail="team_id or code is required")
    result = service.get_next_assignee(agent_id, team_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="No assignee found. Ensure the agent is linked to the team and the team has members.",
        )
    return {
        "assignee_id": result.get("id"),
        "assignee_email": result.get("email"),
        "assignee_name": result.get("name"),
    }
