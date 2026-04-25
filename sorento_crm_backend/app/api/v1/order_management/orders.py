"""Orders API routes."""
from datetime import datetime

from fastapi import APIRouter, Depends, Query, HTTPException, status, UploadFile, File, Body
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user, get_current_user_or_api_key, require_permission
from app.services.order_service import OrderService
from app.schemas.order import (
    OrderCreate,
    OrderUpdate,
    OrderResponse,
    OrderSimpleRef,
    OrderLineCreate,
    OrderLineUpdate,
    OrderLineResponse,
    BulkImportRequest,
    BulkImportResponse,
    BulkDeleteOrdersRequest,
    BulkDeleteOrderLinesRequest,
)
from app.schemas.common import ListResponse, ValidateImportResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/", response_model=ListResponse[OrderResponse])
async def get_orders(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=1000),
    query: Optional[str] = Query(None),
    customer_id: Optional[str] = Query(None),
    order_status_id: Optional[str] = Query(None),
    has_order_lines: Optional[str] = Query(
        None,
        description="Filter by lines: 'yes' = at least one line, 'no' = no lines, omit = all",
    ),
    has_actual_delivery_date: Optional[str] = Query(
        None,
        description="Filter by actual delivery date: 'yes' = has date, 'no' = missing date, omit = all",
    ),
    order_date_from: Optional[datetime] = Query(None, description="Filter by order date from (inclusive)"),
    order_date_to: Optional[datetime] = Query(None, description="Filter by order date to (inclusive)"),
    actual_delivery_date_from: Optional[datetime] = Query(None),
    actual_delivery_date_to: Optional[datetime] = Query(None),
    sort: Optional[str] = Query("created_at"),
    dir: Optional[str] = Query("asc"),
    current_user: dict = Depends(get_current_user_or_api_key),
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
            has_order_lines=has_order_lines,
            has_actual_delivery_date=has_actual_delivery_date,
            order_date_from=order_date_from,
            order_date_to=order_date_to,
            actual_delivery_date_from=actual_delivery_date_from,
            actual_delivery_date_to=actual_delivery_date_to,
            sort_field=sort or "created_at",
            sort_dir=dir or "asc"
        )
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/by-product", response_model=ListResponse[OrderSimpleRef])
async def get_orders_by_product(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=1000),
    query: Optional[str] = Query(None, description="Matches product code, name, description, order number, or debtor name"),
    product_id: Optional[str] = Query(None),
    has_actual_delivery_date: Optional[str] = Query(
        None,
        description="Filter by actual delivery date: 'yes' = has date, 'no' = missing date, omit = all",
    ),
    order_date_from: Optional[datetime] = Query(None, description="Filter by order date from (inclusive)"),
    order_date_to: Optional[datetime] = Query(None, description="Filter by order date to (inclusive)"),
    actual_delivery_date_from: Optional[datetime] = Query(None),
    actual_delivery_date_to: Optional[datetime] = Query(None),
    sort: Optional[str] = Query("order_date"),
    dir: Optional[str] = Query("desc"),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get distinct orders matched by product search."""
    try:
        service = OrderService(db)
        return service.list_orders_by_product(
            page=page,
            limit=limit,
            query=query,
            product_id=product_id,
            has_actual_delivery_date=has_actual_delivery_date,
            order_date_from=order_date_from,
            order_date_to=order_date_to,
            actual_delivery_date_from=actual_delivery_date_from,
            actual_delivery_date_to=actual_delivery_date_to,
            sort_field=sort or "order_date",
            sort_dir=dir or "desc",
        )
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    current_user: dict = Depends(get_current_user_or_api_key),
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


@router.delete("/bulk", status_code=status.HTTP_200_OK)
async def bulk_delete_orders(
    body: BulkDeleteOrdersRequest = Body(...),
    current_user: dict = Depends(require_permission("order_management.orders.delete")),
    db: Session = Depends(get_db)
):
    """Bulk delete orders by ID."""
    try:
        service = OrderService(db)
        return service.bulk_delete_orders(body.ids)
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


@router.post("/{order_id}/lines", response_model=OrderLineResponse, status_code=status.HTTP_201_CREATED)
async def create_order_line(
    order_id: str,
    data: OrderLineCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a line to an order (delivery order detail)."""
    try:
        service = OrderService(db)
        line = service.create_order_line(order_id, data)
        return line
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{order_id}/lines/{line_id}", response_model=OrderLineResponse)
async def update_order_line(
    order_id: str,
    line_id: str,
    data: OrderLineUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update an order line."""
    try:
        service = OrderService(db)
        line = service.update_order_line(order_id, line_id, data)
        return line
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{order_id}/lines/{line_id}", status_code=status.HTTP_200_OK)
async def delete_order_line(
    order_id: str,
    line_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove an order line."""
    try:
        service = OrderService(db)
        return service.delete_order_line(order_id, line_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{order_id}/lines/bulk-delete", status_code=status.HTTP_200_OK)
async def bulk_delete_order_lines(
    order_id: str,
    body: BulkDeleteOrderLinesRequest = Body(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete multiple order lines from one order."""
    try:
        service = OrderService(db)
        return service.bulk_delete_order_lines(order_id, body.ids)
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
    current_user: dict = Depends(require_permission("order_management.orders.import")),
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
    validate_only: bool = Query(False, description="If true, validate file only and return errors/warnings (no import)."),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Import orders from Excel file with Master and Daily Tracking sheets (queued). Use validate_only=true to test without importing."""
    try:
        if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid file type. Please upload an Excel file (.xlsx or .xls)."
            )
        file_data = await file.read()

        if validate_only:
            service = OrderService(db)
            result = service.import_excel_tracking(file_data, current_user["id"], validate_only=True)
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "valid": result["valid"],
                    "errors": result["errors"],
                    "warnings": result["warnings"],
                    "summary": result.get("summary"),
                },
            )

        from app.services.job_service import JobService
        from app.services.queue_service import enqueue_job
        from app.tasks.import_tasks import process_order_tracking_import

        job_service = JobService(db)
        job = job_service.create_job(
            job_type='order_tracking_import',
            user_id=current_user["id"],
            filename=file.filename
        )
        db.commit()

        rq_job = enqueue_job(
            process_order_tracking_import,
            str(job.id),
            file_data,
            current_user["id"],
            queue_name='imports',
            job_timeout=3600
        )
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


@router.post("/import-order-lines", status_code=status.HTTP_202_ACCEPTED)
async def import_delivery_order_detail(
    file: UploadFile = File(...),
    validate_only: bool = Query(False, description="If true, validate file only and return errors/warnings (no import)."),
    current_user: dict = Depends(require_permission("order_management.orders.import")),
    db: Session = Depends(get_db),
):
    """Import delivery order detail (order lines) from Excel. Uses doc no -> order, item code -> product, location -> warehouse. Upserts by (order, product, warehouse)."""
    try:
        if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid file type. Please upload an Excel file (.xlsx or .xls)."
            )
        file_data = await file.read()
        if validate_only:
            service = OrderService(db)
            result = service.validate_delivery_order_detail_excel(file_data)
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "valid": result["valid"],
                    "errors": result["errors"],
                    "warnings": result["warnings"],
                    "summary": result.get("summary"),
                },
            )

        from app.services.job_service import JobService
        from app.services.queue_service import enqueue_job
        from app.tasks.import_tasks import process_delivery_order_detail_import

        job_service = JobService(db)
        job = job_service.create_job(
            job_type="delivery_order_detail_import",
            user_id=current_user["id"],
            filename=file.filename,
        )
        db.commit()

        rq_job = enqueue_job(
            process_delivery_order_detail_import,
            str(job.id),
            file_data,
            file.filename or "upload.xlsx",
            current_user["id"],
            queue_name="imports",
            job_timeout=3600,
        )
        job_service.update_job_with_rq_id(job, rq_job.id)

        return {
            "job_id": rq_job.id,
            "status": "queued",
            "message": "Delivery order detail import job queued successfully",
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise handle_internal_error(str(e))
