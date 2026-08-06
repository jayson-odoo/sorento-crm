"""Public view endpoints (no auth): token-based read-only views and optional revise actions."""
from fastapi import APIRouter, Depends, Query, HTTPException, Body
from pydantic import BaseModel

from app.database import get_db
from app.services.complaints_service import ComplaintService
from app.services.procurement_service import PurchaseRequestService, StockInquiryService
from app.services.error_handler import handle_internal_error
from app.modules.runtime.guards import ensure_public_view_links_allowed
from app.services.portal_service import PortalService
from app.models.complaints import Complaint
from app.models.procurement import StockInquiry, PurchaseRequestHeader

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


def _portal_url_for_view(db, entity: str, summary: dict) -> str | None:
    entity_id = summary.get("entity_id") if isinstance(summary, dict) else None
    if not entity_id:
        return None
    if entity == "complaint":
        row = db.query(Complaint.contact_id, Complaint.space_id).filter(Complaint.id == entity_id).first()
    elif entity == "stock-inquiry":
        row = db.query(StockInquiry.contact_id, StockInquiry.space_id).filter(StockInquiry.id == entity_id).first()
    elif entity == "request":
        row = (
            db.query(PurchaseRequestHeader.contact_id, PurchaseRequestHeader.space_id)
            .filter(PurchaseRequestHeader.id == entity_id)
            .first()
        )
    else:
        return None
    if not row:
        return None
    contact_id, space_id = row
    if not contact_id or not space_id:
        return None
    try:
        token = PortalService(db).mint_token(contact_id, space_id)
        return PortalService(db).build_portal_url(token.token)
    except Exception:  # noqa: BLE001
        return None


@router.get("/{entity}")
def get_public_view(
    entity: str,
    token: str = Query(..., description="View token (shareable link)"),
    db=Depends(get_db),
):
    """Return read-only entity summary for the given view token. No auth required."""
    try:
        ensure_public_view_links_allowed(db, current_user_id=None)
        summary = _get_summary_by_entity(db, entity, token)
        if isinstance(summary, dict):
            summary["portal_url"] = _portal_url_for_view(db, entity, summary)
        return summary
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{entity}/revise")
def request_public_view_revision(
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
