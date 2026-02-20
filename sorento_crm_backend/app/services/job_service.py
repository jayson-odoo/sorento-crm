"""Service for managing import jobs."""
import logging
import threading
import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.job import ImportJob, JobStatus
from app.services.queue_service import enqueue_job, get_job_status, cancel_job as cancel_rq_job

logger = logging.getLogger(__name__)


def _notify_import_job_event(
    db: Session,
    job: ImportJob,
    event_type: str,
    title: str,
    body: str,
) -> None:
    """Create an idempotent in-app notification for the job owner. Swallowed on error."""
    try:
        from app.services.notification_service import NotificationService
        NotificationService(db).create(
            user_id=job.user_id,
            type=f"import_job_{event_type}",
            title=title,
            body=body,
            data={
                "job_id": job.job_id,
                "job_type": job.job_type,
                "filename": job.filename,
                "total_rows": job.total_rows,
                "processed_rows": job.processed_rows,
                "successful_rows": getattr(job, "successful_rows", None),
                "failed_rows": getattr(job, "failed_rows", None),
                "skipped_rows": getattr(job, "skipped_rows", None),
            },
            source_entity_type="import_job",
            source_entity_id=job.job_id,
            event_type=event_type,
        )
    except Exception as e:
        logger.warning("Failed to create import job notification: %s", e, exc_info=True)


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
        job.updated_at = datetime.utcnow()
        self.db.commit()
        return job

    def start_job(self, job_id: str) -> Optional[ImportJob]:
        """Mark job as started."""
        job = self.db.query(ImportJob).filter(ImportJob.job_id == job_id).first()
        if job:
            job.status = JobStatus.STARTED.value
            job.started_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()
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
            now = datetime.utcnow()
            job.status = JobStatus.FINISHED.value
            job.completed_at = now
            job.updated_at = now
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
            try:
                _notify_import_job_event(
                    self.db,
                    job,
                    "finished",
                    "Import job finished",
                    f"Your {job.job_type} import completed: {processed_rows}/{job.total_rows} rows processed, {successful_rows} successful, {failed_rows} failed, {skipped_rows} skipped.",
                )
            except Exception:
                pass  # Do not let notification failure mark the job as failed
        return job

    def fail_job(self, job_id: str, error: str) -> Optional[ImportJob]:
        """Mark job as failed."""
        job = self.db.query(ImportJob).filter(ImportJob.job_id == job_id).first()
        if job:
            now = datetime.utcnow()
            job.status = JobStatus.FAILED.value
            job.completed_at = now
            job.updated_at = now
            job.error = error
            self.db.commit()
            _notify_import_job_event(
                self.db,
                job,
                "failed",
                "Import job failed",
                f"Your {job.job_type} import failed: {error[:500]}",
            )
        return job

    def update_job_progress(
        self,
        job_id: str,
        processed_rows: Optional[int] = None,
        successful_rows: Optional[int] = None,
        failed_rows: Optional[int] = None,
        skipped_rows: Optional[int] = None,
        total_rows: Optional[int] = None,
        result: Optional[dict] = None,
    ) -> Optional[ImportJob]:
        """Update job progress (for long-running tasks)."""
        job = self.db.query(ImportJob).filter(ImportJob.job_id == job_id).first()
        if not job:
            return None
        if processed_rows is not None:
            job.processed_rows = processed_rows
        if successful_rows is not None:
            job.successful_rows = successful_rows
        if failed_rows is not None:
            job.failed_rows = failed_rows
        if skipped_rows is not None:
            job.skipped_rows = skipped_rows
        if total_rows is not None:
            job.total_rows = total_rows
        if result is not None:
            job.result = result
        job.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(job)
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
    
    def cancel_job(self, job_id_or_db_id: str) -> bool:
        """Cancel a job. Accepts either RQ job_id or DB id (UUID). Updates DB immediately so API returns fast; RQ stop is best-effort."""
        job = self.get_job(job_id_or_db_id) or self.get_job_by_db_id(job_id_or_db_id)
        if not job:
            return False

        if job.status not in (JobStatus.PENDING.value, JobStatus.QUEUED.value, JobStatus.STARTED.value):
            return False

        # Update DB first so the API can return immediately (avoids UI stuck on "Cancelling...")
        now = datetime.utcnow()
        job.status = JobStatus.CANCELLED.value
        job.completed_at = now
        job.updated_at = now
        self.db.commit()

        _notify_import_job_event(
            self.db,
            job,
            "cancelled",
            "Import job cancelled",
            f"Your {job.job_type} import was cancelled.",
        )

        # Tell RQ to stop the worker in background so we never block the API response
        rq_job_id = job.job_id
        def _send_rq_cancel():
            try:
                cancel_rq_job(rq_job_id)
            except Exception:
                pass

        t = threading.Thread(target=_send_rq_cancel, daemon=True)
        t.start()

        return True
    
    def sync_job_status(self, job_id: str) -> Optional[ImportJob]:
        """Sync job status from RQ. Never overwrite a job already marked CANCELLED in DB."""
        job = self.get_job(job_id)
        if not job:
            return None

        # Once we've marked as cancelled, do not overwrite with RQ (RQ may still report 'started' briefly)
        if job.status == JobStatus.CANCELLED.value:
            return job

        rq_status = get_job_status(job_id)
        if not rq_status:
            return job

        now = datetime.utcnow()
        rq_status_str = rq_status.get('status') or ''
        if rq_status_str == 'canceled':
            job.status = JobStatus.CANCELLED.value
            if not job.completed_at:
                job.completed_at = now
            job.updated_at = now
            self.db.commit()
            _notify_import_job_event(self.db, job, "cancelled", "Import job cancelled", f"Your {job.job_type} import was cancelled.")
            return job
        elif rq_status_str == 'started' and job.status != JobStatus.STARTED.value:
            job.status = JobStatus.STARTED.value
            if not job.started_at:
                job.started_at = now
            job.updated_at = now
        elif rq_status_str == 'finished' and job.status != JobStatus.FINISHED.value:
            job.status = JobStatus.FINISHED.value
            job.completed_at = now
            job.updated_at = now
            if rq_status.get('result'):
                job.result = rq_status['result']
            self.db.commit()
            _notify_import_job_event(
                self.db,
                job,
                "finished",
                "Import job finished",
                f"Your {job.job_type} import completed: {job.processed_rows}/{job.total_rows} rows processed.",
            )
            return job
        elif rq_status_str == 'failed' and job.status != JobStatus.FAILED.value:
            # Do not overwrite if the task already marked the job as FINISHED (e.g. complete_job
            # succeeded then something in cleanup raised, so RQ reports failed but work is done).
            if job.status == JobStatus.FINISHED.value:
                self.db.commit()
                return job
            job.status = JobStatus.FAILED.value
            job.completed_at = now
            job.updated_at = now
            if rq_status.get('exc_info'):
                job.error = str(rq_status['exc_info'])
            self.db.commit()
            _notify_import_job_event(
                self.db,
                job,
                "failed",
                "Import job failed",
                f"Your {job.job_type} import failed.",
            )
            return job

        self.db.commit()
        return job
