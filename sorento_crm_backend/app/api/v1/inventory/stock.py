"""Stock API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user
from app.services.inventory_service import StockService
from app.schemas.inventory import StockResponse, StockDashboardResponse, BulkImportStockRequest, BulkImportStockResponse, StockLedgerResponse
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/balance", response_model=ListResponse[StockResponse])
async def get_stock_balance(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    query: Optional[str] = Query(None),
    warehouse_id: Optional[str] = Query(None),
    product_id: Optional[str] = Query(None),
    quantity_operator: Optional[str] = Query(None),
    quantity_value: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get stock balance with pagination and filtering."""
    try:
        service = StockService(db)
        result = service.list_stock(
            page=page,
            limit=limit,
            query=query,
            warehouse_id=warehouse_id,
            product_id=product_id,
            quantity_operator=quantity_operator,
            quantity_value=quantity_value
        )
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


@router.get("/balance/export")
async def export_stock_balance(
    warehouse_id: Optional[str] = Query(None),
    product_id: Optional[str] = Query(None),
    quantity_operator: Optional[str] = Query(None),
    quantity_value: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
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


@router.get("/{product_id}/{warehouse_id}/ledger", response_model=ListResponse[StockLedgerResponse])
async def get_stock_ledger_by_stock(
    product_id: str,
    warehouse_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
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


@router.post("/bulk-import", status_code=status.HTTP_202_ACCEPTED)
async def bulk_import_stock(
    import_data: BulkImportStockRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Bulk import stock from Excel data (queued).

    Updates existing stock records based on ID or product_id + warehouse_id.
    Rows without existing stock records are skipped and logged.
    Returns job ID for tracking progress.
    """
    try:
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
        job.total_rows = len(import_data.stock)
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
