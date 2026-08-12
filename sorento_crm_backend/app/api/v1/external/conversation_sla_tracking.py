"""
External API: fetch conversation SLA tracking by Respond contact id or phone.

Auth: X-API-Key header (get_external_api_user).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.api.v1.sla.sla_tracking import build_conversation_sla_tracking_response
from app.schemas.sla import ConversationSLATrackingResponse
from app.services.sla_service import ConversationSLATrackingService

router = APIRouter()


@router.get(
    "",
    response_model=ConversationSLATrackingResponse,
    summary="Get SLA tracking by contact_id or phone_number",
)
async def get_conversation_sla_tracking_by_contact(
    contact_id: Optional[str] = Query(
        None,
        description="Respond.io contact id (respond_io_id) or CRM respond_contacts row id.",
    ),
    phone_number: Optional[str] = Query(
        None,
        description="Contact phone (E.164), e.g. +60123456789. Also accepts contact_phone alias via duplicate param in docs only - use phone_number.",
    ),
    contact_phone: Optional[str] = Query(
        None,
        description="Alias for phone_number (same value).",
    ),
    _current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """
    Returns the **preferred** conversation SLA tracking for the contact: unresolved first,
    otherwise the most recent by `created_at`. Same core fields as the internal GET-by-id
    endpoint, but **event_logs are omitted** (and averages derived from logs are null) to keep
    responses small for automation.

    **Auth:** `X-API-Key` header.

    **Query:** Provide **contact_id** and/or **phone_number** (or **contact_phone**).
    If both identifiers are sent, they must refer to the same internal user record.

    **404:** No matching contact, or no SLA tracking for that contact.

    **AC-E4 / AC-F1 caution (multi-open consumer audit):** a contact can now hold
    several open tickets at once. Returning only the "preferred" (most-recently-
    created open) one is fine for a read/summary, but if any caller chains this GET
    with a resolve/update call on the returned `id` in response to a Respond.io
    "conversation closed" event, that chain would resolve the WRONG ticket under
    multi-open (or an arbitrary one). No such inbound "resolve on Respond close"
    webhook exists in this backend today (`PUT /integration/{tracking_id}` is always
    ticket_id-scoped by the caller) - this note exists so that assumption is never
    silently reintroduced by wiring this GET into a resolve chain. Kept for backward
    compat (regression net 3) until the n8n contract moves to per-ticket ids (S3.2).
    """
    phone = (phone_number or contact_phone or "").strip()
    cid = (contact_id or "").strip()
    if not cid and not phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide contact_id and/or phone_number (or contact_phone).",
        )

    service = ConversationSLATrackingService(db)
    contact, conflict = service.resolve_respond_contact(phone_number=phone or None, contact_id=cid or None)
    if conflict:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=conflict)
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No contact found for the given contact_id or phone_number.",
        )
    stub = service.get_preferred_tracking_for_contact(contact)
    if not stub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No conversation SLA tracking found for this contact.",
        )
    tracking = service.get_tracking(str(stub.id), load_event_logs=False)
    return build_conversation_sla_tracking_response(db, tracking, include_event_logs=False)
