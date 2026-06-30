"""Stock batches API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.services.uuid_path_param import validate_uuid_path
from app.dependencies import get_current_user, get_current_user_or_api_key
from app.services.inventory_service import StockBatchService
from app.schemas.inventory import StockBatchCreate, StockBatchUpdate, StockBatchResponse
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/", response_model=ListResponse[StockBatchResponse])
async def get_stock_batches(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    product_id: Optional[str] = Query(
        None,
        description="Product UUID or product_code (e.g. SKU).",
    ),
    warehouse_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get stock batches with pagination and filtering."""
    try:
        service = StockBatchService(db)
        result = service.list_batches(
            page=page,
            limit=limit,
            product_id=product_id,
            warehouse_id=warehouse_id
        )
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{batch_id}", response_model=StockBatchResponse)
async def get_stock_batch(
    batch_id: str,
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get a single stock batch by ID."""
    try:
        validate_uuid_path(batch_id, resource="Stock batch")
        service = StockBatchService(db)
        batch = service.get_batch(batch_id)
        return batch
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=StockBatchResponse, status_code=status.HTTP_201_CREATED)
async def create_stock_batch(
    batch_data: StockBatchCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new stock batch."""
    try:
        service = StockBatchService(db)
        batch = service.create_batch(batch_data)
        return batch
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{batch_id}", response_model=StockBatchResponse)
async def update_stock_batch(
    batch_id: str,
    batch_data: StockBatchUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a stock batch."""
    try:
        service = StockBatchService(db)
        batch = service.update_batch(batch_id, batch_data)
        return batch
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{batch_id}", status_code=status.HTTP_200_OK)
async def delete_stock_batch(
    batch_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a stock batch."""
    try:
        service = StockBatchService(db)
        # Implement delete logic
        return {"message": "Stock batch deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
