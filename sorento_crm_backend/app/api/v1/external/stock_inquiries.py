"""External API: create stock inquiries and notify teams.

Auth: X-API-Key header (get_external_api_user).
"""

import logging

from fastapi import APIRouter, Depends, Body, HTTPException, status, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.schemas.procurement import StockInquiryCreate, StockInquiryResponse
from app.services.procurement_service import StockInquiryService
from app.services.error_handler import handle_internal_error

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/", response_model=StockInquiryResponse, status_code=status.HTTP_201_CREATED)
async def create_stock_inquiry_external(
    response: Response,
    inquiry_data: StockInquiryCreate = Body(...),
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """Create stock inquiry via external API and notify Project Sales team (in-app + email to all)."""
    try:
        service = StockInquiryService(db)
        inquiry, outcome = service.create_inquiry(
            inquiry_data,
            require_user_confirmation=True,
        )
        if outcome == "resubmitted":
            response.status_code = status.HTTP_200_OK
        try:
            # Notify project sales team (lead_time_enquiries / project_sales). Email is enqueued so
            # API returns immediately; Notification Delivery Processor sends it in the background.
            if outcome == "resubmitted":
                service._notify_team_stock_inquiry(
                    inquiry_id=str(inquiry.id),
                    agent_code="lead_time_enquiries",
                    team_assignment_code="project_sales",
                    title="Stock Inquiry updated (edited rejected form)",
                    intro_plain="Dear Project Sales Team,\n\nA rejected stock inquiry has been edited and submitted for your review.",
                    intro_html="Dear Project Sales Team,<br /><br />A rejected stock inquiry has been edited and submitted for your review.",
                    event_type="external_resubmitted",
                    sync_email=False,
                )
            else:
                service._notify_team_stock_inquiry(
                    inquiry_id=str(inquiry.id),
                    agent_code="lead_time_enquiries",
                    team_assignment_code="project_sales",
                    title="New Stock Inquiry created",
                    intro_plain="Dear Project Sales Team,\n\nA new stock inquiry has been created and requires your review.",
                    intro_html="Dear Project Sales Team,<br /><br />A new stock inquiry has been created and requires your review.",
                    event_type="external_created",
                    sync_email=False,
                )
        except Exception as e:
            # Don't fail the API call if notifications fail; log for debugging (e.g. team resolution, SMTP enqueue).
            logger.warning(
                "Stock inquiry external notify failed for inquiry %s: %s",
                getattr(inquiry, "id", None),
                e,
                exc_info=True,
            )
        return service.get_inquiry_for_response(str(inquiry.id))
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))

