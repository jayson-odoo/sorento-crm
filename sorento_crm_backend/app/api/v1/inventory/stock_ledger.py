"""Stock ledger API routes."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user_or_api_key
from app.services.inventory_service import StockService
from app.schemas.inventory import StockLedgerResponse
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/", response_model=ListResponse[StockLedgerResponse])
async def get_stock_ledger(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    product_id: Optional[str] = Query(
        None,
        description="Product UUID or product_code (e.g. SKU).",
    ),
    warehouse_id: Optional[str] = Query(None),
    transaction_type: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get stock ledger entries with pagination and filtering."""
    try:
        service = StockService(db)
        result = service.list_stock_ledger(
            page=page,
            limit=limit,
            product_id=product_id,
            warehouse_id=warehouse_id,
            transaction_type=transaction_type
        )
        return result
    except Exception as e:
        raise handle_internal_error(str(e))
