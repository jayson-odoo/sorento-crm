"""Public view endpoint (no auth): view stock inquiry by token."""
from fastapi import APIRouter, Depends, Query, HTTPException, Body
from pydantic import BaseModel

from app.database import get_db
from app.services.procurement_service import StockInquiryService
from app.services.error_handler import handle_internal_error
from app.modules.runtime.guards import ensure_public_view_links_allowed

router = APIRouter()


class StockInquiryReviseRequest(BaseModel):
    token: str


@router.get("/stock-inquiry")
async def get_view_stock_inquiry(
    token: str = Query(..., description="View token (shareable link)"),
    db=Depends(get_db),
):
    """Return read-only stock inquiry summary for the given view token. No auth required."""
    try:
        ensure_public_view_links_allowed(db, current_user_id=None)
        service = StockInquiryService(db)
        summary = service.get_inquiry_summary_by_token(token)
        return summary
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/stock-inquiry/revise")
async def request_view_stock_inquiry_revision(
    payload: StockInquiryReviseRequest = Body(...),
    db=Depends(get_db),
):
    """Trigger the external revise webhook for a rejected stock inquiry public view."""
    try:
        ensure_public_view_links_allowed(db, current_user_id=None)
        service = StockInquiryService(db)
        return service.request_inquiry_revision_by_token(payload.token)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
