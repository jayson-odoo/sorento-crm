"""Public ticket-draft portal routes (token-gated, no JWT).

Used by WhatsApp / n8n flow: contact opens the URL we returned from the
intake endpoint, FE page reads the token from the URL, calls these routes
to fetch the preview and to submit / cancel the draft.

All routes require a valid ``ticket_draft`` token signed by the same
JWT secret as the rest of the app. The token carries the ticket_id +
7-day expiry, so the contact does not need to authenticate again."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.access import RespondContact
from app.models.tickets import Ticket, TicketRespondContactLink
from app.schemas.tickets import TicketDraftPortalUpdate
from app.services import tickets_service
from app.services.ticket_draft_token_service import verify_draft_token

router = APIRouter()


def _resolve_draft_or_404(db: Session, ticket_id: str) -> Ticket:
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Draft ticket not found.",
        )
    return ticket


# Bypasses ``can_view`` because the token IS the authorisation grant for this
# specific ticket. We never expose other tickets via this surface.
def _system_actor() -> dict:
    return {
        "id": None,
        "permissions": ["tickets.tickets.view_all"],
        "role_slugs": [],
    }


@router.get("/{token}")
def get_draft_via_token(token: str, db: Session = Depends(get_db)):
    ticket_id = verify_draft_token(token)
    ticket = _resolve_draft_or_404(db, ticket_id)
    return tickets_service.ticket_to_response(db, ticket)


@router.patch("/{token}")
def update_draft_via_token(
    token: str,
    data: TicketDraftPortalUpdate,
    db: Session = Depends(get_db),
):
    ticket_id = verify_draft_token(token)
    ticket = _resolve_draft_or_404(db, ticket_id)
    if ticket.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ticket is not a draft (status={ticket.status}); cannot edit.",
        )
    if data.description_html is not None:
        ticket.description_html = data.description_html or None
        ticket.description_text = (
            data.description_text
            or tickets_service._strip_html(data.description_html)
        )
    elif data.description_text is not None:
        ticket.description_text = data.description_text or None
        ticket.description_html = None
    db.commit()
    db.refresh(ticket)
    return tickets_service.ticket_to_response(db, ticket)


@router.post("/{token}/submit")
def submit_draft_via_token(token: str, db: Session = Depends(get_db)):
    ticket_id = verify_draft_token(token)
    ticket = _resolve_draft_or_404(db, ticket_id)
    if ticket.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ticket is not a draft (status={ticket.status}); cannot submit.",
        )
    return tickets_service.submit_ticket_draft(
        db, ticket_id=str(ticket.id), current_user=_system_actor()
    )


@router.get("/{token}/conversation")
def get_draft_conversation_via_token(
    token: str,
    limit: int = Query(50, ge=1, le=50),
    cursor: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Respond.io messages for the contact linked to this draft ticket.

    Submitter sees the chat thread that triggered the ticket so they can
    confirm the draft was based on the right message before submitting.
    Returns ``{items, pagination, contact, source_message_id}``; on missing
    contact link or Respond.io misconfig returns empty items + ``error``."""
    from app.services.integration_service import RespondClient

    ticket_id = verify_draft_token(token)
    ticket = _resolve_draft_or_404(db, ticket_id)

    link = (
        db.query(TicketRespondContactLink)
        .filter(TicketRespondContactLink.ticket_id == str(ticket.id))
        .order_by(
            TicketRespondContactLink.is_primary.desc(),
            TicketRespondContactLink.created_at.asc(),
        )
        .first()
    )
    contact_meta: Optional[dict] = None
    identifier: Optional[str] = None
    if link is not None:
        contact = (
            db.query(RespondContact)
            .filter(
                or_(
                    RespondContact.id == str(link.respond_contact_id),
                    RespondContact.respond_io_id == str(link.respond_contact_id),
                )
            )
            .first()
        )
        if contact is not None:
            contact_meta = {"name": contact.name, "phone": contact.phone_number}
            identifier = contact.respond_io_id or str(contact.id)

    if not identifier:
        return {
            "items": [],
            "pagination": {},
            "error": "No Respond.io contact linked to this draft.",
            "contact": contact_meta,
            "source_message_id": ticket.source_message_id,
        }

    try:
        result = RespondClient().list_messages(identifier, limit=limit, cursor=cursor)
    except ValueError as e:
        return {
            "items": [],
            "pagination": {},
            "error": str(e),
            "contact": contact_meta,
            "source_message_id": ticket.source_message_id,
        }
    if isinstance(result, dict):
        result["contact"] = contact_meta
        result["source_message_id"] = ticket.source_message_id
    return result


@router.post("/{token}/cancel", status_code=status.HTTP_204_NO_CONTENT)
def cancel_draft_via_token(token: str, db: Session = Depends(get_db)):
    ticket_id = verify_draft_token(token)
    ticket = _resolve_draft_or_404(db, ticket_id)
    if ticket.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ticket is not a draft (status={ticket.status}); cannot cancel.",
        )
    tickets_service.cancel_ticket_draft(
        db, ticket_id=str(ticket.id), current_user=_system_actor()
    )
