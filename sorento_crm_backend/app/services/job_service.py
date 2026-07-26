"""Service for managing import jobs."""
import logging
import threading
import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.job import ImportJob, JobStatus
from app.services.company_scope import admin_listing_company_filter
from app.services.queue_service import enqueue_job, get_job_status, cancel_job as cancel_rq_job

logger = logging.getLogger(__name__)

_IMPORT_NOTIFICATION_DISCLAIMER = (
    "\n\nThis is a system-generated message. Please do not reply."
)


def active_company_id_from_scope(db: Session) -> Optional[str]:
    """Snapshot the request's active company from the session scope for an import.

    Reads the four-state company scope stamped on the request session by the
    resolver. Only a single-company scope yields a concrete company to persist
    onto the ImportJob (the worker later re-establishes exactly that company so
    its owned writes auto-stamp + isolate). None (all-companies / system) and
    UNSET / empty / multi-company all snapshot NULL (the worker then runs
    system-scoped, ``set_company_scope(None)``) — logged for traceability.
    """
    try:
        from app.models.base import get_company_scope

        scope = get_company_scope(db)
    except Exception:  # never block an import on scope resolution
        return None
    if isinstance(scope, frozenset) and len(scope) == 1:
        return str(next(iter(scope)))
    logger.debug(
        "Import enqueue: no single-company scope (%r); snapshotting NULL company_id", scope
    )
    return None


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
        metadata: Optional[dict] = None,
        company_id: Optional[str] = None,
    ) -> ImportJob:
        """Create a new import job record.

        ``company_id`` snapshots the request's active company so the worker can
        re-establish scope for owned writes (multi-company isolation). When not
        passed explicitly it is derived from the request session's company scope
        (``active_company_id_from_scope``) — so the snapshot is captured even for
        callers that don't thread it through.
        """
        if company_id is None:
            company_id = active_company_id_from_scope(self.db)
        job = ImportJob(
            job_id=str(uuid.uuid4()),  # Temporary, will be updated with RQ job ID
            job_type=job_type,
            status=JobStatus.PENDING.value,  # Use enum value explicitly
            user_id=user_id,
            filename=filename,
            company_id=company_id,
            job_metadata=metadata or {}
        )
        self.db.add(job)
        self.db.flush()  # Get the ID
        return job
    
    def update_job_with_rq_id(self, job: ImportJob, rq_job_id: str) -> ImportJob:
        """Link the RQ job id to the DB row.

        The dedicated worker container runs a blocking RQ Worker on the imports
        queue and picks the job up the moment it is enqueued, so the worker can
        already be running — or even finished — by the time this commits. Two
        guards:
        - Callers should pass job_id=str(job.job_id) to enqueue_job so the RQ
          id equals the DB job_id from creation; rewriting it here is then a
          no-op. (Historically the temp uuid was swapped for the RQ id, which
          made the worker's complete_job/update_job_progress — keyed on the
          job_id it resolved at start — silently miss the row.)
        - Only promote PENDING → QUEUED; never clobber a status the worker
          already advanced (started/finished/failed).
        """
        self.db.refresh(job)
        job.job_id = rq_job_id
        if job.status == JobStatus.PENDING.value:
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
                    "Import completed",
                    (
                        f"Your {job.job_type} import has completed. Processed: {processed_rows}/{job.total_rows} rows "
                        f"({successful_rows} successful, {failed_rows} failed, {skipped_rows} skipped). View job for details."
                        + _IMPORT_NOTIFICATION_DISCLAIMER
                    ),
                )
            except Exception:
                pass  # Do not let notification failure mark the job as failed
        return job

    def fail_job(self, job_id: str, error: str) -> Optional[ImportJob]:
        """Mark job as failed.

        Roll back first: the caller usually lands here because a prior flush
        aborted the transaction, which would otherwise make the query below
        raise PendingRollbackError and mask the real error.
        """
        try:
            self.db.rollback()
        except Exception:
            pass
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
                "Import failed",
                (
                    f"Your {job.job_type} import has failed. {error[:500]} View job for details."
                    + _IMPORT_NOTIFICATION_DISCLAIMER
                ),
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

        # Multi-company: staff import-jobs listing shows only the active company's
        # jobs (+ legacy-null). ImportJob is not an owned mixin (worker infra), so
        # filter by hand. See admin_listing_company_filter for the four-state rules.
        scope_filter = admin_listing_company_filter(self.db, ImportJob.company_id)
        if scope_filter is not None:
            query = query.filter(scope_filter)

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
            "Import cancelled",
            f"Your {job.job_type} import was cancelled. View job for details." + _IMPORT_NOTIFICATION_DISCLAIMER,
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
            _notify_import_job_event(
                self.db, job, "cancelled", "Import cancelled",
                f"Your {job.job_type} import was cancelled. View job for details." + _IMPORT_NOTIFICATION_DISCLAIMER,
            )
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
                "Import completed",
                (
                    f"Your {job.job_type} import has completed. Processed: {job.processed_rows}/{job.total_rows} rows. View job for details."
                    + _IMPORT_NOTIFICATION_DISCLAIMER
                ),
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
                "Import failed",
                f"Your {job.job_type} import has failed. View job for details." + _IMPORT_NOTIFICATION_DISCLAIMER,
            )
            return job

        self.db.commit()
        return job
