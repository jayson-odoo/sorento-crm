"""Stock inquiries API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status, Request, Body
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user, get_current_user_or_api_key
from app.services.procurement_service import StockInquiryService
from app.schemas.procurement import StockInquiryCreate, StockInquiryUpdate, StockInquiryResponse
from app.schemas.procurement import ViewLinkRequest, ViewLinkResponse
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error
from app.config import settings as app_settings

router = APIRouter()


class BulkDeleteStockInquiriesRequest(BaseModel):
    ids: list[str]


def _respond_user_id_from_current_user(current_user: dict) -> str:
    """Get respond_user_id for SLA/response tracking; fallback to user id."""
    rid = (current_user or {}).get("respond_user_id") or (current_user or {}).get("respondUserId")
    if rid and str(rid).strip():
        return str(rid).strip()
    uid = (current_user or {}).get("id")
    if uid and str(uid).strip():
        return str(uid).strip()
    raise HTTPException(status_code=400, detail="User respond_user_id or id is required for Update & Reply.")


@router.get("/", response_model=ListResponse[StockInquiryResponse])
async def get_stock_inquiries(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    query: Optional[str] = Query(None),
    sort: Optional[str] = Query("id"),
    dir: Optional[str] = Query("desc"),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get stock inquiries with pagination and search."""
    try:
        service = StockInquiryService(db)
        # Handle empty strings or None values
        sort_field = (sort and sort.strip()) or "created_at"
        sort_dir = (dir and dir.strip()) or "desc"
        result = service.list_inquiries(page=page, limit=limit, query=query, sort_field=sort_field, sort_dir=sort_dir)
        return result
    except Exception as e:
        import logging
        import traceback
        logger = logging.getLogger(__name__)
        logger.error(f"Error in get_stock_inquiries: {str(e)}")
        logger.error(traceback.format_exc())
        raise handle_internal_error(str(e))


@router.get("/neighbours")
async def get_stock_inquiry_neighbours(
    inquiry_id: Optional[str] = Query(None, alias="id", description="Stock inquiry ID"),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Return prev_id and next_id for navigation (order: id desc)."""
    if not inquiry_id:
        return {"prev_id": None, "next_id": None}
    try:
        service = StockInquiryService(db)
        return service.get_neighbour_ids(inquiry_id)
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{inquiry_id}", response_model=StockInquiryResponse)
async def get_stock_inquiry(
    inquiry_id: str,
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get a single stock inquiry by ID."""
    try:
        service = StockInquiryService(db)
        return service.get_inquiry_for_response(inquiry_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{inquiry_id}/view-link", response_model=ViewLinkResponse)
async def get_or_create_stock_inquiry_view_link(
    inquiry_id: str,
    data: Optional[ViewLinkRequest] = Body(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get or create a shareable view link for this stock inquiry (no login required to view)."""
    try:
        service = StockInquiryService(db)
        service.get_inquiry(inquiry_id)  # ensure exists and user can access
        token = service.get_or_create_view_token(inquiry_id)
        db.commit()
        base = ((data.base_url if data else None) or getattr(app_settings, "frontend_base_url", "") or "").rstrip("/")
        view_url = f"{base}/view/stock-inquiry?token={token}" if base else f"/view/stock-inquiry?token={token}"
        return ViewLinkResponse(view_token=token, view_url=view_url)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=StockInquiryResponse, status_code=status.HTTP_201_CREATED)
async def create_stock_inquiry(
    inquiry_data: StockInquiryCreate,
    request: Request,
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Create a new stock inquiry."""
    try:
        service = StockInquiryService(db)
        inquiry = service.create_inquiry(inquiry_data)
        db.commit()
        return inquiry
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{inquiry_id}", response_model=StockInquiryResponse)
async def update_stock_inquiry(
    inquiry_id: str,
    inquiry_data: StockInquiryUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Update a stock inquiry."""
    try:
        service = StockInquiryService(db)
        inquiry = service.update_inquiry(inquiry_id, inquiry_data)
        db.commit()
        return inquiry
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{inquiry_id}/update-and-reply", response_model=StockInquiryResponse)
async def update_stock_inquiry_and_reply(
    inquiry_id: str,
    inquiry_data: StockInquiryUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Update inquiry, send purchasing response to customer via Respond.io, and mark SLA as responded."""
    try:
        respond_user_id = _respond_user_id_from_current_user(current_user)
        service = StockInquiryService(db)
        inquiry = service.update_inquiry_and_reply(
            inquiry_id,
            inquiry_data,
            respond_user_id=respond_user_id,
            request_url=str(request.url) if request else "",
        )
        db.commit()
        return inquiry
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/bulk", status_code=status.HTTP_200_OK)
async def bulk_delete_stock_inquiries(
    body: BulkDeleteStockInquiriesRequest = Body(...),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Bulk delete stock inquiries by ID."""
    try:
        service = StockInquiryService(db)
        return service.bulk_delete_inquiries(body.ids)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{inquiry_id}", status_code=status.HTTP_200_OK)
async def delete_stock_inquiry(
    inquiry_id: str,
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Delete a stock inquiry."""
    try:
        service = StockInquiryService(db)
        return service.delete_inquiry(inquiry_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
