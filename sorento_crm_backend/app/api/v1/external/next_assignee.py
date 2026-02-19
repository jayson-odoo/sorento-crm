"""External endpoint for n8n: get next assignee by round-robin for (agent_id, team_id)."""
from fastapi import APIRouter, Depends, HTTPException

from app.database import get_db
from app.dependencies import get_external_api_user
from app.services.user_service import AccessAgentService
from app.services.sla_service import ConversationSLATrackingService

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
    contact_phone_number is required. If a conversation SLA tracking already exists for
    that phone with an assignee, that assignee is returned so the conversation is not
    reassigned. Only when there is no existing assignee for that contact does round-robin run.
    Auth: X-API-Key header.

    Body (required): contact_phone_number or contact_phone (contact phone number, e.g. "+60123456789").
    Body (for round-robin when no existing assignee): agent_id/agent_code and team_id/team_code or code.

    Example (by codes, for n8n):
      { "contact_phone_number": "+60123456789", "agent_code": "<access-agent-code>", "team_code": "<agent-team-code>" }
    Example (by UUIDs):
      { "contact_phone_number": "+60123456789", "agent_id": "<uuid>", "team_id": "<uuid>" }
    """
    contact_phone = (body.get("contact_phone_number") or body.get("contact_phone") or "").strip()
    if not contact_phone:
        raise HTTPException(
            status_code=400,
            detail="contact_phone_number (or contact_phone) is required.",
        )
    sla_service = ConversationSLATrackingService(db)
    existing = sla_service.get_existing_assignee_for_contact_phone(contact_phone)
    if existing:
        return _format_assignee_response(existing)

    agent_id = body.get("agent_id")
    team_id = body.get("team_id")
    code = body.get("code")
    agent_code = body.get("agent_code")
    team_code = body.get("team_code")

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

    result = service.get_next_assignee(agent_id, team_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="No assignee found. Ensure the agent is linked to the team and the team has members.",
        )
    return _format_assignee_response(result)
