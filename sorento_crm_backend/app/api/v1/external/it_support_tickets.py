"""External MCP/n8n endpoint for IT-support ticket intake.

Auth: X-API-Key header (``get_external_api_user``). The MCP tool
``crm_it_support_ticket_create`` POSTs JSON here. Two-call protocol - see
``app.services.ticket_intake_service``."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.schemas.tickets import (
    ITSupportTicketCreateRequest,
    ITSupportTicketCreateResponse,
)
from app.services.ticket_intake_service import TicketIntakeService

router = APIRouter()


@router.post("/", response_model=ITSupportTicketCreateResponse)
def submit_it_support_ticket(
    payload: ITSupportTicketCreateRequest,
    principal: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
) -> ITSupportTicketCreateResponse:
    """X-API-Key principal's ``act_as`` user (typically the AI assistant
    runtime caller) is used as ``actor_user_id`` when the body omits it."""
    fallback_user_id = (
        str(principal.get("id"))
        if isinstance(principal, dict) and principal.get("id")
        else None
    )
    return TicketIntakeService(db).submit(
        payload, actor_user_id_fallback=fallback_user_id
    )
