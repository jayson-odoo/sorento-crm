"""Service for managing import jobs."""
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional, List
from app.models.job import ImportJob, JobStatus
from app.services.queue_service import enqueue_job, get_job_status, cancel_job as cancel_rq_job
from datetime import datetime
import uuid
import logging

logger = logging.getLogger(__name__)


class JobService:
    """Service for managing import jobs."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_job(
        self,
        job_type: str,
        user_id: str,
        filename: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> ImportJob:
        """Create a new import job record."""
        job = ImportJob(
            job_id=str(uuid.uuid4()),  # Temporary, will be updated with RQ job ID
            job_type=job_type,
            status=JobStatus.PENDING.value,  # Use enum value explicitly
            user_id=user_id,
            filename=filename,
            job_metadata=metadata or {}
        )
        self.db.add(job)
        self.db.flush()  # Get the ID
        return job
    
    def update_job_with_rq_id(self, job: ImportJob, rq_job_id: str) -> ImportJob:
        """Update job with RQ job ID."""
        job.job_id = rq_job_id
        job.status = JobStatus.QUEUED.value
        self.db.commit()
        return job
    
    def start_job(self, job_id: str) -> Optional[ImportJob]:
        """Mark job as started."""
        job = self.db.query(ImportJob).filter(ImportJob.job_id == job_id).first()
        if job:
            job.status = JobStatus.STARTED.value
            job.started_at = datetime.utcnow()
            self.db.commit()
        return job
    
    def complete_job(
        self,
        job_id: str,
        result: Optional[dict] = None,
        successful_rows: int = 0,
        failed_rows: int = 0,
        skipped_rows: int = 0,
        processed_rows: int = 0,
        total_rows: Optional[int] = None,
    ) -> Optional[ImportJob]:
        """Mark job as completed."""
        job = self.db.query(ImportJob).filter(ImportJob.job_id == job_id).first()
        if job:
            job.status = JobStatus.FINISHED.value
            job.completed_at = datetime.utcnow()
            job.result = result
            job.successful_rows = successful_rows
            job.failed_rows = failed_rows
            job.skipped_rows = skipped_rows
            job.processed_rows = processed_rows
            if total_rows is not None:
                job.total_rows = total_rows
            elif job.total_rows == 0 and processed_rows > 0:
                job.total_rows = processed_rows
            self.db.commit()
        return job
    
    def fail_job(self, job_id: str, error: str) -> Optional[ImportJob]:
        """Mark job as failed."""
        job = self.db.query(ImportJob).filter(ImportJob.job_id == job_id).first()
        if job:
            job.status = JobStatus.FAILED.value
            job.completed_at = datetime.utcnow()
            job.error = error
            self.db.commit()
        return job
    
    def get_job(self, job_id: str) -> Optional[ImportJob]:
        """Get job by RQ job ID."""
        return self.db.query(ImportJob).filter(ImportJob.job_id == job_id).first()
    
    def get_job_by_db_id(self, db_id: str) -> Optional[ImportJob]:
        """Get job by database ID."""
        return self.db.query(ImportJob).filter(ImportJob.id == db_id).first()
    
    def list_jobs(
        self,
        user_id: Optional[str] = None,
        job_type: Optional[str] = None,
        status: Optional[JobStatus] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[ImportJob]:
        """List jobs with filters."""
        query = self.db.query(ImportJob)
        
        if user_id:
            query = query.filter(ImportJob.user_id == user_id)
        if job_type:
            query = query.filter(ImportJob.job_type == job_type)
        if status:
            # Compare with enum value (string)
            query = query.filter(ImportJob.status == status.value if isinstance(status, JobStatus) else status)
        
        return query.order_by(desc(ImportJob.created_at)).limit(limit).offset(offset).all()
    
    def cancel_job(self, job_id: str) -> bool:
        """Cancel a job."""
        job = self.get_job(job_id)
        if not job:
            return False
        
        # Cancel RQ job
        if cancel_rq_job(job_id):
            job.status = JobStatus.CANCELLED.value
            job.completed_at = datetime.utcnow()
            self.db.commit()
            return True
        
        return False
    
    def sync_job_status(self, job_id: str) -> Optional[ImportJob]:
        """Sync job status from RQ."""
        job = self.get_job(job_id)
        if not job:
            return None
        
        rq_status = get_job_status(job_id)
        if not rq_status:
            return job
        
        # Update status based on RQ status
        rq_status_str = rq_status['status']
        if rq_status_str == 'started' and job.status != JobStatus.STARTED.value:
            job.status = JobStatus.STARTED.value
            if not job.started_at:
                job.started_at = datetime.utcnow()
        elif rq_status_str == 'finished' and job.status != JobStatus.FINISHED.value:
            job.status = JobStatus.FINISHED.value
            job.completed_at = datetime.utcnow()
            if rq_status.get('result'):
                job.result = rq_status['result']
        elif rq_status_str == 'failed' and job.status != JobStatus.FAILED.value:
            job.status = JobStatus.FAILED.value
            job.completed_at = datetime.utcnow()
            if rq_status.get('exc_info'):
                job.error = str(rq_status['exc_info'])
        
        self.db.commit()
        return job
