"""Portal price tag request endpoints.

Mounted at ``/api/v1/public/portal`` alongside the existing portal router.
Auth: portal token (``get_portal_token`` dependency).

These endpoints are separate from ``portal.py`` because price tag requests use
a dedicated service (``PriceTagRequestService``) rather than the generic
``PortalService`` CRUD, and keeping them apart avoids bloating the already-large
portal module.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.v1.public.portal import get_portal_token
from app.database import get_db
from app.models.portal import PortalToken
from app.schemas.price_tag import (
    DebtorForAgentItem,
    PriceTagRequestCreate,
    PriceTagRequestListItem,
    PriceTagRequestResponse,
    PriceTagRequestUpdate,
)
from app.services.error_handler import AppException
from app.services.portal_form_visibility_service import resolve_visible_form_types
from app.services.price_tag_request_service import (
    PriceTagRequestService,
    STATUS_APPROVED,
    STATUS_CHANGES_REQUESTED,
    STATUS_NEW,
    STATUS_PROOF_READY,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["public-portal-price-tag"])

_FORM_TYPE = "price_tag_request"


def _assert_visible(db: Session, contact_id: str) -> None:
    """Raise 403 if price_tag_request is not visible to this contact."""
    visible = resolve_visible_form_types(db, contact_id)
    if _FORM_TYPE not in visible:
        raise AppException(
            status_code=403,
            message="Price tag request is not available for your account.",
            code="FORM_TYPE_NOT_VISIBLE",
        )


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get("/submissions/price_tag_request")
def portal_list_price_tag_requests(
    q: Optional[str] = Query(None),
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    """List price tag requests for the authenticated contact."""
    _assert_visible(db, token.contact_id)
    results = PriceTagRequestService.list_requests(
        db, contact_id=token.contact_id, search=q,
    )
    return {
        "items": [PriceTagRequestListItem.model_validate(r) for r in results],
    }


# ---------------------------------------------------------------------------
# Create (draft)
# ---------------------------------------------------------------------------


@router.post("/submissions/price_tag_request", status_code=201)
def portal_create_price_tag_request(
    payload: PriceTagRequestCreate,
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    """Create a new price tag request as a draft."""
    _assert_visible(db, token.contact_id)
    req = PriceTagRequestService.create_request(
        db,
        contact_id=token.contact_id,
        company_id=_resolve_company(db, token),
        data=payload.model_dump(),
    )
    db.commit()
    return PriceTagRequestResponse.model_validate(req)


# ---------------------------------------------------------------------------
# Update (draft)
# ---------------------------------------------------------------------------


@router.put("/submissions/price_tag_request/{request_id}")
def portal_update_price_tag_request(
    request_id: str,
    payload: PriceTagRequestUpdate,
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    """Update a draft price tag request."""
    _assert_visible(db, token.contact_id)
    req = PriceTagRequestService.get_request(db, request_id)
    if not req or req.contact_id != token.contact_id:
        raise AppException(
            status_code=404,
            message="Price tag request not found.",
            code="NOT_FOUND",
        )
    if req.portal_draft_at is None and req.status != STATUS_NEW:
        raise AppException(
            status_code=409,
            message="Only draft requests can be updated.",
            code="NOT_DRAFT",
        )

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(req, key, value)

    db.flush()
    db.commit()
    return PriceTagRequestResponse.model_validate(req)


# ---------------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------------


@router.post("/submissions/price_tag_request/{request_id}/submit")
def portal_submit_price_tag_request(
    request_id: str,
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    """Submit a draft price tag request: clears portal_draft_at, runs set guard,
    and fires the form SLA."""
    _assert_visible(db, token.contact_id)
    req = PriceTagRequestService.get_request(db, request_id)
    if not req or req.contact_id != token.contact_id:
        raise AppException(
            status_code=404,
            message="Price tag request not found.",
            code="NOT_FOUND",
        )
    if req.portal_draft_at is None and req.status != STATUS_NEW:
        raise AppException(
            status_code=409,
            message="This request has already been submitted.",
            code="ALREADY_SUBMITTED",
        )

    # Run set guard validation on the existing lines.
    PriceTagRequestService.validate_set_guard(db, req)

    # Clear draft and set status to new (ready for marketing).
    req.portal_draft_at = None
    req.status = STATUS_NEW
    db.flush()

    # Fire form SLA.
    try:
        from app.services.form_sla_service import emit_form_event

        emit_form_event(
            db,
            _FORM_TYPE,
            str(req.id),
            "submit",
            contact_id=req.contact_id,
        )
    except Exception:
        logger.warning(
            "Form SLA emit 'submit' failed for price_tag_request %s",
            req.id,
            exc_info=True,
        )

    db.commit()
    return PriceTagRequestResponse.model_validate(req)


# ---------------------------------------------------------------------------
# Approve (portal proof review)
# ---------------------------------------------------------------------------


@router.post("/submissions/price_tag_request/{request_id}/approve")
def portal_approve_price_tag_request(
    request_id: str,
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    """Approve a proof-ready price tag request."""
    _assert_visible(db, token.contact_id)
    req = PriceTagRequestService.get_request(db, request_id)
    if not req or req.contact_id != token.contact_id:
        raise AppException(
            status_code=404,
            message="Price tag request not found.",
            code="NOT_FOUND",
        )

    result = PriceTagRequestService.transition_status(
        db, request_id, STATUS_APPROVED,
    )
    db.commit()
    return PriceTagRequestResponse.model_validate(result)


# ---------------------------------------------------------------------------
# Request changes (portal proof review)
# ---------------------------------------------------------------------------


class RequestChangesPayload(BaseModel):
    note: str = Field(..., min_length=1)


@router.post("/submissions/price_tag_request/{request_id}/request-changes")
def portal_request_changes(
    request_id: str,
    payload: RequestChangesPayload,
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    """Request changes on a proof-ready price tag request."""
    _assert_visible(db, token.contact_id)
    req = PriceTagRequestService.get_request(db, request_id)
    if not req or req.contact_id != token.contact_id:
        raise AppException(
            status_code=404,
            message="Price tag request not found.",
            code="NOT_FOUND",
        )

    result = PriceTagRequestService.transition_status(
        db, request_id, STATUS_CHANGES_REQUESTED,
    )
    # Store the note on the request (could be moved to a dedicated notes table later).
    result.notes = (result.notes or "") + f"\n[Changes requested]: {payload.note}"
    db.flush()
    db.commit()
    return PriceTagRequestResponse.model_validate(result)


# ---------------------------------------------------------------------------
# Debtor lookup
# ---------------------------------------------------------------------------


@router.get("/lookups/debtors-for-agent", response_model=list[DebtorForAgentItem])
def portal_lookup_debtors_for_agent(
    q: Optional[str] = Query(None),
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    """Scoped debtor lookup: customers by sales_agent_id + orders."""
    debtors = PriceTagRequestService.lookup_debtors_for_agent(db, token.contact_id)
    if q:
        q_lower = q.lower()
        debtors = [
            d for d in debtors
            if q_lower in (d.get("customer_name") or "").lower()
            or q_lower in (d.get("customer_code") or "").lower()
        ]
    return [DebtorForAgentItem(**d) for d in debtors]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_company(db: Session, token: PortalToken) -> str:
    """Resolve the company_id for a portal contact.

    Price tag requests are company-scoped. For now, use the default company id
    (single-tenant stub). In multi-tenant, this would resolve from the contact's
    workspace or access type.
    """
    # The Sorento company is the only one in the current single-tenant setup.
    from app.models.company import Company

    company = db.query(Company).filter(Company.is_active.is_(True)).first()
    if company:
        return company.id
    # Fallback: use the hardcoded default.
    return "00000000-0000-0000-0000-000000000001"
