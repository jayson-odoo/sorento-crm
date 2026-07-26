"""Job status API routes."""
import csv
import io
import json

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import String, cast, or_
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user
from app.services.job_service import JobService
from app.services.company_scope import admin_listing_company_filter
from app.services.import_outcome_codes import label_for
from app.models.job import ImportJob, ImportJobRow
from app.schemas.job import ImportJobResponse, ImportJobRowResponse, JobStatusResponse
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/jobs", response_model=ListResponse[ImportJobResponse])
async def list_jobs(
    job_type: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List import jobs."""
    try:
        from app.models.job import JobStatus
        
        job_service = JobService(db)
        job_status = None
        if status_filter:
            try:
                job_status = JobStatus(status_filter)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status: {status_filter}"
                )
        
        offset = (page - 1) * limit
        jobs = job_service.list_jobs(
            user_id=current_user["id"],
            job_type=job_type,
            status=job_status,
            limit=limit,
            offset=offset
        )
        
        # Sync status from RQ
        for job in jobs:
            job_service.sync_job_status(str(getattr(job, "job_id")))
        
        # Get actual total count
        count_query = job_service.db.query(ImportJob).filter(ImportJob.user_id == current_user["id"])
        if job_type:
            count_query = count_query.filter(ImportJob.job_type == job_type)
        if job_status:
            count_query = count_query.filter(ImportJob.status == job_status.value)
        count_scope_filter = admin_listing_company_filter(db, ImportJob.company_id)
        if count_scope_filter is not None:
            count_query = count_query.filter(count_scope_filter)
        total_count = count_query.count()
        
        # Convert jobs to response format, ensuring UUIDs are strings
        jobs_data = []
        for job in jobs:
            job_dict = {
                'id': str(job.id),
                'job_id': job.job_id,
                'job_type': job.job_type,
                'status': job.status if isinstance(job.status, str) else job.status.value,
                'user_id': job.user_id,
                'filename': job.filename,
                'total_rows': job.total_rows,
                'processed_rows': job.processed_rows,
                'successful_rows': job.successful_rows,
                'failed_rows': job.failed_rows,
                'skipped_rows': job.skipped_rows,
                'result': job.result,
                'error': job.error,
                'created_at': job.created_at,
                'started_at': job.started_at,
                'completed_at': job.completed_at,
                'updated_at': getattr(job, 'updated_at', None),
                'job_metadata': job.job_metadata,
                'source_filename': getattr(job, 'source_filename', None),
                'source_file_size': getattr(job, 'source_file_size', None),
                'has_source_file': bool(getattr(job, 'source_file_key', None)),
            }
            jobs_data.append(job_dict)
        
        return {
            'data': jobs_data,
            'pagination': {
                'total': total_count,
                'page': page,
                'limit': limit,
            },
            'empty': total_count == 0
        }
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/jobs/{job_id}", response_model=ImportJobResponse)
async def get_job(
    job_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single import job by ID (accepts RQ job_id or DB id)."""
    try:
        job_service = JobService(db)
        job = job_service.get_job(job_id) or job_service.get_job_by_db_id(job_id)
        
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found"
            )
        
        # Verify ownership
        if job.user_id != current_user["id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        # Sync status from RQ (use job.job_id, the RQ id)
        job_service.sync_job_status(str(getattr(job, "job_id")))
        
        # Refresh job from DB
        db.refresh(job)
        
        # Convert to response format with string ID
        return {
            'id': str(job.id),
            'job_id': job.job_id,
            'job_type': job.job_type,
            'status': job.status if isinstance(job.status, str) else job.status.value,
            'user_id': job.user_id,
            'filename': job.filename,
            'total_rows': job.total_rows,
            'processed_rows': job.processed_rows,
            'successful_rows': job.successful_rows,
            'failed_rows': job.failed_rows,
            'skipped_rows': job.skipped_rows,
            'result': job.result,
            'error': job.error,
            'created_at': job.created_at,
            'started_at': job.started_at,
            'completed_at': job.completed_at,
            'updated_at': getattr(job, 'updated_at', None),
            'job_metadata': job.job_metadata,
            'source_filename': getattr(job, 'source_filename', None),
            'source_file_size': getattr(job, 'source_file_size', None),
            'has_source_file': bool(getattr(job, 'source_file_key', None)),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


def _resolve_owned_job(db: Session, job_id: str, current_user: dict) -> ImportJob:
    """Job lookup + ownership check shared by the row endpoints (mirrors get_job).

    A malformed id is "not found", not a server error: the DB id column is a UUID,
    so a non-uuid path segment raises in the driver rather than returning no rows.
    """
    job_service = JobService(db)
    job = None
    for lookup in (job_service.get_job, job_service.get_job_by_db_id):
        try:
            job = lookup(job_id)
        except Exception:
            db.rollback()
            job = None
        if job:
            break
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job.user_id != current_user["id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return job


def _job_rows_query(db: Session, job: ImportJob, outcome, code, query):
    """Filtered ImportJobRow query for one job."""
    q = db.query(ImportJobRow).filter(ImportJobRow.import_job_id == job.id)
    if outcome:
        q = q.filter(ImportJobRow.outcome == outcome)
    if code:
        q = q.filter(ImportJobRow.code == code)
    if query:
        needle = f"%{query.strip()}%"
        q = q.filter(
            or_(
                ImportJobRow.message.ilike(needle),
                ImportJobRow.value.ilike(needle),
                cast(ImportJobRow.identity, String).ilike(needle),
            )
        )
    return q


@router.get("/jobs/{job_id}/rows", response_model=ListResponse[ImportJobRowResponse])
async def list_job_rows(
    job_id: str,
    outcome: Optional[str] = Query(None, description="created|updated|unchanged|skipped|failed"),
    code: Optional[str] = Query(None, description="reason code from the job's breakdown"),
    query: Optional[str] = Query(None, description="free text over detail / value / identity"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    sort: Optional[str] = Query(None),
    dir: str = Query("asc"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Per-row outcomes for one import job.

    A job with no captured rows (ran before row capture, or its detail has aged out
    of the retention window) returns an empty list rather than an error.
    """
    try:
        job = _resolve_owned_job(db, job_id, current_user)
        q = _job_rows_query(db, job, outcome, code, query)
        total = q.count()

        sort_column = {
            "row_number": ImportJobRow.row_number,
            "outcome": ImportJobRow.outcome,
            "code": ImportJobRow.code,
            "created_at": ImportJobRow.created_at,
        }.get(sort or "row_number", ImportJobRow.row_number)
        q = q.order_by(
            sort_column.desc() if (dir or "asc").lower() == "desc" else sort_column.asc(),
            ImportJobRow.id.asc(),  # stable tiebreak so paging never repeats a row
        )

        rows = q.offset((page - 1) * limit).limit(limit).all()
        return ListResponse(
            data=[
                ImportJobRowResponse(
                    id=str(r.id),
                    row_number=r.row_number,
                    outcome=r.outcome,
                    code=r.code,
                    label=label_for(r.code),
                    message=r.message,
                    value=r.value,
                    identity=r.identity,
                    entity_type=r.entity_type,
                    entity_id=r.entity_id,
                )
                for r in rows
            ],
            pagination={"total": total, "page": page, "limit": limit},
            empty=total == 0,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/jobs/{job_id}/rows/export")
async def export_job_rows(
    job_id: str,
    outcome: Optional[str] = Query(None),
    code: Optional[str] = Query(None),
    query: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Stream the FILTERED row set as CSV — the whole set, not a page.

    Keyset-paginated generator so a 200k-row job never materialises in memory.
    """
    try:
        job = _resolve_owned_job(db, job_id, current_user)
        base_query = _job_rows_query(db, job, outcome, code, query)

        def rows_csv():
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(
                ["row", "outcome", "code", "reason", "detail", "value", "identity", "entity_id"]
            )
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)

            last_id = None
            while True:
                chunk_q = base_query.order_by(ImportJobRow.id.asc())
                if last_id is not None:
                    chunk_q = chunk_q.filter(ImportJobRow.id > last_id)
                chunk = chunk_q.limit(2000).all()
                if not chunk:
                    break
                for r in chunk:
                    writer.writerow(
                        [
                            r.row_number if r.row_number is not None else "",
                            r.outcome,
                            r.code,
                            label_for(r.code),
                            r.message or "",
                            r.value or "",
                            json.dumps(r.identity, ensure_ascii=False) if r.identity else "",
                            r.entity_id or "",
                        ]
                    )
                yield buffer.getvalue()
                buffer.seek(0)
                buffer.truncate(0)
                last_id = chunk[-1].id

        filename = f"import-job-{job.job_id}-rows.csv"
        return StreamingResponse(
            rows_csv(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/jobs/{job_id}/source")
async def download_job_source_file(
    job_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return a fresh signed URL for the retained original upload of an import job.

    Accepts RQ job_id or DB id. Owner-only (mirrors get_job). 404 when the job has no
    retained source file (older jobs, non-file imports, or a best-effort storage miss).
    """
    try:
        job_service = JobService(db)
        job = job_service.get_job(job_id) or job_service.get_job_by_db_id(job_id)

        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        if job.user_id != current_user["id"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

        key = getattr(job, "source_file_key", None)
        if not key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No source file was retained for this import job.",
            )

        from app.services.storage_router import resolve_signed_url

        url = resolve_signed_url(
            key,
            provider=getattr(job, "source_file_provider", None),
            expires_in=3600,
        )
        if not url:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not generate a download link for the source file.",
            )
        return {
            "url": url,
            "filename": getattr(job, "source_filename", None) or job.filename,
            "size": getattr(job, "source_file_size", None),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/jobs/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get job status (lightweight endpoint for polling). Accepts RQ job_id or DB id."""
    try:
        job_service = JobService(db)
        job = job_service.get_job(job_id) or job_service.get_job_by_db_id(job_id)
        
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found"
            )
        
        # Verify ownership
        if job.user_id != current_user["id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        # Sync status from RQ (use job.job_id, the RQ id)
        job_service.sync_job_status(str(getattr(job, "job_id")))
        db.refresh(job)
        
        progress = None
        total_rows = getattr(job, "total_rows", 0)
        processed_rows = getattr(job, "processed_rows", 0)
        successful_rows = getattr(job, "successful_rows", 0)
        failed_rows = getattr(job, "failed_rows", 0)
        skipped_rows = getattr(job, "skipped_rows", 0)
        if isinstance(total_rows, int) and total_rows > 0:
            progress = {
                'total': total_rows,
                'processed': processed_rows,
                'successful': successful_rows,
                'failed': failed_rows,
                'skipped': skipped_rows,
                'percentage': int((processed_rows / total_rows) * 100) if total_rows > 0 else 0
            }
        
        return {
            'job_id': job.job_id,
            'status': job.status if isinstance(job.status, str) else job.status.value,
            'progress': progress,
            'result': job.result,
            'error': job.error
        }
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/jobs/{job_id}/cancel", status_code=status.HTTP_200_OK)
async def cancel_job(
    job_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cancel a job. Accepts RQ job_id or DB id."""
    try:
        job_service = JobService(db)
        job = job_service.get_job(job_id) or job_service.get_job_by_db_id(job_id)
        
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found"
            )
        
        # Verify ownership
        if job.user_id != current_user["id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        success = job_service.cancel_job(job_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to cancel job"
            )
        
        return {'message': 'Job cancelled successfully'}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
