"""Job status API routes."""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user
from app.services.job_service import JobService
from app.models.job import ImportJob
from app.schemas.job import ImportJobResponse, JobStatusResponse
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


@router.get("/jobs/{job_id}/source")
async def download_job_source_file(
    job_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Stream the retained original upload of an import job as a file download.

    Accepts RQ job_id or DB id. Owner-only (mirrors get_job). 404 when the job has no
    retained source file (older jobs, non-file imports, or a best-effort storage miss).
    Streamed same-origin (not a redirect to the signed CDN URL) so the browser downloads
    it via an anchor without navigating away from the SPA.
    """
    from fastapi import Response
    from urllib.parse import quote

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

        from app.services.storage_router import get_backend

        try:
            data = get_backend(getattr(job, "source_file_provider", None)).download_file(key)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not read the source file from storage.",
            )

        filename = getattr(job, "source_filename", None) or job.filename or "import-source.xlsx"
        ascii_name = filename.encode("ascii", "ignore").decode() or "import-source.xlsx"
        disposition = (
            f'attachment; filename="{ascii_name}"; '
            f"filename*=UTF-8''{quote(filename)}"
        )
        return Response(
            content=data,
            media_type="application/octet-stream",
            headers={"Content-Disposition": disposition},
        )
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
