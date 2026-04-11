"""Stock API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status, Body, Path
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import (
    get_current_user,
    get_current_user_or_api_key,
    require_permission,
    require_permission_with_api_key,
)
from app.services.inventory_service import StockService
from app.schemas.inventory import StockResponse, StockDashboardResponse, BulkImportStockRequest, BulkImportStockResponse, StockLedgerResponse
from app.schemas.common import ListResponse, ValidateImportResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


class BulkDeleteStockRequest(BaseModel):
    ids: list[str]


@router.get("/balance", response_model=ListResponse[StockResponse])
async def get_stock_balance(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=5000),
    query: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
    dir: Optional[str] = Query(None),
    warehouse_id: Optional[str] = Query(None),
    product_id: Optional[str] = Query(
        None,
        description="Product UUID or product_code (e.g. SKU).",
    ),
    quantity_operator: Optional[str] = Query(None),
    quantity_value: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="Filter by status: critical, low, normal, overstock"),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get stock balance with pagination and filtering."""
    try:
        service = StockService(db)
        result = service.list_stock(
            page=page,
            limit=limit,
            query=query,
            sort=sort,
            dir=dir,
            warehouse_id=warehouse_id,
            product_id=product_id,
            quantity_operator=quantity_operator,
            quantity_value=quantity_value,
            status=status,
        )
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/dashboard", response_model=StockDashboardResponse)
async def get_stock_dashboard(
    current_user: dict = Depends(get_current_user_or_api_key),
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
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get low stock alerts."""
    try:
        service = StockService(db)
        alerts = service.get_stock_alerts()
        return alerts
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/balance/export")
async def export_stock_balance(
    warehouse_id: Optional[str] = Query(None),
    product_id: Optional[str] = Query(
        None,
        description="Product UUID or product_code (e.g. SKU).",
    ),
    quantity_operator: Optional[str] = Query(None),
    quantity_value: Optional[str] = Query(None),
    current_user: dict = Depends(require_permission_with_api_key("inventory.stock.export")),
    db: Session = Depends(get_db)
):
    """Export all stock balance data (no pagination, returns all records)."""
    try:
        service = StockService(db)
        stock_items = service.get_all_stock_for_export(
            warehouse_id=warehouse_id,
            product_id=product_id,
            quantity_operator=quantity_operator,
            quantity_value=quantity_value
        )
        return {
            "data": stock_items,
            "total": len(stock_items)
        }
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/bulk")
async def bulk_delete_stock(
    body: BulkDeleteStockRequest = Body(...),
    current_user: dict = Depends(require_permission("inventory.stock.delete")),
    db: Session = Depends(get_db)
):
    """Bulk delete stock records by id. Requires inventory.stock.delete permission."""
    try:
        service = StockService(db)
        result = service.bulk_delete_stock(body.ids)
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{product_id}/{warehouse_id}/ledger", response_model=ListResponse[StockLedgerResponse])
async def get_stock_ledger_by_stock(
    product_id: str = Path(
        ...,
        description="Product UUID or product_code (e.g. SKU).",
    ),
    warehouse_id: str = Path(..., description="Warehouse id (UUID)."),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=5000),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get stock ledger entries for a specific product and warehouse."""
    try:
        service = StockService(db)
        result = service.get_stock_ledger_by_stock(
            product_id=product_id,
            warehouse_id=warehouse_id,
            page=page,
            limit=limit
        )
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post(
    "/bulk-import",
    status_code=status.HTTP_202_ACCEPTED,
    responses={200: {"description": "Validation only (validate_only=true)", "model": ValidateImportResponse}},
)
async def bulk_import_stock(
    import_data: BulkImportStockRequest,
    current_user: dict = Depends(require_permission("inventory.stock.import")),
    db: Session = Depends(get_db)
):
    """Bulk import stock from Excel data (queued). If validate_only=true, validate only and return errors/warnings (no job)."""
    try:
        if getattr(import_data, "validate_only", False):
            service = StockService(db)
            result = service.bulk_import_stock(
                import_data.stock, current_user["id"], validate_only=True
            )
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "valid": result["valid"],
                    "errors": result["errors"],
                    "warnings": result.get("warnings", []),
                    "summary": result.get("summary"),
                },
            )

        from app.services.job_service import JobService
        from app.services.queue_service import enqueue_job
        from app.tasks.import_tasks import process_stock_import

        # Create job record
        job_service = JobService(db)
        job = job_service.create_job(
            job_type='stock_import',
            user_id=current_user["id"],
            metadata={'total_rows': len(import_data.stock)}
        )
        setattr(job, "total_rows", len(import_data.stock))
        db.commit()
        
        # Enqueue job
        rq_job = enqueue_job(
            process_stock_import,
            str(job.id),  # Pass DB job ID (UUID)
            import_data.stock,
            current_user["id"],
            queue_name='imports',
            job_timeout=3600
        )
        
        # Update job with RQ job ID
        job_service.update_job_with_rq_id(job, rq_job.id)
        
        return {
            'job_id': rq_job.id,
            'status': 'queued',
            'message': 'Import job queued successfully'
        }
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
