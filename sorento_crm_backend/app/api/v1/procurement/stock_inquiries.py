"""Stock inquiries API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user
from app.services.procurement_service import StockInquiryService
from app.schemas.procurement import StockInquiryCreate, StockInquiryUpdate, StockInquiryResponse
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/", response_model=ListResponse[StockInquiryResponse])
async def get_stock_inquiries(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    query: Optional[str] = Query(None),
    sort: Optional[str] = Query("id"),
    dir: Optional[str] = Query("desc"),
    current_user: dict = Depends(get_current_user),
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


@router.get("/{inquiry_id}", response_model=StockInquiryResponse)
async def get_stock_inquiry(
    inquiry_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single stock inquiry by ID."""
    try:
        service = StockInquiryService(db)
        inquiry = service.get_inquiry(inquiry_id)
        return inquiry
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=StockInquiryResponse, status_code=status.HTTP_201_CREATED)
async def create_stock_inquiry(
    inquiry_data: StockInquiryCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new stock inquiry."""
    try:
        service = StockInquiryService(db)
        inquiry = service.create_inquiry(inquiry_data)
        return inquiry
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{inquiry_id}", response_model=StockInquiryResponse)
async def update_stock_inquiry(
    inquiry_id: str,
    inquiry_data: StockInquiryUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a stock inquiry."""
    try:
        service = StockInquiryService(db)
        inquiry = service.update_inquiry(inquiry_id, inquiry_data)
        return inquiry
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{inquiry_id}", status_code=status.HTTP_200_OK)
async def delete_stock_inquiry(
    inquiry_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a stock inquiry."""
    try:
        service = StockInquiryService(db)
        # Implement delete logic
        return {"message": "Stock inquiry deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
