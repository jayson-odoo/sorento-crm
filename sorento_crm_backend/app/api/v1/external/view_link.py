"""
External API: get shareable view link for a record by entity_type and entity_id.

Auth: X-API-Key header (get_external_api_user).
Returns the same view link as the in-app "Copy view link" (no login required to open the link).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_external_api_user
from app.modules.runtime.guards import ensure_public_view_links_allowed
from app.schemas.procurement import ViewLinkResponse
from app.services.complaints_service import ComplaintService
from app.services.procurement_service import StockInquiryService, PurchaseRequestService

router = APIRouter()

# Entity types that have a view token and public view page
VIEW_ENTITY_TYPES = {"complaint", "stock_inquiry", "purchase_request", "sponsorship_form"}
# sponsorship_form uses same view path as purchase_request
ENTITY_VIEW_PATH = {
    "complaint": "/view/complaint",
    "stock_inquiry": "/view/stock-inquiry",
    "purchase_request": "/view/request",
    "sponsorship_form": "/view/request",
}


class ViewLinkExternalRequest(BaseModel):
    """Request body for external view-link endpoint."""

    entity_type: str = Field(
        ...,
        description="One of: complaint, stock_inquiry, purchase_request, sponsorship_form",
    )
    entity_id: str = Field(..., description="ID of the record (e.g. UUID).")
    base_url: str | None = Field(
        default=None,
        description="Optional frontend base URL to build full view URL (e.g. https://fe-sorento.foundryx.my). If omitted, uses FRONTEND_BASE_URL from config or returns a relative path.",
    )


@router.post("/", response_model=ViewLinkResponse)
def get_view_link(
    payload: ViewLinkExternalRequest,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """
    Get or create a shareable view link for a record. Pass entity_type and entity_id;
    returns view_token and view_url so the record can be viewed without logging in.

    Supported entity_type: complaint, stock_inquiry, purchase_request, sponsorship_form.
    (sponsorship_form uses the same view page as purchase_request.)
    """
    entity_type = (payload.entity_type or "").strip().lower()
    if entity_type not in VIEW_ENTITY_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"entity_type must be one of: {', '.join(sorted(VIEW_ENTITY_TYPES))}",
        )
    entity_id = (payload.entity_id or "").strip()
    if not entity_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="entity_id is required.",
        )

    ensure_public_view_links_allowed(db, current_user_id=None)

    # Normalize: sponsorship_form uses purchase_request token/path
    token_entity_type = "purchase_request" if entity_type == "sponsorship_form" else entity_type
    view_path = ENTITY_VIEW_PATH[entity_type]

    try:
        if token_entity_type == "complaint":
            service = ComplaintService(db)
            service.get_complaint(entity_id)  # ensure exists
            token = service.get_or_create_view_token(entity_id)
        elif token_entity_type == "stock_inquiry":
            service = StockInquiryService(db)
            service.get_inquiry(entity_id)  # ensure exists
            token = service.get_or_create_view_token(entity_id)
        else:
            # purchase_request (and sponsorship_form)
            service = PurchaseRequestService(db)
            service.get_request(entity_id)  # ensure exists
            token = service.get_or_create_view_token(entity_id)

        db.commit()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get view link.",
        ) from e

    base = (payload.base_url or "").strip().rstrip("/")
    if not base:
        base = (getattr(settings, "frontend_base_url", None) or "").strip().rstrip("/")
    view_url = f"{base}{view_path}?token={token}" if base else f"{view_path}?token={token}"

    return ViewLinkResponse(view_token=token, view_url=view_url)
