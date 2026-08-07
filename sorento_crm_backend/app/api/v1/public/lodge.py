"""The consumer intake surface (S3, Journey actor 1).

Three routes, and the split between them is the journey:

    GET  /portal/lodge/kinds      what the tiled chooser shows
    POST /portal/lodge/resolve    "did I get this right?" - re-runnable, writes nothing
    POST /portal/lodge            submit

**`resolve` writes nothing and may be called on every keystroke-ish edit.** The Phase 1
prototype pre-fills an EDITABLE form rather than a read-only confirmation, so correcting the
shop name has to re-run the dealer match. Making that a side-effect-free call is what lets
the consumer fix a bad extraction themselves instead of it costing CS a cleanup.

**Extraction itself is not here.** `POST /portal/ai-extract` already reads receipts; this
module resolves what extraction (or the consumer) produced into a dealer, a product and a
Kind. Keeping them apart means the consumer can correct a field and get a fresh resolution
without paying for another model call.

**Portal-token scoped, like every other public write.** An unauthenticated lodge endpoint is
an invitation to fill the complaint table with junk, and the consumer arrives from a
WhatsApp link that already carries a token.
"""
from __future__ import annotations

import logging
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.v1.public.portal import get_portal_token
from app.database import get_db
from app.models.portal import PortalToken
from app.models.warranty import WarrantyProductKind
from app.services.dealer_resolution_service import resolve_dealer
from app.services.product_resolution_service import STATE_AMBIGUOUS, resolve_product

logger = logging.getLogger(__name__)

router = APIRouter()


class LodgeLineIn(BaseModel):
    """One product the consumer is complaining about.

    Every field is optional except the fault, because AC-C14 means a line that resolved
    to nothing is still a line worth submitting.
    """

    claimed_text: Optional[str] = None
    model_code_raw: Optional[str] = None
    kind_code: Optional[str] = None
    quantity: Optional[int] = None
    fault_description: Optional[str] = None


class ResolveIn(BaseModel):
    shop_name: Optional[str] = None
    lines: List[LodgeLineIn] = Field(default_factory=list)


class LodgeIn(ResolveIn):
    # OPTIONAL, and ignored whenever the token's contact carries a phone. It stays on the
    # schema only for the contact-without-a-phone case; see `lodge` below for why it is
    # not the identity.
    phone: Optional[str] = None
    full_name: Optional[str] = None
    purchase_date: Optional[str] = None
    dealer_document_number: Optional[str] = None
    # The composed one-line address, still authoritative for every existing reader.
    site_address: Optional[str] = None
    # ...and the parts it was composed from. A single free-text line accepts "kajang" and
    # calls it an address, which is a van sent to a town; postcode and state are also what
    # documents need and cannot be recovered from prose afterwards.
    site_address_line1: Optional[str] = None
    site_address_line2: Optional[str] = None
    site_postcode: Optional[str] = None
    site_city: Optional[str] = None
    site_state: Optional[str] = None
    site_country: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    defect_description: Optional[str] = None
    proof_attachment_id: Optional[str] = None


def _kind_payload(row: WarrantyProductKind) -> Dict[str, Any]:
    return {
        "kind_code": row.code,
        # What a homeowner is shown. Falls back to the internal name rather than
        # rendering an empty tile: a tile with no label is unclickable in practice.
        "label": row.consumer_label or row.name,
        "icon": row.consumer_icon,
        "sort_order": row.sort_order,
    }


@router.get("/lodge/kinds")
async def lodge_kinds(
    _token: Annotated[PortalToken, Depends(get_portal_token)],
    db: Session = Depends(get_db),
):
    """The tiled chooser (AC-C11).

    `icon` is null for every Kind today, which is Sorento's accepted position: text-only
    tiles ship, and the field is here so adding artwork later needs no contract change.
    """
    rows = (
        db.query(WarrantyProductKind)
        .order_by(WarrantyProductKind.sort_order, WarrantyProductKind.code)
        .all()
    )
    return {"kinds": [_kind_payload(row) for row in rows]}


def _resolve_lines(db: Session, lines: List[LodgeLineIn]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for index, line in enumerate(lines):
        match = resolve_product(db, line.model_code_raw or line.claimed_text)
        out.append(
            {
                "index": index,
                "claimed_text": line.claimed_text,
                "model_code_raw": line.model_code_raw,
                "state": match.state,
                # NULL on `ambiguous` by design: a base code covering three variants
                # resolves the Kind, never the variant (AC-C17).
                "product_id": match.product_id,
                "product_code": match.product_code,
                "product_name": match.product_name,
                "candidates": match.candidates,
                "needs_kind": match.state != "exact" or not line.kind_code,
                "kind_code": line.kind_code,
            }
        )
    return out


@router.post("/lodge/resolve")
async def lodge_resolve(
    payload: ResolveIn,
    _token: Annotated[PortalToken, Depends(get_portal_token)],
    db: Session = Depends(get_db),
):
    """What the system understood, so the consumer can correct it. Writes nothing.

    The dealer comes back as a STATE. `candidate` carries no `customer_id`: the consumer
    never sees a guess presented as a fact, because three receipts in thirty-eight had a
    real but wrong nearest neighbour.
    """
    match = resolve_dealer(db, payload.shop_name)
    return {
        "dealer": {
            "state": match.state,
            "printed_name": match.printed_name,
            "customer_id": match.customer_id,
            "customer_name": match.customer_name,
            # For CS only. The portal shows the printed name and asks.
            "suggestion_name": match.suggestion_name,
        },
        "lines": _resolve_lines(db, payload.lines),
    }


@router.post("/lodge")
async def lodge(
    payload: LodgeIn,
    token: Annotated[PortalToken, Depends(get_portal_token)],
    db: Session = Depends(get_db),
):
    """Submit. One transaction; see `consumer_lodge_service` for what it guarantees.

    Nothing here validates the shape into submission: a missing date, an unmatched shop
    and an unresolvable code all lodge (AC-C14). The only refusal comes from the service,
    and it is consent.
    """
    from app.models.access import RespondContact
    from app.services.consumer_lodge_service import lodge_complaint
    from app.services.error_handler import AppException

    body = payload.model_dump()
    body["respond_contact_id"] = str(token.contact_id) if token.contact_id else None

    # THE PHONE IS THE IDENTITY, so it comes from the token and never from the body.
    #
    # `ensure_profile` resolves (and creates) a ConsumerProfile by normalised phone. While
    # the body supplied it, any valid portal token could lodge against a stranger simply by
    # typing their number: it wrote consent, a name-conflict review row and a purchase onto
    # that stranger's ledger, and returned their dealer and warranty verdicts in the
    # response. Overriding only `respond_contact_id` was not enough - that field is not
    # what the profile is keyed on.
    contact = (
        db.query(RespondContact).filter(RespondContact.id == token.contact_id).first()
        if token.contact_id
        else None
    )
    contact_phone = (getattr(contact, "phone_number", None) or "").strip()
    if not contact_phone:
        # Unreachable in practice - `respond_contacts.phone_number` is NOT NULL, which a
        # test attempting to create the state confirmed by failing at the constraint. Kept
        # as a fail-closed floor rather than deleted: falling back to the body here would
        # be the same hole in a smaller shape, and the guard costs one comparison.
        raise AppException(
            status_code=400,
            message=(
                "This portal link is not linked to a phone number, so we cannot tell "
                "whose report this is. Please contact us to continue."
            ),
            code="lodge_identity_unresolved",
        )
    body["phone"] = contact_phone
    # The name is a label, not an identity, so a consumer may still correct their own.
    body["full_name"] = body.get("full_name") or getattr(contact, "name", None)

    result = lodge_complaint(db, body)
    return {
        "complaint_id": result.complaint_id,
        "complaint_number": result.complaint_number,
        "purchase_id": result.purchase_id,
        "dealer_state": result.dealer_state,
        "dealer_name": result.dealer_name,
        # The value exchanged for the data. Empty is a normal answer: no purchase date
        # means no verdict, and saying so beats inventing one.
        "warranty": result.warranty,
    }


__all__ = ["router", "STATE_AMBIGUOUS"]
