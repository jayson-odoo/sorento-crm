"""Order status select endpoint."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import get_current_user
from app.models.order import OrderStatus
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/select")
async def get_order_statuses_select(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get order statuses for select dropdowns."""
    try:
        statuses = db.query(OrderStatus).order_by(OrderStatus.sequence).all()
        return {
            "data": statuses,
            "pagination": {"total": len(statuses), "page": 1, "limit": len(statuses)},
            "empty": len(statuses) == 0
        }
    except Exception as e:
        raise handle_internal_error(str(e))
