"""Purchase requests / sponsorship forms API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.dependencies import get_current_user
from app.services.procurement_service import PurchaseRequestService
from app.schemas.procurement import (
    PurchaseRequestHeaderCreate,
    PurchaseRequestHeaderUpdate,
    PurchaseRequestHeaderResponse,
    PurchaseRequestHeaderListResponse,
)
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/", response_model=ListResponse[PurchaseRequestHeaderListResponse])
async def get_purchase_requests(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    query: Optional[str] = Query(None),
    request_type: Optional[str] = Query(None, description="purchase_request or sponsorship_form"),
    sort: Optional[str] = Query("request_date"),
    dir: Optional[str] = Query("desc"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List purchase requests and sponsorship forms with pagination."""
    try:
        service = PurchaseRequestService(db)
        result = service.list_requests(
            page=page,
            limit=limit,
            query=query,
            request_type=request_type,
            sort_field=sort or "request_date",
            sort_dir=dir or "desc",
        )
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{request_id}", response_model=PurchaseRequestHeaderResponse)
async def get_purchase_request(
    request_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a purchase request or sponsorship form by ID with lines."""
    try:
        service = PurchaseRequestService(db)
        return service.get_request(request_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=PurchaseRequestHeaderResponse, status_code=status.HTTP_201_CREATED)
async def create_purchase_request(
    data: PurchaseRequestHeaderCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a purchase request or sponsorship form."""
    try:
        service = PurchaseRequestService(db)
        return service.create_request(data)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{request_id}", response_model=PurchaseRequestHeaderResponse)
async def update_purchase_request(
    request_id: str,
    data: PurchaseRequestHeaderUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a purchase request or sponsorship form."""
    try:
        service = PurchaseRequestService(db)
        return service.update_request(request_id, data)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{request_id}", status_code=status.HTTP_200_OK)
async def delete_purchase_request(
    request_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a purchase request or sponsorship form."""
    try:
        service = PurchaseRequestService(db)
        service.delete_request(request_id)
        return {"message": "Purchase request deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
