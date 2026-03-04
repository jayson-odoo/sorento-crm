"""Public view endpoint (no auth): view stock inquiry by token."""
from fastapi import APIRouter, Depends, Query, HTTPException

from app.database import get_db
from app.services.procurement_service import StockInquiryService
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/stock-inquiry")
async def get_view_stock_inquiry(
    token: str = Query(..., description="View token (shareable link)"),
    db=Depends(get_db),
):
    """Return read-only stock inquiry summary for the given view token. No auth required."""
    try:
        service = StockInquiryService(db)
        summary = service.get_inquiry_summary_by_token(token)
        return summary
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
