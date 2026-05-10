"""Public ticket-draft portal routes (token-gated, no JWT).

Used by WhatsApp / n8n flow: contact opens the URL we returned from the
intake endpoint, FE page reads the token from the URL, calls these routes
to fetch the preview and to submit / cancel the draft.

All routes require a valid ``ticket_draft`` token signed by the same
JWT secret as the rest of the app. The token carries the ticket_id +
7-day expiry, so the contact does not need to authenticate again."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.tickets import Ticket
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
