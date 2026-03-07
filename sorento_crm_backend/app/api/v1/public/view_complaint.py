"""Public view endpoint (no auth): view complaint by token."""
from fastapi import APIRouter, Depends, Query, HTTPException

from app.database import get_db
from app.services.complaints_service import ComplaintService
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/complaint")
async def get_view_complaint(
    token: str = Query(..., description="View token (shareable link)"),
    db=Depends(get_db),
):
    """Return read-only complaint summary for the given view token. No auth required."""
    try:
        service = ComplaintService(db)
        summary = service.get_complaint_summary_by_token(token)
        return summary
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
