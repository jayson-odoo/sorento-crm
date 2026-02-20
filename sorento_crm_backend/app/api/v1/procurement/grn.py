"""GRN (Goods Receipt Note) API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status, File, UploadFile
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user
from app.services.procurement_service import PickingHeaderService
from app.services.job_service import JobService
from app.services.queue_service import enqueue_job
from app.schemas.procurement import PickingHeaderCreate, PickingHeaderUpdate, PickingHeaderResponse
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/", response_model=ListResponse[PickingHeaderResponse])
async def get_grns(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    query: Optional[str] = Query(None),
    picking_status: Optional[str] = Query(None),
    inspection_status: Optional[str] = Query(None),
    sort: Optional[str] = Query("created_at"),
    dir: Optional[str] = Query("asc"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get GRNs (Goods Receipt Notes) with pagination, filtering, and sorting."""
    try:
        service = PickingHeaderService(db)
        result = service.list_grns(
            page=page,
            limit=limit,
            query=query,
            picking_status=picking_status,
            inspection_status=inspection_status,
            sort_field=sort or "created_at",
            sort_dir=dir or "asc"
        )
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/import-listing", status_code=status.HTTP_202_ACCEPTED)
async def import_grn_listing(
    file: UploadFile = File(..., description="Excel file: GRN listing (doc number, transfer from, date)"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Queue GRN listing import. Creates/updates picking headers. Processed in background; track via Import Jobs."""
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Excel file (.xlsx or .xls) required")
    file_data = await file.read()
    from app.tasks.import_tasks import process_grn_listing_import

    job_service = JobService(db)
    job = job_service.create_job(
        job_type="grn_listing_import",
        user_id=current_user["id"],
        filename=file.filename,
    )
    db.commit()
    rq_job = enqueue_job(
        process_grn_listing_import,
        str(job.id),
        file_data,
        file.filename or "unknown.xlsx",
        current_user["id"],
        queue_name="imports",
        job_timeout=3600,
    )
    job_service.update_job_with_rq_id(job, rq_job.id)
    return {"message": "GRN listing import queued.", "job_id": job.job_id, "id": str(job.id)}


@router.post("/import-lines", status_code=status.HTTP_202_ACCEPTED)
async def import_grn_lines(
    file: UploadFile = File(..., description="Excel file: GRN lines (doc no, item code, location, quantity)"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Queue GRN lines import. Creates/updates picking lines; links to headers by doc no. Processed in background."""
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Excel file (.xlsx or .xls) required")
    file_data = await file.read()
    from app.tasks.import_tasks import process_grn_lines_import

    job_service = JobService(db)
    job = job_service.create_job(
        job_type="grn_lines_import",
        user_id=current_user["id"],
        filename=file.filename,
    )
    db.commit()
    rq_job = enqueue_job(
        process_grn_lines_import,
        str(job.id),
        file_data,
        file.filename or "unknown.xlsx",
        current_user["id"],
        queue_name="imports",
        job_timeout=3600,
    )
    job_service.update_job_with_rq_id(job, rq_job.id)
    return {"message": "GRN lines import queued.", "job_id": job.job_id, "id": str(job.id)}


@router.get("/{grn_id}", response_model=PickingHeaderResponse)
async def get_grn(
    grn_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single GRN by ID."""
    try:
        service = PickingHeaderService(db)
        grn = service.get_grn(grn_id)
        return grn
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=PickingHeaderResponse, status_code=status.HTTP_201_CREATED)
async def create_grn(
    grn_data: PickingHeaderCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new GRN (Goods Receipt Note) with lines."""
    try:
        service = PickingHeaderService(db)
        grn = service.create_grn(grn_data, current_user["id"])
        return grn
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{grn_id}", response_model=PickingHeaderResponse)
async def update_grn(
    grn_id: str,
    grn_data: PickingHeaderUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a GRN."""
    try:
        service = PickingHeaderService(db)
        grn = service.update_grn(grn_id, grn_data)
        return grn
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{grn_id}", status_code=status.HTTP_200_OK)
async def delete_grn(
    grn_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a GRN (cascade will delete lines)."""
    try:
        service = PickingHeaderService(db)
        result = service.delete_grn(grn_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
