"""Unauthenticated commercial quotation actions (e.g. pricing approval from email links)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.modules.commercial_core.services.commercial_quotation_price_policy import complete_pricing_approval
from app.modules.commercial_core.services.commercial_quotation_revision_service import CommercialQuotationRevisionService
from app.services.pricing_approval_token import decode_mq_pricing_approval_token

router = APIRouter()


@router.get("/master-quotations/pricing-approval/email-consume")
async def pricing_approval_email_consume(
    token: str = Query(..., min_length=10),
    approve: bool = Query(True),
    db: Session = Depends(get_db),
):
    """Validate JWT from email and approve or reject pricing; then redirect to the app."""
    try:
        mid, approver_id = decode_mq_pricing_approval_token(token)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    svc = CommercialQuotationRevisionService(db)
    try:
        mq = svc.get_master_by_id(mid)
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quotation not found.") from None

    try:
        complete_pricing_approval(
            db,
            mq,
            actor_user_id=approver_id,
            approved=approve,
            notes=None,
        )
        db.commit()
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    base = (settings.frontend_base_url or "http://localhost:3000").rstrip("/")
    q = f"pricing_approval={'approved' if approve else 'rejected'}"
    url = f"{base}?{q}" if "?" not in base else f"{base}&{q}"
    return RedirectResponse(url=url, status_code=302)
