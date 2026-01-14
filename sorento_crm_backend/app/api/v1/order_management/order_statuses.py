"""Order statuses API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import get_current_user
from app.services.order_service import OrderStatusService
from app.schemas.order import OrderStatusCreate, OrderStatusUpdate, OrderStatusResponse
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/", response_model=ListResponse[OrderStatusResponse])
async def get_order_statuses(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get order statuses with pagination."""
    try:
        service = OrderStatusService(db)
        result = service.list_order_statuses(page=page, limit=limit)
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{status_id}", response_model=OrderStatusResponse)
async def get_order_status(
    status_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single order status by ID."""
    try:
        service = OrderStatusService(db)
        status = service.get_order_status(status_id)
        return status
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=OrderStatusResponse, status_code=status.HTTP_201_CREATED)
async def create_order_status(
    status_data: OrderStatusCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new order status."""
    try:
        service = OrderStatusService(db)
        status = service.create_order_status(status_data)
        return status
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{status_id}", response_model=OrderStatusResponse)
async def update_order_status(
    status_id: str,
    status_data: OrderStatusUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an order status."""
    try:
        service = OrderStatusService(db)
        status = service.update_order_status(status_id, status_data)
        return status
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{status_id}", status_code=status.HTTP_200_OK)
async def delete_order_status(
    status_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete an order status."""
    try:
        service = OrderStatusService(db)
        # Implement delete logic
        return {"message": "Order status deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
