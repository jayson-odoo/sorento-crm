"""External endpoint for n8n: get next assignee by round-robin for (agent_id, team_id)."""
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException

from app.database import get_db
from app.dependencies import get_external_api_user
from app.services.calendar_service import CalendarService
from app.services.sla_service import ConversationSLATrackingService
from app.services.user_service import AccessAgentService

router = APIRouter()


def _format_assignee_response(result: dict) -> dict:
    return {
        "assignee_id": result.get("id"),
        "assignee_email": result.get("email"),
        "assignee_name": result.get("name"),
        "assignee_respond_user_id": result.get("respond_user_id"),
    }


def _tracking_is_assigned(tracking: Any) -> bool:
    """True if SLA tracking row has an assignee at CRM (user id and/or legacy respond id string)."""
    if tracking is None:
        return False
    if getattr(tracking, "assigned_to_id", None):
        return True
    at = getattr(tracking, "assigned_to", None)
    if at is None:
        return False
    if isinstance(at, str):
        return bool(at.strip())
    return True


def _enrich_n8n_response(
    base: dict,
    *,
    is_working_hours: bool,
    is_already_assigned: bool,
) -> dict:
    status_flags: list[str] = []
    if not is_working_hours:
        status_flags.append("non_working_hours")
    if is_already_assigned:
        status_flags.append("already_assigned")

    if is_working_hours and not is_already_assigned:
        message = "Within working hours; conversation not yet assigned in CRM."
    elif is_working_hours and is_already_assigned:
        message = "Within working hours; conversation already has an assignee in CRM (use comment flow)."
    elif not is_working_hours and not is_already_assigned:
        message = "Outside working hours (Asia/Kuala_Lumpur); queue for later; round-robin assignee included."
    else:
        message = (
            "Outside working hours (Asia/Kuala_Lumpur) and conversation already has an assignee in CRM; "
            "queue and use comment flow as needed."
        )

    out = {**base}
    out["is_working_hours"] = is_working_hours
    out["is_already_assigned"] = is_already_assigned
    out["status_flags"] = status_flags
    out["message"] = message
    return out


@router.post("")
async def post_next_assignee(
    body: dict,
    current_user: dict = Depends(get_external_api_user),
    db=Depends(get_db),
):
    """
    Return the next eligible assignee for the given agent and team (round-robin).
    contact_phone_number is required. Each call advances the round-robin and returns
    the next assignee unless current_assignee is used (see below).

    Response always includes assignee fields plus:
    - is_working_hours: True if now is within configured working calendar in Asia/Kuala_Lumpur
    - is_already_assigned: True if latest SLA tracking for this phone has an assignee in CRM
    - status_flags: e.g. ["non_working_hours"], ["already_assigned"], or both
    - message: human-readable hint for n8n (queue vs assign vs comment)

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

    calendar = CalendarService(db)
    is_working_hours = calendar.is_within_working_time()

    sla_service = ConversationSLATrackingService(db)
    tracking: Optional[Any] = sla_service.get_tracking_by_contact_phone(contact_phone)
    is_already_assigned = _tracking_is_assigned(tracking)

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
    # Otherwise advance round-robin and return the next assignee.
    current_assignee_raw = body.get("current_assignee")
    if current_assignee_raw is not None and str(current_assignee_raw).strip():
        result = service.get_next_assignee_after(
            agent_id, team_id, str(current_assignee_raw).strip()
        )
        if result is not None:
            return _enrich_n8n_response(
                _format_assignee_response(result),
                is_working_hours=is_working_hours,
                is_already_assigned=is_already_assigned,
            )
        # current_assignee not in team or other failure: fall through to normal round-robin

    result = service.get_next_assignee(agent_id, team_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="No assignee found. Ensure the agent is linked to the team and the team has members.",
        )
    return _enrich_n8n_response(
        _format_assignee_response(result),
        is_working_hours=is_working_hours,
        is_already_assigned=is_already_assigned,
    )
