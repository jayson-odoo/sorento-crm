"""External API: create stock inquiries and notify teams.

Auth: X-API-Key header (get_external_api_user).
"""

from fastapi import APIRouter, Depends, Body, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.schemas.procurement import StockInquiryCreate, StockInquiryResponse
from app.services.procurement_service import StockInquiryService
from app.services.error_handler import handle_internal_error


router = APIRouter()


@router.post("/", response_model=StockInquiryResponse, status_code=status.HTTP_201_CREATED)
async def create_stock_inquiry_external(
    inquiry_data: StockInquiryCreate = Body(...),
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """Create stock inquiry via external API and notify Project Sales team (in-app + email to all)."""
    try:
        service = StockInquiryService(db)
        inquiry = service.create_inquiry(inquiry_data)
        try:
            # If external wants a specific frontend domain for the link, it can set FRONTEND_BASE_URL / Website URL.
            service._notify_team_stock_inquiry(
                inquiry_id=str(inquiry.id),
                agent_code="stock_inquiry_project_sales",
                title="New Stock Inquiry created",
                intro_plain="Dear Project Sales Team,\n\nA new stock inquiry has been created via system integration and requires your review.",
                intro_html="Dear Project Sales Team,<br /><br />A new stock inquiry has been created via system integration and requires your review.",
                event_type="external_created",
            )
        except Exception:
            # Don't fail the API call if notifications fail.
            pass
        return service.get_inquiry_for_response(str(inquiry.id))
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))

