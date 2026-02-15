"""Job status API routes."""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user
from app.services.job_service import JobService
from app.models.job import ImportJob
from app.schemas.job import ImportJobResponse, JobStatusResponse
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/jobs", response_model=ListResponse[ImportJobResponse])
async def list_jobs(
    job_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List import jobs."""
    try:
        from app.models.job import JobStatus
        
        job_service = JobService(db)
        job_status = None
        if status:
            try:
                job_status = JobStatus(status)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status: {status}"
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
            job_service.sync_job_status(job.job_id)
        
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
                'job_metadata': job.job_metadata,
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
        job_service.sync_job_status(job.job_id)
        
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
            'job_metadata': job.job_metadata,
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
        job_service.sync_job_status(job.job_id)
        db.refresh(job)
        
        progress = None
        if job.total_rows > 0:
            progress = {
                'total': job.total_rows,
                'processed': job.processed_rows,
                'successful': job.successful_rows,
                'failed': job.failed_rows,
                'skipped': job.skipped_rows,
                'percentage': int((job.processed_rows / job.total_rows) * 100) if job.total_rows > 0 else 0
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
