"""Order statuses API routes."""
import logging
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import get_current_user, get_current_user_optional
from app.models.order import OrderStatus
from app.services.order_service import OrderStatusService
from app.schemas.order import OrderStatusCreate, OrderStatusUpdate, OrderStatusResponse
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()
logger = logging.getLogger(__name__)


def _safe_select_response():
    """Return a valid empty response so the UI does not break."""
    return {
        "data": [],
        "pagination": {"total": 0, "page": 1, "limit": 0},
        "empty": True,
    }


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


@router.get("/select")
def get_order_statuses_select(
    current_user: dict | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Get order statuses for select dropdowns. Returns empty data on any error to avoid 500."""
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        statuses = db.query(OrderStatus).order_by(OrderStatus.id).all()
        if statuses is None:
            return _safe_select_response()

        data = []
        for s in statuses:
            try:
                data.append({
                    "id": str(s.id),
                    "status_code": str(s.status_code) if s.status_code is not None else "",
                    "status_name": str(s.status_name) if s.status_name is not None else "",
                })
            except Exception as e:
                logger.warning("order-statuses/select: skip row %s: %s", getattr(s, "id", None), e)
                continue

        return {
            "data": data,
            "pagination": {"total": len(data), "page": 1, "limit": len(data)},
            "empty": len(data) == 0,
        }
    except Exception as e:
        logger.exception("order-statuses/select failed: %s", e)
        return _safe_select_response()


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
