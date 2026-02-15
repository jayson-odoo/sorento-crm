"""Orders API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user
from app.services.order_service import OrderService
from app.schemas.order import OrderCreate, OrderUpdate, OrderResponse, BulkImportRequest, BulkImportResponse
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/", response_model=ListResponse[OrderResponse])
async def get_orders(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    query: Optional[str] = Query(None),
    customer_id: Optional[str] = Query(None),
    order_status_id: Optional[str] = Query(None),
    sort: Optional[str] = Query("created_at"),
    dir: Optional[str] = Query("asc"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get orders with pagination, filtering, and sorting."""
    try:
        service = OrderService(db)
        result = service.list_orders(
            page=page,
            limit=limit,
            query=query,
            customer_id=customer_id,
            order_status_id=order_status_id,
            sort_field=sort or "created_at",
            sort_dir=dir or "asc"
        )
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single order by ID."""
    try:
        service = OrderService(db)
        order = service.get_order(order_id)
        return order
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    order_data: OrderCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new order."""
    try:
        service = OrderService(db)
        order = service.create_order(order_data, current_user["id"])
        return order
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{order_id}", response_model=OrderResponse)
async def update_order(
    order_id: str,
    order_data: OrderUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an order."""
    try:
        service = OrderService(db)
        order = service.update_order(order_id, order_data, current_user["id"])
        return order
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{order_id}", status_code=status.HTTP_200_OK)
async def delete_order(
    order_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete an order permanently (hard delete). Use archive for retention."""
    try:
        service = OrderService(db)
        result = service.delete_order(order_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{order_id}/archive", status_code=status.HTTP_200_OK)
async def archive_order(
    order_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Archive an order (soft delete). Data remains for retention."""
    try:
        service = OrderService(db)
        result = service.archive_order(order_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{order_id}/restore", status_code=status.HTTP_200_OK)
async def restore_order(
    order_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Restore an archived order."""
    try:
        service = OrderService(db)
        result = service.restore_order(order_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/bulk-import", response_model=BulkImportResponse, status_code=status.HTTP_200_OK)
async def bulk_import_orders(
    import_data: BulkImportRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Bulk import orders from Excel data.
    
    Creates new orders or updates existing ones based on ID or order_number.
    """
    try:
        service = OrderService(db)
        result = service.bulk_import_orders(import_data.orders, current_user["id"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/import-tracking", status_code=status.HTTP_202_ACCEPTED)
async def import_order_tracking(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Import orders from Excel file with Master and Daily Tracking sheets (queued).
    
    Returns job ID for tracking progress.
    """
    try:
        if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid file type. Please upload an Excel file (.xlsx or .xls)."
            )
        file_data = await file.read()
        
        from app.services.job_service import JobService
        from app.services.queue_service import enqueue_job
        from app.tasks.import_tasks import process_order_tracking_import
        
        # Create job record
        job_service = JobService(db)
        job = job_service.create_job(
            job_type='order_tracking_import',
            user_id=current_user["id"],
            filename=file.filename
        )
        db.commit()
        
        # Enqueue job
        rq_job = enqueue_job(
            process_order_tracking_import,
            str(job.id),  # Pass DB job ID (UUID)
            file_data,
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
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise handle_internal_error(str(e))
