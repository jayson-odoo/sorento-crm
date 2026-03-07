"""External endpoint for n8n: get next assignee by round-robin for (agent_id, team_id)."""
from fastapi import APIRouter, Depends, HTTPException

from app.database import get_db
from app.dependencies import get_external_api_user
from app.services.user_service import AccessAgentService

router = APIRouter()


def _format_assignee_response(result: dict) -> dict:
    return {
        "assignee_id": result.get("id"),
        "assignee_email": result.get("email"),
        "assignee_name": result.get("name"),
        "assignee_respond_user_id": result.get("respond_user_id"),
    }


@router.post("")
async def post_next_assignee(
    body: dict,
    current_user: dict = Depends(get_external_api_user),
    db=Depends(get_db),
):
    """
    Return the next eligible assignee for the given agent and team (round-robin).
    contact_phone_number is required. Each call advances the round-robin and returns
    the next assignee (Demo, then Jayson, then Demo, ...).

    - If current_assignee (respond_user_id) is provided: returns the *next* assignee
      after that person in round-robin order, without advancing the stored cursor.
    - If current_assignee is not provided: advances the round-robin cursor and returns
      that next assignee.

    Body (required): contact_phone_number or contact_phone.
    Body (agent/team): agent_id/agent_code/agent and team_id/team_code/team or code.
    Body (optional): current_assignee (respond_user_id) to get the next in line after that user.

    Example:
      { "contact_phone_number": "+60123456789", "agent_code": "general_enquiries", "team_code": "marketing" }
    """
    contact_phone = (body.get("contact_phone_number") or body.get("contact_phone") or "").strip()
    if not contact_phone:
        raise HTTPException(
            status_code=400,
            detail="contact_phone_number (or contact_phone) is required.",
        )

    # Accept client-friendly names: agent -> agent_code, team -> team_code
    agent_id = body.get("agent_id")
    team_id = body.get("team_id")
    code = body.get("code")
    agent_code = body.get("agent_code") or body.get("agent")
    team_code = body.get("team_code") or body.get("team")

    service = AccessAgentService(db)

    # Resolve agent_id from agent_code if provided
    if agent_code and not agent_id:
        agent_id = service.get_agent_id_by_code(agent_code)
        if not agent_id:
            raise HTTPException(status_code=404, detail=f"No agent found with code={agent_code!r}")
    if not agent_id:
        raise HTTPException(status_code=400, detail="agent_id or agent_code is required")

    # Resolve team_id from team_code (or code) for this agent if provided
    if team_code and not team_id:
        team_id = service.get_team_id_by_code(agent_id, team_code)
        if not team_id:
            raise HTTPException(status_code=404, detail=f"No team found for agent and team_code={team_code!r}")
    if not team_id and code:
        team_id = service.get_team_id_by_code(agent_id, code)
        if not team_id:
            raise HTTPException(status_code=404, detail=f"No team found for agent and code={code!r}")
    if not team_id:
        raise HTTPException(status_code=400, detail="team_id, team_code, or code is required")

    # When current_assignee (respond_user_id) is sent, return the *next* in round-robin after them.
    # Otherwise always advance round-robin and return the next assignee (no reuse by contact phone).
    current_assignee_raw = body.get("current_assignee")
    if current_assignee_raw is not None and str(current_assignee_raw).strip():
        result = service.get_next_assignee_after(
            agent_id, team_id, str(current_assignee_raw).strip()
        )
        if result is not None:
            return _format_assignee_response(result)
        # current_assignee not in team or other failure: fall through to normal round-robin

    result = service.get_next_assignee(agent_id, team_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="No assignee found. Ensure the agent is linked to the team and the team has members.",
        )
    return _format_assignee_response(result)
