"""Stock API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user
from app.services.inventory_service import StockService
from app.schemas.inventory import StockResponse, StockDashboardResponse
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/balance", response_model=ListResponse[StockResponse])
async def get_stock_balance(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    warehouse_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get stock balance with pagination."""
    try:
        service = StockService(db)
        result = service.list_stock(page=page, limit=limit, warehouse_id=warehouse_id)
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/dashboard", response_model=StockDashboardResponse)
async def get_stock_dashboard(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get stock dashboard statistics."""
    try:
        service = StockService(db)
        result = service.get_stock_dashboard()
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/alerts")
async def get_stock_alerts(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get low stock alerts."""
    try:
        service = StockService(db)
        alerts = service.get_stock_alerts()
        return alerts
    except Exception as e:
        raise handle_internal_error(str(e))
