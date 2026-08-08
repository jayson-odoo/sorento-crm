"""General background task scheduler (imports, integrations, notifications, summaries)."""
import logging
from contextlib import contextmanager
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.database import SessionLocal
from app.models.base import set_company_scope
from app.services.integration_service import IntegrationLogService
from app.services.queue_service import get_queue, run_sync_rq_jobs
from app.services.scheduled_task_service import (
    run_due_tasks,
    register_handler,
)
from app.services.respond_sync_handler import run_respond_contacts_sync
from app.services.attachment_storage_audit_service import run_attachment_storage_audit
from app.services.n8n_liveness_service import run_n8n_liveness_ping
from app.services.system_health_alert_service import run_health_watchdog, run_health_daily_digest
from app.services.user_sla_daily_summary_service import run_user_sla_daily_summary
from app.services.marketing_service import PromotionService
from app.services.automation_service import AutomationService
from app.config import settings
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@contextmanager
def scheduler_session():
    """A DB session for background ticks, explicitly scoped to ALL companies.

    Sessions default to ``UNSET``, which the company-scope filter treats as zero
    rows (fail closed). That is right for an unauthenticated request and wrong for
    a scheduler tick: it has no principal, yet must see every company's work. Left
    at the default, an overdue-SLA scan reads zero rows from every company-scoped
    table, escalates nothing, and raises nothing - the failure is completely silent.

    Background work opts out of the filter, exactly as ``import_tasks`` and
    ``export_tasks`` already do. Per-row company still governs what each tick then
    does with what it read (an SLA tracker escalates up its own company's ladder).
    """
    db = SessionLocal()
    set_company_scope(db, None)
    try:
        yield db
    finally:
        db.close()


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


def _handler_coverage_subscription_expiry(db, task):
    """Deactivate coverage subscriptions whose expires_at has passed."""
    from app.services.coverage_subscription_service import CoverageSubscriptionService

    count = CoverageSubscriptionService(db).deactivate_expired_subscriptions()
    return {"deactivated": count}


def _handler_takeover_request_commit(db, task):
    """Commit pending SLA takeover requests whose cooldown has elapsed unchallenged
    (re-validating first); void those whose premise changed. See PLAN-takeover-cooldown."""
    from app.services.sla_takeover_service import SlaTakeoverService

    return SlaTakeoverService(db).commit_due()


def _handler_chat_message_resolver(db, task):
    """Fill `respond_ts` / delivery status on chat rows from Respond itself.

    n8n's `sent_at` is its own wall clock, so the round-trip SLA cannot be measured from
    it. This resolves the authoritative Respond-side timestamp per message id, in
    batches, so both ends of the measurement share one clock."""
    from app.services.chat_message_resolver import resolve_pending

    limit = int((task.metadata_ or {}).get("batch_limit", 200)) if task is not None else 200
    return resolve_pending(db, limit=limit)


def _handler_chat_latency_watchdog(db, task):
    """Evaluate the WhatsApp round-trip p99 and the per-turn hard ceiling."""
    from app.services.system_health_alert_service import run_chat_latency_watchdog

    return run_chat_latency_watchdog(db)


def _handler_user_downloads_purge(db, task):
    """Delete My Downloads rows and their stored objects past the retention window.

    Nothing purged this table before; chat-history CSV exports make it matter."""
    from app.models.user import SystemSetting
    from app.services.download_service import purge_expired_downloads

    settings = db.query(SystemSetting).first()
    days = int(getattr(settings, "downloads_retention_days", 30) or 30) if settings else 30
    return purge_expired_downloads(db, retention_days=days)


def _handler_api_call_log_prune(db, task):
    """Two-stage retention: NULL payloads at 30d, DELETE rows at 180d.

    Split because payloads are the bulk of the bytes and the shortest-lived
    value, while the metadata row stays useful for trend analysis."""
    from app.models.user import SystemSetting
    from app.services.api_call_log_service import prune_api_call_log

    settings = db.query(SystemSetting).first()
    payload_days = int(getattr(settings, "api_call_log_payload_retention_days", 30) or 30) if settings else 30
    row_days = int(getattr(settings, "api_call_log_row_retention_days", 180) or 180) if settings else 180
    return prune_api_call_log(
        db, payload_retention_days=payload_days, row_retention_days=row_days
    )


def _handler_import_job_rows_prune(db, task):
    """Retention for per-row import outcome detail.

    Only the drill-down rows age out; the job's counts and aggregated breakdown
    live on import_jobs.result and survive forever, so an old job still says what
    it did - you just can no longer page through its individual rows.
    """
    from app.models.user import SystemSetting
    from app.services.import_outcome import prune_import_job_rows

    settings = db.query(SystemSetting).first()
    days = int(getattr(settings, "import_job_rows_retention_days", 90) or 90) if settings else 90
    return prune_import_job_rows(db, retention_days=days)


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


def _handler_product_discontinued_check(db, task):
    """Report newly-discontinued products (batched) to subscribed staff."""
    from app.services.product_discontinued_notify_service import (
        run_product_discontinued_check,
    )

    return run_product_discontinued_check(db, task)


def _handler_scm_analytics(db, task):
    """Nightly SCM analytics full recompute (demand + ABC/XYZ + supplier performance).

    Runs ``run_analytics`` on the scheduler/worker process. ``run_analytics`` opens its
    own ``scm.scm_analytics_run`` log row up-front and, on any failure, stamps that row
    ``status='failed'`` + ``error_text`` before re-raising — so a bad run is always
    observable in the run log. We re-raise here so the scheduled-task run is marked
    failed too; the heartbeat's outer guard (``run_due_tasks``) keeps the scheduler
    process alive, so a failed analytics run never crashes the scheduler.

    Optional ``scheduled_tasks.metadata`` keys tune the run with no code change:
      * ``scope``  — dict forwarded to run_analytics (product_ids / supplier_ids / ...).
      * ``config`` — dict forwarded to run_analytics (e.g. ``as_of``).
    Absent metadata => full-catalog run as of today (the nightly default).
    """
    from app.services.scm.analytics_service import run_analytics

    metadata = getattr(task, "metadata_", None)
    scope = metadata.get("scope") if isinstance(metadata, dict) else None
    config = metadata.get("config") if isinstance(metadata, dict) else None
    try:
        return run_analytics(db, scope=scope, config=config)
    except Exception:
        # run_analytics already recorded status='failed' + error_text on its run-log
        # row; re-raise so the scheduled-task run is failed too. The heartbeat catches
        # this so the scheduler keeps ticking.
        logger.exception("Scheduled SCM analytics run failed")
        raise


def _handler_scm_reorder_run(db, task):
    """Daily scheduled reorder planning run (M8-D1/D6/D8).

    Plans ALL active warehouses with market insight OFF, then funds EVERYTHING (full
    budget) so the morning snapshot opens fully within-budget — the user tightens the
    budget on the page to defer (M8-D6). Runs the pipeline INLINE on the scheduler/
    worker process (like ``_handler_scm_analytics`` runs ``run_analytics`` inline) so the
    run + the full-budget funding split are both complete + persisted when the handler
    returns; no dependence on a live RQ worker draining the run afterwards.

    Optional ``scheduled_tasks.metadata`` keys tune the run with no code change (the
    "configurable time" is the row's ``start_at``/interval; these tune the run body):
      * ``budget``          — a numeric cash cap for the scheduled split; null/absent =>
        full budget (fund everything, the default).
      * ``include_market``  — market-trend priority factor (default false; market never
        enters a run per M8-D5, so leave false).
    """
    from app.services.scm import reorder_run_service as reorder_svc

    metadata = getattr(task, "metadata_", None)
    md = metadata if isinstance(metadata, dict) else {}
    budget = md.get("budget")
    include_market = bool(md.get("include_market", False))

    created = reorder_svc.create_run(
        db,
        warehouse_codes=[],            # all active warehouses (M8-D1)
        buy_scope="warehouse",         # per-warehouse planning: each buy ties to a real WH
        include_market=include_market,  # market OFF for the scheduled run (M8-D1)
        enqueue=False,                  # run inline on this process
    )
    run_id = created["run_id"]
    reorder_svc.run_reorder(run_id, db=db)

    if isinstance(budget, (int, float)) and not isinstance(budget, bool):
        funding = reorder_svc.apply_run_budget(db, run_id, float(budget))
    else:
        # Full budget (M8-D6): fund every costed buy regardless of a numeric cap.
        funding = reorder_svc.apply_run_budget(db, run_id, None, full=True)
    return {"run_id": run_id, "include_market": include_market, **funding}


def _drain_email_outbox_tick():
    """APScheduler tick wrapper. Owns its own DB session (drain_email_outbox handles errors)."""
    try:
        from app.tasks.email_outbox_tasks import drain_email_outbox

        summary = drain_email_outbox()
        if summary.get("picked"):
            logger.info("Email outbox drainer tick: %s", summary)
    except Exception as e:
        logger.error("Email outbox drainer tick failed: %s", e, exc_info=True)


def _ai_trace_sweep_tick():
    """APScheduler tick: delete expired AI assistant traces (M2 retention).
    Owns its own DB session; sweep is best-effort and never raises."""
    try:
        from app.services.ai_trace import sweep_expired_traces

        with scheduler_session() as db:
            sweep_expired_traces(db)
    except Exception as e:
        logger.error("AI trace sweep tick failed: %s", e, exc_info=True)


def _run_queue_jobs_impl(queue_name: str, max_jobs_per_run: int) -> dict:
    """Generic queue processor used by scheduled task heartbeat."""
    return run_sync_rq_jobs(queue_name, max_jobs_per_run)


def process_pending_integration_logs():
    """
    Process pending integration logs that are ready for retry.
    This function is called periodically by the scheduler.
    """
    try:
        with scheduler_session() as db:
            service = IntegrationLogService(db)
            result = service.process_pending_logs()

            if result["processed"] > 0:
                logger.info(
                    f"Processed {result['processed']} integration logs: "
                    f"{result['succeeded']} succeeded, {result['failed']} failed"
                )
    except Exception as e:
        logger.error(f"Error processing pending integration logs: {str(e)}", exc_info=True)


def _scheduled_tasks_heartbeat():
    """Heartbeat: run due DB-configured scheduled tasks and persist run logs."""
    try:
        with scheduler_session() as db:
            run_due_tasks(db)
    except Exception as e:
        logger.error("Scheduled tasks heartbeat failed: %s", str(e), exc_info=True)


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
    register_handler("product_discontinued_check", _handler_product_discontinued_check)
    register_handler("coverage_subscription_expiry", _handler_coverage_subscription_expiry)
    register_handler("takeover_request_commit", _handler_takeover_request_commit)
    register_handler("n8n_liveness_ping", lambda db, task: run_n8n_liveness_ping(db))
    register_handler("system_health_watchdog", lambda db, task: run_health_watchdog(db))
    register_handler("system_health_daily_digest", lambda db, task: run_health_daily_digest(db, task))
    register_handler("chat_message_resolver", _handler_chat_message_resolver)
    register_handler("user_downloads_purge", _handler_user_downloads_purge)
    register_handler("api_call_log_prune", _handler_api_call_log_prune)
    register_handler("import_job_rows_prune", _handler_import_job_rows_prune)
    register_handler("chat_latency_watchdog", _handler_chat_latency_watchdog)
    register_handler("scm_analytics", _handler_scm_analytics)
    register_handler("scm_reorder_run", _handler_scm_reorder_run)


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
        with scheduler_session() as db:
            from app.models.user import SystemSetting

            settings_row = db.query(SystemSetting).first()
            if settings_row and getattr(settings_row, "email_outbox_drain_interval_seconds", None):
                drain_seconds = int(settings_row.email_outbox_drain_interval_seconds)
    except Exception as e:
        logger.warning("Email outbox drainer interval lookup failed (%s); using 5s default.", e)
    scheduler.add_job(
        _drain_email_outbox_tick,
        trigger=IntervalTrigger(seconds=max(1, drain_seconds)),
        id="email_outbox_drainer",
        name="Email outbox drainer",
        replace_existing=True,
    )

    # AI assistant trace retention sweep (M2): daily. Deletes ok traces past
    # ai_trace_ttl_days and error/flagged past ai_trace_error_ttl_days.
    scheduler.add_job(
        _ai_trace_sweep_tick,
        trigger=IntervalTrigger(hours=24),
        id="ai_trace_sweep",
        name="AI assistant trace retention sweep",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        "Scheduler started: scheduled tasks heartbeat (every 10s), email outbox drainer "
        "(every %ds), AI trace sweep (daily)",
        max(1, drain_seconds),
    )
    return scheduler
