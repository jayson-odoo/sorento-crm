"""SPO Allocations API routes."""
import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, HTTPException, status, Body, File, UploadFile
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
from app.database import get_db
from app.dependencies import get_current_user, get_current_user_or_api_key, require_permission
from app.services.procurement_service import SPOAllocationService
from app.schemas.procurement import (
    SPOAllocationCreate,
    SPOAllocationUpdate,
    SPOAllocationResponse,
    LinkedGRNSimple,
    ShipmentWithAllocationsGroup,
    SPOWithAllocationsGroup,
    BulkDeleteSPOAllocationsRequest,
)
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/grouped-by-shipment", response_model=ListResponse[ShipmentWithAllocationsGroup])
async def get_spo_allocations_grouped_by_shipment(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=1000),
    query: Optional[str] = Query(None),
    product_code: Optional[str] = Query(None),
    warehouse_id: Optional[str] = Query(None),
    receipt_status: Optional[str] = Query(None),
    sort: Optional[str] = Query("shipment_number"),
    dir: Optional[str] = Query("asc"),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db),
):
    """Get SPO allocations grouped by inbound shipment (for list view with expandable groups)."""
    try:
        service = SPOAllocationService(db)
        result = service.list_allocations_grouped_by_shipment(
            page=page,
            limit=limit,
            query=query,
            product_code=product_code,
            warehouse_id=warehouse_id,
            receipt_status=receipt_status,
            sort_field=sort or "shipment_number",
            sort_dir=dir or "asc",
        )
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/grouped-by-spo-number", response_model=ListResponse[SPOWithAllocationsGroup])
async def get_spo_allocations_grouped_by_spo_number(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=1000),
    query: Optional[str] = Query(None),
    product_code: Optional[str] = Query(None),
    warehouse_id: Optional[str] = Query(None),
    receipt_status: Optional[str] = Query(None),
    sort: Optional[str] = Query("spo_number"),
    dir: Optional[str] = Query("asc"),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db),
):
    """Get SPO allocations grouped by SPO number (for list view by SPO)."""
    try:
        service = SPOAllocationService(db)
        result = service.list_allocations_grouped_by_spo_number(
            page=page,
            limit=limit,
            query=query,
            product_code=product_code,
            warehouse_id=warehouse_id,
            receipt_status=receipt_status,
            sort_field=sort or "spo_number",
            sort_dir=dir or "asc",
        )
        return result
    except Exception as e:
        logger.exception("grouped-by-spo-number failed: %s", e)
        raise handle_internal_error(str(e))


@router.post("/import", status_code=status.HTTP_202_ACCEPTED)
async def import_spo_allocations(
    files: List[UploadFile] = File(..., description="One or more Excel files (.xlsx). Filename = SPO number."),
    validate_only: bool = Query(False, description="If true, validate the first file only and return errors/warnings (no import)."),
    current_user: dict = Depends(require_permission("procurement.spo_allocations.import")),
    db: Session = Depends(get_db),
):
    """Queue SPO allocation import jobs. Use validate_only=true to test the first file without importing."""
    from fastapi.responses import JSONResponse
    from app.services.job_service import JobService
    from app.services.queue_service import enqueue_job
    from app.tasks.import_tasks import process_spo_import, validate_spo_import

    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one file is required.",
        )

    for upload in files:
        if not upload.filename or not upload.filename.lower().endswith((".xlsx", ".xls")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file type: {upload.filename}. Please upload Excel (.xlsx or .xls).",
            )

    if validate_only:
        upload = files[0]
        file_data = await upload.read()
        result = validate_spo_import(file_data, upload.filename or "unknown.xlsx")
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "valid": result["valid"],
                "errors": result["errors"],
                "warnings": result.get("warnings", []),
                "summary": result.get("summary"),
            },
        )

    job_ids = []
    job_service = JobService(db)
    for upload in files:
        file_data = await upload.read()
        job = job_service.create_job(
            job_type="spo_import",
            user_id=current_user["id"],
            filename=upload.filename,
        )
        db.commit()
        rq_job = enqueue_job(
            process_spo_import,
            str(job.id),
            file_data,
            upload.filename or "unknown.xlsx",
            current_user["id"],
            queue_name="imports",
            job_timeout=3600,
        )
        job_service.update_job_with_rq_id(job, rq_job.id)
        job_ids.append(rq_job.id)

    return {
        "message": f"{len(job_ids)} import job(s) queued.",
        "job_ids": job_ids,
    }


@router.get("/", response_model=ListResponse[SPOAllocationResponse])
async def get_spo_allocations(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=1000),
    query: Optional[str] = Query(None),
    shipment_id: Optional[str] = Query(None),
    warehouse_id: Optional[str] = Query(None),
    receipt_status: Optional[str] = Query(None),
    sort: Optional[str] = Query("created_at"),
    dir: Optional[str] = Query("asc"),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get SPO allocations with pagination, filtering, and sorting."""
    try:
        service = SPOAllocationService(db)
        result = service.list_allocations(
            page=page,
            limit=limit,
            query=query,
            shipment_id=shipment_id,
            warehouse_id=warehouse_id,
            receipt_status=receipt_status,
            sort_field=sort or "created_at",
            sort_dir=dir or "asc"
        )
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{allocation_id}", response_model=SPOAllocationResponse)
async def get_spo_allocation(
    allocation_id: str,
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get a single SPO allocation by ID. quantity_received is computed on load (sum quantity_expected from approved GRN lines); returns linked GRNs."""
    try:
        service = SPOAllocationService(db)
        allocation = service.get_allocation(allocation_id)
        computed_received = service.compute_received_for_allocation(allocation_id)
        receipt_status = "received" if computed_received >= (allocation.allocated_quantity or 0) else "pending"
        linked = service.get_linked_grns_for_spo(allocation.spo_number)
        linked_grns_list = []
        for g in linked:
            try:
                linked_grns_list.append(LinkedGRNSimple(
                    id=str(g["id"]),
                    picking_number=g.get("picking_number"),
                    picking_status=g.get("picking_status"),
                    picking_date=g.get("picking_date"),
                ))
            except Exception:
                continue
        response = SPOAllocationResponse.model_validate(allocation)
        out = response.model_dump()
        out["quantity_received"] = computed_received
        out["receipt_status"] = receipt_status
        out["linked_grns"] = linked_grns_list
        return SPOAllocationResponse(**out)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "get_spo_allocation failed for allocation_id=%s: %s",
            allocation_id,
            str(e),
            exc_info=True,
        )
        raise handle_internal_error(str(e))


@router.post("/", response_model=SPOAllocationResponse, status_code=status.HTTP_201_CREATED)
async def create_spo_allocation(
    allocation_data: SPOAllocationCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new SPO allocation."""
    try:
        service = SPOAllocationService(db)
        allocation = service.create_allocation(allocation_data, current_user["id"])
        return allocation
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/bulk", status_code=status.HTTP_200_OK)
async def bulk_delete_spo_allocations(
    body: BulkDeleteSPOAllocationsRequest = Body(...),
    current_user: dict = Depends(require_permission("procurement.spo_allocations.delete")),
    db: Session = Depends(get_db)
):
    """Bulk delete SPO allocations by ID."""
    try:
        service = SPOAllocationService(db)
        return service.bulk_delete_allocations(body.ids)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{allocation_id}", response_model=SPOAllocationResponse)
async def update_spo_allocation(
    allocation_id: str,
    allocation_data: SPOAllocationUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an SPO allocation."""
    try:
        service = SPOAllocationService(db)
        allocation = service.update_allocation(allocation_id, allocation_data)
        return allocation
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{allocation_id}", status_code=status.HTTP_200_OK)
async def delete_spo_allocation(
    allocation_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete an SPO allocation."""
    try:
        service = SPOAllocationService(db)
        service.delete_allocation(allocation_id)
        return {"message": "SPO allocation deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
