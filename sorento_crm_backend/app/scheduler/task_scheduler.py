"""General background task scheduler (imports, integrations, notifications, summaries)."""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.database import SessionLocal
from app.services.integration_service import IntegrationLogService
from app.services.queue_service import get_queue, run_sync_rq_jobs
from app.services.scheduled_task_service import (
    run_due_tasks,
    register_handler,
)
from app.services.respond_sync_handler import run_respond_contacts_sync
from app.services.attachment_storage_audit_service import run_attachment_storage_audit
from app.services.user_sla_daily_summary_service import run_user_sla_daily_summary
from app.services.marketing_service import PromotionService
from app.services.automation_service import AutomationService
from app.config import settings
from datetime import datetime, timedelta

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
    """Drain RQ imports queue (race-safe lpop) + reconcile orphan QUEUED rows."""
    drain = run_sync_rq_jobs("imports", max_jobs=2)
    orphans = _reconcile_orphan_import_jobs(db)
    return {**drain, "orphans_failed": orphans}


def _reconcile_orphan_import_jobs(db) -> int:
    """Flip QUEUED `import_jobs` rows to FAILED when their RQ job is gone.

    Catches rows where the worker exited before `start_job` ran (e.g. early
    exception in task body or temp-file unreachable across containers). Only
    rows older than 3 minutes are inspected so fresh enqueues are not raced.
    """
    from rq.job import Job
    from rq.exceptions import NoSuchJobError
    from app.models.job import ImportJob, JobStatus
    from app.services.job_service import JobService
    from app.services.queue_service import redis_conn

    cutoff = datetime.utcnow() - timedelta(minutes=3)
    rows = (
        db.query(ImportJob)
        .filter(
            ImportJob.status == JobStatus.QUEUED.value,
            ImportJob.created_at < cutoff,
        )
        .limit(50)
        .all()
    )
    if not rows:
        return 0
    job_service = JobService(db)
    failed = 0
    for row in rows:
        rq_job_id = str(row.job_id)
        try:
            rq_job = Job.fetch(rq_job_id, connection=redis_conn)
            status = rq_job.get_status()
        except NoSuchJobError:
            status = None
        except Exception:
            continue
        if status in (None, "failed", "canceled"):
            try:
                job_service.fail_job(
                    rq_job_id,
                    "Import did not start (worker dropped before processing).",
                )
                failed += 1
            except Exception:
                logger.exception("Failed to fail orphan import job %s", rq_job_id)
    return failed


def _handler_notification_delivery_processor(db, task):
    """Handler for notification_delivery_processor: drain notifications queue (race-safe lpop)."""
    return run_sync_rq_jobs("notifications", max_jobs=20)


def _handler_embedding_job_processor(db, task):
    """Process embedding jobs: Redis RQ first; optional Postgres embedding_queue fallback."""
    rq_result = _run_queue_jobs_impl(settings.embedding_queue_name, max_jobs_per_run=10)
    if not getattr(settings, "embedding_queue_db_fallback_enabled", True):
        return {
            "processed": rq_result.get("processed", 0),
            "queued_redis": rq_result.get("queued", 0),
            "processed_redis": rq_result.get("processed", 0),
            "processed_db": 0,
            "db_fallback_enabled": False,
        }
    db_result = _run_embedding_db_queue_fallback(db, max_jobs_per_run=10)
    return {
        "processed": rq_result.get("processed", 0) + db_result.get("processed", 0),
        "queued_redis": rq_result.get("queued", 0),
        "queued_db_pending_before": db_result.get("queued_db_pending_before", 0),
        "processed_redis": rq_result.get("processed", 0),
        "processed_db": db_result.get("processed", 0),
        "db_fallback_enabled": True,
    }


def _run_embedding_db_queue_fallback(db, max_jobs_per_run: int) -> dict:
    """Run worker for pending ``embedding_queue`` rows (available now), no Redis required."""
    from sqlalchemy import case, func
    from app.models.embeddings import EmbeddingQueue
    from app.services.embedding_worker import process_embedding_queue_item

    now_naive = datetime.utcnow()
    pending_before = (
        db.query(func.count(EmbeddingQueue.id))
        .filter(EmbeddingQueue.status == "pending", EmbeddingQueue.available_at <= now_naive)
        .scalar()
        or 0
    )
    ids = (
        db.query(EmbeddingQueue.id)
        .filter(EmbeddingQueue.status == "pending", EmbeddingQueue.available_at <= now_naive)
        .order_by(
            case((EmbeddingQueue.source_type == "mcp_tool", 0), else_=1).asc(),
            EmbeddingQueue.created_at.asc(),
        )
        .limit(max_jobs_per_run)
        .all()
    )
    ids = [str(row[0]) for row in ids]
    processed = 0
    for qid in ids:
        try:
            process_embedding_queue_item(qid)
            processed += 1
        except Exception as e:
            logger.error("Embedding DB fallback failed for queue id %s: %s", qid, e, exc_info=True)
    return {"processed": processed, "queued_db_pending_before": int(pending_before)}


def _handler_user_sla_daily_summary(db, task):
    """Daily in-app/email summary of SLA performance and outstanding assignments per user."""
    return run_user_sla_daily_summary(db, task)


def _handler_promotion_active_window(db, task):
    """Set promotion is_active from Malaysia today vs inclusive [start_date, end_date]."""
    return PromotionService(db).sync_promotion_active_by_calendar_window()


def _handler_automation_runner(db, task):
    """Heartbeat for automations: dispatch every enabled automation whose next_run_at is due."""
    return AutomationService(db).evaluate_due()


def _handler_form_sla_overdue_scan(db, task):
    """Scan unresolved form SLA trackers, escalate any past due_at to next tier."""
    from app.services.form_sla_service import FormSLAOrchestrator

    return FormSLAOrchestrator(db).scan_overdue_and_escalate()


def _handler_email_outbox_drainer(db, task):
    """Drain pending email_outbox rows respecting guardrail caps."""
    from app.tasks.email_outbox_tasks import drain_email_outbox

    return drain_email_outbox()


def _handler_respond_templates_sync(db, task):
    """Sync Respond.io channels + WhatsApp templates for all active workspaces."""
    from app.services.respond_template_service import run_respond_templates_sync

    return run_respond_templates_sync(db, task)


def _drain_email_outbox_tick():
    """APScheduler tick wrapper. Owns its own DB session (drain_email_outbox handles errors)."""
    try:
        from app.tasks.email_outbox_tasks import drain_email_outbox

        summary = drain_email_outbox()
        if summary.get("picked"):
            logger.info("Email outbox drainer tick: %s", summary)
    except Exception as e:
        logger.error("Email outbox drainer tick failed: %s", e, exc_info=True)


def _run_queue_jobs_impl(queue_name: str, max_jobs_per_run: int) -> dict:
    """Generic queue processor used by scheduled task heartbeat."""
    return run_sync_rq_jobs(queue_name, max_jobs_per_run)


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


def _scheduled_tasks_heartbeat():
    """Heartbeat: run due DB-configured scheduled tasks and persist run logs."""
    db = SessionLocal()
    try:
        run_due_tasks(db)
    except Exception as e:
        logger.error("Scheduled tasks heartbeat failed: %s", str(e), exc_info=True)
    finally:
        db.close()


def register_task_handlers():
    """Register all scheduled task handlers. Safe to call multiple times."""
    register_handler("integration_log_retry", _handler_integration_log_retry)
    register_handler("import_job_processor", _handler_import_job_processor)
    register_handler("notification_delivery_processor", _handler_notification_delivery_processor)
    register_handler("embedding_job_processor", _handler_embedding_job_processor)
    register_handler("user_sla_daily_summary", _handler_user_sla_daily_summary)
    register_handler("promotion_active_window", _handler_promotion_active_window)
    register_handler("respond_contacts_sync", run_respond_contacts_sync)
    register_handler("respond_templates_sync", _handler_respond_templates_sync)
    register_handler("automation_runner", _handler_automation_runner)
    register_handler("form_sla_overdue_scan", _handler_form_sla_overdue_scan)
    register_handler("email_outbox_drainer", _handler_email_outbox_drainer)
    register_handler("attachment_storage_audit", run_attachment_storage_audit)


def start_scheduler():
    """
    Start the APScheduler background scheduler.
    Uses a single heartbeat to execute due DB-configured tasks.
    """
    register_task_handlers()

    scheduler = BackgroundScheduler()

    # Single heartbeat every 10s: query due scheduled_tasks, run handlers, persist run logs
    scheduler.add_job(
        _scheduled_tasks_heartbeat,
        trigger=IntervalTrigger(seconds=10),
        id="scheduled_tasks_heartbeat",
        name="Scheduled tasks heartbeat",
        replace_existing=True,
    )

    # Email outbox drainer: read interval from SystemSetting (default 5s) so password-reset
    # and approval-link emails leave the queue near-instantly while attachment-linkage
    # bursts get throttled by the per-recipient cap inside drain_email_outbox.
    drain_seconds = 5
    try:
        db = SessionLocal()
        try:
            from app.models.user import SystemSetting

            settings_row = db.query(SystemSetting).first()
            if settings_row and getattr(settings_row, "email_outbox_drain_interval_seconds", None):
                drain_seconds = int(settings_row.email_outbox_drain_interval_seconds)
        finally:
            db.close()
    except Exception as e:
        logger.warning("Email outbox drainer interval lookup failed (%s); using 5s default.", e)
    scheduler.add_job(
        _drain_email_outbox_tick,
        trigger=IntervalTrigger(seconds=max(1, drain_seconds)),
        id="email_outbox_drainer",
        name="Email outbox drainer",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        "Scheduler started: scheduled tasks heartbeat (every 10s), email outbox drainer (every %ds)",
        max(1, drain_seconds),
    )
    return scheduler
