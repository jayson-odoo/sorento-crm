"""
External API: fetch conversation SLA tracking by Respond contact id or phone.

Auth: X-API-Key header (get_external_api_user).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.api.v1.sla.sla_tracking import build_conversation_sla_tracking_response
from app.schemas.integration import IntegrationLogCreate
from app.schemas.sla import (
    ConversationSLAAgentRepliedRequest,
    ConversationSLAAgentRepliedResponse,
    ConversationSLAOpenCountResponse,
    ConversationSLATrackingResponse,
)
from app.services.integration_service import IntegrationLogService
from app.services.sla_service import ConversationSLATrackingService

router = APIRouter()

# integration_log.business_id is a NOT NULL uuid column, but a skipped outcome has
# no tracking to point at. Same placeholder the sibling SLA routes use.
_NO_TRACKING_BUSINESS_ID = "00000000-0000-0000-0000-000000000000"

_AGENT_REPLIED_LOG_STATUS = {
    None: "success",
    "ambiguous": "skipped_ambiguous",
    "no_open_ticket": "skipped_no_open_ticket",
}


@router.get(
    "/open-count",
    response_model=ConversationSLAOpenCountResponse,
    summary="Count a contact's OPEN conversation SLA tickets",
)
async def get_conversation_sla_open_count(
    contact_id: Optional[str] = Query(
        None,
        description="Respond.io contact id (respond_io_id) or CRM respond_contacts row id.",
    ),
    phone_number: Optional[str] = Query(
        None,
        description="Contact phone (E.164), e.g. +60123456789.",
    ),
    contact_phone: Optional[str] = Query(
        None,
        description="Alias for phone_number (same value).",
    ),
    _current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """How many OPEN conversation-scope tickets a contact holds right now (AC-I2).

    **Auth:** `X-API-Key` header.

    **Query:** Provide **contact_id** and/or **phone_number** (or **contact_phone**),
    resolved exactly like the sibling GET above. If both are sent they must refer to
    the same contact.

    **Always 200.** An unknown contact, a known contact with no tickets, and a contact
    whose tickets are all resolved every return `{"contact_id": <resolved or null>,
    "open_count": 0}`. The only 4xx is a caller mistake: no identifier at all, or two
    identifiers that disagree.

    Why this exists rather than reusing the sibling GET: n8n gates the customer-facing
    "conversation closed and resolved" WhatsApp message on this number. The sibling GET
    404s on "no contact" / "no tracking" and otherwise returns ONE sort-order-dependent
    "preferred" row, so under multi-open tickets it cannot answer "is anything still
    open for this contact". Either shape ends with a contact being told their still-open
    enquiry is resolved. Form-SLA rows are excluded (`conversation_tracking_scope`).
    """
    phone = (phone_number or contact_phone or "").strip()
    cid = (contact_id or "").strip()
    if not cid and not phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide contact_id and/or phone_number (or contact_phone).",
        )

    service = ConversationSLATrackingService(db)
    contact, conflict = service.resolve_respond_contact(
        phone_number=phone or None, contact_id=cid or None
    )
    if conflict:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=conflict)
    if not contact:
        # Deliberately NOT a 404: "we have never heard of this contact" and "this
        # contact has nothing open" are the same answer to the question n8n asks.
        return ConversationSLAOpenCountResponse(contact_id=None, open_count=0)

    return ConversationSLAOpenCountResponse(
        contact_id=str(contact.id),
        open_count=service.count_open_tickets_for_contact(contact),
    )


@router.post(
    "/agent-replied",
    response_model=ConversationSLAAgentRepliedResponse,
    status_code=status.HTTP_200_OK,
    summary="Record that a staff member replied to a contact in the Respond app",
)
async def record_agent_reply(
    body: ConversationSLAAgentRepliedRequest,
    request: Request,
    _current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """Stop the right ticket's response clock after a Respond-app reply (AC-I4).

    **Auth:** `X-API-Key` header.

    **Body:** `{contact_id, replied_by, replied_at?}`. `contact_id` accepts a CRM
    `respond_contacts.id`, a Respond.io contact id, or a phone number.
    `replied_by` is a Respond user id, a CRM `users.id`, or an email.

    **Always 200** with `{matched, tracking_id, skipped_reason, open_ticket_count}`.
    `skipped_reason` is null on a stamp, else `"ambiguous"` or `"no_open_ticket"`.
    An unknown contact and an unknown replier are both ordinary outcomes, not 4xx:
    n8n has nowhere useful to route an error here, and a lost reply signal means a
    ticket breaches while a human is actively answering it.

    The rule (revised AC-E3, keyed on the contact first) lives in
    `ConversationSLATrackingService.apply_agent_reply`, deliberately server-side:
    this endpoint retires the n8n `respond-send-user` workflow, which resolved rows
    in raw SQL by (arbitrary first policy, is_responded=false, assigned_to=replier)
    with NO CONTACT PREDICATE and PUT once per row - so one reply to one contact
    stamped every unanswered ticket that agent owned across ALL contacts.

    Every outcome writes an `integration_log` row, INCLUDING the skips. The path
    being replaced surfaced its failures as 400s; that signal has to survive the
    move to an always-200 contract, or the endpoint goes quiet exactly when it is
    doing nothing.
    """
    service = ConversationSLATrackingService(db)
    result = service.apply_agent_reply(
        contact_identifier=body.contact_id,
        replied_by=body.replied_by,
        replied_at=body.replied_at,
    )

    try:
        IntegrationLogService(db).create_integration_log(
            IntegrationLogCreate(
                integration_channel="sla_agent_replied",
                business_table="conversation_sla_tracking",
                business_id=result["tracking_id"] or _NO_TRACKING_BUSINESS_ID,
                external_reference=body.contact_id,
                direction="inbound",
                endpoint=str(request.url),
                http_method="POST",
                status=_AGENT_REPLIED_LOG_STATUS.get(
                    result["skipped_reason"], "skipped"
                ),
            ),
            request_payload_dict={
                "contact_id": body.contact_id,
                "replied_by": body.replied_by,
                "replied_at": body.replied_at.isoformat() if body.replied_at else None,
                "open_ticket_count": result["open_ticket_count"],
            },
        )
    except Exception:  # noqa: BLE001 - the stamp already committed
        # Post-commit side effect: logging must never turn a successful stamp
        # into a 500 the caller then retries into the idempotent path.
        pass

    return ConversationSLAAgentRepliedResponse(**result)


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
