"""General background task scheduler (imports, integrations, notifications, summaries)."""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.database import SessionLocal
from app.services.integration_service import IntegrationLogService
from app.services.queue_service import get_queue
from app.services.scheduled_task_service import (
    run_due_tasks,
    register_handler,
)
from app.services.respond_sync_handler import run_respond_contacts_sync
from app.services.user_sla_daily_summary_service import run_user_sla_daily_summary
from app.services.marketing_service import PromotionService
from app.config import settings

logger = logging.getLogger(__name__)


def _handler_integration_log_retry(db, task):
    """Handler for integration_log_retry: process pending integration logs."""
    service = IntegrationLogService(db)
    result = service.process_pending_logs()
    return {
        "processed": result.get("processed", 0),
        "succeeded": result.get("succeeded", 0),
        "failed": result.get("failed", 0),
    }


def _handler_import_job_processor(db, task):
    """Handler for import_job_processor: process RQ import jobs (no db from task)."""
    result = _run_import_jobs_impl()
    return result


def _handler_notification_delivery_processor(db, task):
    """Handler for notification_delivery_processor: process notification email/push deliveries from queue."""
    result = _run_notification_delivery_jobs_impl()
    return result


def _handler_embedding_job_processor(db, task):
    """Handler for embedding_job_processor: process embedding jobs from queue."""
    return _run_queue_jobs_impl(settings.embedding_queue_name, max_jobs_per_run=10)


def _handler_user_sla_daily_summary(db, task):
    """Daily in-app/email summary of SLA performance and outstanding assignments per user."""
    return run_user_sla_daily_summary(db, task)


def _handler_promotion_active_window(db, task):
    """Set promotion is_active from Malaysia today vs inclusive [start_date, end_date]."""
    return PromotionService(db).sync_promotion_active_by_calendar_window()


def _run_notification_delivery_jobs_impl():
    """Process jobs from the notifications queue (email and web_push deliveries). Returns summary dict."""
    from rq.job import Job
    from app.services.queue_service import redis_conn

    queue = get_queue("notifications")
    queue_length = len(queue)
    if queue_length == 0:
        return {"processed": 0, "queued": 0}
    all_job_ids = queue.get_job_ids()
    if not all_job_ids:
        return {"processed": 0, "queued": 0}
    queued_jobs = []
    for job_id in all_job_ids:
        try:
            job = Job.fetch(job_id, connection=redis_conn)
            if job.get_status() == "queued":
                queued_jobs.append(job)
            else:
                try:
                    queue.remove(job)
                except Exception:
                    pass
        except Exception:
            continue
    if not queued_jobs:
        return {"processed": 0, "queued": 0}
    max_jobs_per_run = 20
    processed = 0
    for job in queued_jobs[:max_jobs_per_run]:
        try:
            job.set_status("started")
            job.save()
            result = job.func(*job.args, **job.kwargs)
            job.set_status("finished")
            job.save()
            try:
                queue.remove(job)
            except Exception:
                pass
            processed += 1
        except Exception as e:
            logger.error("Error processing notification job %s: %s", job.id, e, exc_info=True)
            try:
                job.set_status("failed")
                job.meta["exc_info"] = str(e)
                job.save()
                queue.remove(job)
            except Exception:
                pass
    return {"processed": processed, "queued": len(queued_jobs)}


def _run_import_jobs_impl():
    """Logic of process_import_jobs, returns summary dict."""
    from rq.job import Job
    from app.services.queue_service import redis_conn

    queue = get_queue("imports")
    queue_length = len(queue)
    if queue_length == 0:
        return {"processed": 0, "queued": 0}
    all_job_ids = queue.get_job_ids()
    if not all_job_ids:
        return {"processed": 0, "queued": 0}
    queued_jobs = []
    for job_id in all_job_ids:
        try:
            job = Job.fetch(job_id, connection=redis_conn)
            if job.get_status() == "queued":
                queued_jobs.append(job)
            else:
                try:
                    queue.remove(job)
                except Exception:
                    pass
        except Exception:
            continue
    if not queued_jobs:
        return {"processed": 0, "queued": 0}
    max_jobs_per_run = 2
    processed = 0
    for job in queued_jobs[:max_jobs_per_run]:
        try:
            job.set_status("started")
            job.save()
            result = job.func(*job.args, **job.kwargs)
            job.set_status("finished")
            job.save()
            try:
                queue.remove(job)
            except Exception:
                pass
            processed += 1
        except Exception as e:
            logger.error("Error processing import job %s: %s", job.id, e, exc_info=True)
            try:
                job.set_status("failed")
                job.meta["exc_info"] = str(e)
                job.save()
                queue.remove(job)
            except Exception:
                pass
    return {"processed": processed, "queued": len(queued_jobs)}


def _run_queue_jobs_impl(queue_name: str, max_jobs_per_run: int) -> dict:
    """Generic queue processor used by scheduled task heartbeat."""
    from rq.job import Job
    from app.services.queue_service import redis_conn

    queue = get_queue(queue_name)
    all_job_ids = queue.get_job_ids()
    if not all_job_ids:
        return {"processed": 0, "queued": 0}
    queued_jobs = []
    for job_id in all_job_ids:
        try:
            job = Job.fetch(job_id, connection=redis_conn)
            if job.get_status() == "queued":
                queued_jobs.append(job)
            else:
                try:
                    queue.remove(job)
                except Exception:
                    pass
        except Exception:
            continue
    processed = 0
    for job in queued_jobs[:max_jobs_per_run]:
        try:
            job.set_status("started")
            job.save()
            job.func(*job.args, **job.kwargs)
            job.set_status("finished")
            job.save()
            try:
                queue.remove(job)
            except Exception:
                pass
            processed += 1
        except Exception as e:
            logger.error("Error processing %s job %s: %s", queue_name, job.id, e, exc_info=True)
            try:
                job.set_status("failed")
                job.meta["exc_info"] = str(e)
                job.save()
                queue.remove(job)
            except Exception:
                pass
    return {"processed": processed, "queued": len(queued_jobs)}


def process_pending_integration_logs():
    """
    Process pending integration logs that are ready for retry.
    This function is called periodically by the scheduler.
    """
    db = SessionLocal()
    try:
        service = IntegrationLogService(db)
        result = service.process_pending_logs()

        if result["processed"] > 0:
            logger.info(
                f"Processed {result['processed']} integration logs: "
                f"{result['succeeded']} succeeded, {result['failed']} failed"
            )
    except Exception as e:
        logger.error(f"Error processing pending integration logs: {str(e)}", exc_info=True)
    finally:
        db.close()


def process_import_jobs():
    """
    Process RQ import jobs from the queue.
    This function is called periodically by the scheduler to process queued import jobs.
    Manually executes jobs without registering a worker to avoid conflicts.
    """
    try:
        from rq.job import Job
        from app.services.queue_service import redis_conn
        import time

        # Get the imports queue
        queue = get_queue("imports")

        # Check if there are any job IDs in the RQ (Redis) queue.
        # Note: This is the RQ queue, not the import_jobs DB table. Old processed
        # jobs are removed below so this count stays accurate.
        queue_length = len(queue)
        if queue_length == 0:
            logger.debug("RQ queue is empty, no jobs to process")
            return

        logger.debug(f"RQ queue has {queue_length} job ID(s), checking for queued jobs...")

        # Get all job IDs from the queue
        all_job_ids = queue.get_job_ids()
        if not all_job_ids:
            logger.debug("No job IDs found in queue")
            return

        # Filter for queued jobs only; remove stale (finished/failed) job IDs from queue
        queued_jobs = []
        for job_id in all_job_ids:
            try:
                job = Job.fetch(job_id, connection=redis_conn)
                if job.get_status() == "queued":
                    queued_jobs.append(job)
                else:
                    # Already processed or failed; remove from queue so len(queue) is accurate
                    try:
                        queue.remove(job)
                    except Exception:
                        pass
            except Exception as e:
                logger.debug(f"Could not fetch job {job_id}: {str(e)}")
                continue

        if not queued_jobs:
            logger.debug("No queued jobs found (all jobs are already started/finished/failed)")
            return

        logger.info(f"Found {len(queued_jobs)} queued job(s) to process")

        # Process up to 2 jobs per scheduler run
        jobs_processed = 0
        max_jobs_per_run = 2

        for job in queued_jobs[:max_jobs_per_run]:
            try:
                logger.info(f"Processing job {job.id} (status: {job.get_status()})")

                # Mark job as started in RQ
                job.set_status("started")
                job.save()

                # Call the job function directly with its arguments
                # This avoids signal handling issues in background threads
                # The job function handles its own database job status updates
                result = job.func(*job.args, **job.kwargs)

                # Mark job as finished in RQ and remove from queue so queue length stays accurate
                job.set_status("finished")
                job.save()
                try:
                    queue.remove(job)
                except Exception as remove_err:
                    logger.debug(f"Could not remove job {job.id} from queue: {remove_err}")

                jobs_processed += 1
                logger.info(f"Successfully processed import job {job.id} via scheduler")
            except Exception as e:
                logger.error(f"Error processing import job {job.id}: {str(e)}", exc_info=True)
                # Try to mark job as failed and remove from queue
                try:
                    job.set_status("failed")
                    job.meta["exc_info"] = str(e)
                    job.save()
                    queue.remove(job)
                except Exception as save_error:
                    logger.debug(f"Could not update/remove job {job.id}: {save_error}")

        if jobs_processed > 0:
            logger.info(f"Scheduler successfully processed {jobs_processed} import job(s) from queue")
        else:
            logger.debug("No jobs were processed in this run")

    except Exception as e:
        logger.error(f"Error processing import jobs in scheduler: {str(e)}", exc_info=True)


def _scheduled_tasks_heartbeat():
    """Heartbeat: run due DB-configured scheduled tasks and persist run logs."""
    db = SessionLocal()
    try:
        run_due_tasks(db)
    except Exception as e:
        logger.error("Scheduled tasks heartbeat failed: %s", str(e), exc_info=True)
    finally:
        db.close()


def start_scheduler():
    """
    Start the APScheduler background scheduler.
    Uses a single heartbeat to execute due DB-configured tasks; handlers are registered below.
    """
    # Register handlers for task keys (used when tasks are due in DB)
    register_handler("integration_log_retry", _handler_integration_log_retry)
    register_handler("import_job_processor", _handler_import_job_processor)
    register_handler("notification_delivery_processor", _handler_notification_delivery_processor)
    register_handler("embedding_job_processor", _handler_embedding_job_processor)
    register_handler("user_sla_daily_summary", _handler_user_sla_daily_summary)
    register_handler("promotion_active_window", _handler_promotion_active_window)
    register_handler("respond_contacts_sync", run_respond_contacts_sync)

    scheduler = BackgroundScheduler()

    # Single heartbeat every 10s: query due scheduled_tasks, run handlers, persist run logs
    scheduler.add_job(
        _scheduled_tasks_heartbeat,
        trigger=IntervalTrigger(seconds=10),
        id="scheduled_tasks_heartbeat",
        name="Scheduled tasks heartbeat",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started: scheduled tasks heartbeat (every 10s)")
    return scheduler
