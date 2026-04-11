"""Public view endpoints (no auth): token-based read-only views and optional revise actions."""
from fastapi import APIRouter, Depends, Query, HTTPException, Body
from pydantic import BaseModel

from app.database import get_db
from app.services.complaints_service import ComplaintService
from app.services.procurement_service import PurchaseRequestService, StockInquiryService
from app.services.error_handler import handle_internal_error
from app.modules.runtime.guards import ensure_public_view_links_allowed

router = APIRouter()


class ViewRevisePayload(BaseModel):
    token: str


def _get_summary_by_entity(db, entity: str, token: str):
    if entity == "request":
        return PurchaseRequestService(db).get_view_summary_by_token(token)
    if entity == "stock-inquiry":
        return StockInquiryService(db).get_inquiry_summary_by_token(token)
    if entity == "complaint":
        return ComplaintService(db).get_complaint_summary_by_token(token)
    raise HTTPException(status_code=404, detail="Unsupported public view entity.")


def _request_revision_by_entity(db, entity: str, token: str):
    if entity == "request":
        return PurchaseRequestService(db).request_revision_by_token(token)
    if entity == "stock-inquiry":
        return StockInquiryService(db).request_inquiry_revision_by_token(token)
    raise HTTPException(status_code=404, detail="Revision endpoint not available for this entity.")


@router.get("/{entity}")
async def get_public_view(
    entity: str,
    token: str = Query(..., description="View token (shareable link)"),
    db=Depends(get_db),
):
    """Return read-only entity summary for the given view token. No auth required."""
    try:
        ensure_public_view_links_allowed(db, current_user_id=None)
        return _get_summary_by_entity(db, entity, token)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{entity}/revise")
async def request_public_view_revision(
    entity: str,
    payload: ViewRevisePayload = Body(...),
    db=Depends(get_db),
):
    """Trigger revise webhook for supported public views."""
    try:
        ensure_public_view_links_allowed(db, current_user_id=None)
        return _request_revision_by_entity(db, entity, payload.token)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
