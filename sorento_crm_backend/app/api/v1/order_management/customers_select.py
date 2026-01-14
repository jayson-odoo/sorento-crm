"""Customer select endpoint for dropdowns."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import get_current_user
from app.models.order import Customer
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/select")
async def get_customers_select(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get customers for select dropdowns."""
    try:
        customers = db.query(Customer).filter(Customer.is_active == True).all()
        return {
            "data": customers,
            "pagination": {"total": len(customers), "page": 1, "limit": len(customers)},
            "empty": len(customers) == 0
        }
    except Exception as e:
        raise handle_internal_error(str(e))
