"""Public view endpoint (no auth): view purchase request / sponsorship form by token."""
from fastapi import APIRouter, Depends, Query, HTTPException, Body
from pydantic import BaseModel

from app.database import get_db
from app.services.procurement_service import PurchaseRequestService
from app.schemas.procurement import PublicApprovalSummaryResponse
from app.services.error_handler import handle_internal_error
from app.modules.runtime.guards import ensure_public_view_links_allowed

router = APIRouter()


class RequestRevisePayload(BaseModel):
    token: str


@router.get("/request", response_model=PublicApprovalSummaryResponse)
async def get_view_request(
    token: str = Query(..., description="View token (shareable link)"),
    db=Depends(get_db),
):
    """Return read-only request summary for the given view token. No auth required."""
    try:
        ensure_public_view_links_allowed(db, current_user_id=None)
        service = PurchaseRequestService(db)
        summary = service.get_view_summary_by_token(token)
        return summary
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/request/revise")
async def request_view_request_revision(
    payload: RequestRevisePayload = Body(...),
    db=Depends(get_db),
):
    """Trigger the external revise webhook for a rejected purchase request / sponsorship form public view."""
    try:
        ensure_public_view_links_allowed(db, current_user_id=None)
        service = PurchaseRequestService(db)
        return service.request_revision_by_token(payload.token)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
