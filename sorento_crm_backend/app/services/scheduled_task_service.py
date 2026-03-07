"""Service for scheduled task execution and run logging."""
import logging
from datetime import datetime, timedelta
from typing import Callable, Optional, Any

from sqlalchemy.orm import Session

from app.models.scheduled_task import ScheduledTask, ScheduledTaskRun

logger = logging.getLogger(__name__)

# Type for task handlers: (db, task) -> summary dict
TaskHandler = Callable[[Session, ScheduledTask], dict[str, Any]]

# Registry of task key -> handler. Populated when handlers are registered.
TASK_HANDLERS: dict[str, TaskHandler] = {}


def register_handler(key: str, handler: TaskHandler) -> None:
    """Register a handler for a scheduled task key."""
    TASK_HANDLERS[key] = handler


def compute_next_run(
    interval_unit: str,
    interval_value: int,
    timezone: str,
    start_at: Optional[datetime],
    from_time: datetime,
) -> datetime:
    """
    Compute next run time from interval and start/from time.
    Uses UTC; timezone param is reserved for future use.
    """
    if interval_unit == "minutes":
        delta = timedelta(minutes=interval_value)
    elif interval_unit == "hours":
        delta = timedelta(hours=interval_value)
    elif interval_unit == "days":
        delta = timedelta(days=interval_value)
    else:
        delta = timedelta(minutes=15)
    # If start_at is in the future, next run is start_at
    if start_at and start_at > from_time:
        return start_at
    return from_time + delta


def get_due_tasks(db: Session) -> list[ScheduledTask]:
    """Return enabled tasks where next_run_at <= now (UTC)."""
    now = datetime.utcnow()
    return (
        db.query(ScheduledTask)
        .filter(
            ScheduledTask.enabled.is_(True),
            ScheduledTask.next_run_at.isnot(None),
            ScheduledTask.next_run_at <= now,
        )
        .all()
    )


def get_task(db: Session, task_id: str) -> Optional[ScheduledTask]:
    """Get a scheduled task by id."""
    return db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()


def list_tasks(db: Session) -> list[ScheduledTask]:
    """List all scheduled tasks (for API)."""
    return db.query(ScheduledTask).order_by(ScheduledTask.key).all()


def list_runs(
    db: Session,
    task_id: str,
    page: int = 1,
    limit: int = 50,
) -> tuple[list[ScheduledTaskRun], int]:
    """List run logs for a task with pagination. Returns (runs, total_count)."""
    q = db.query(ScheduledTaskRun).filter(ScheduledTaskRun.task_id == task_id)
    total = q.count()
    runs = q.order_by(ScheduledTaskRun.started_at.desc()).offset((page - 1) * limit).limit(limit).all()
    return runs, total


def update_task(
    db: Session,
    task_id: str,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    enabled: Optional[bool] = None,
    interval_unit: Optional[str] = None,
    interval_value: Optional[int] = None,
    timezone: Optional[str] = None,
    start_at: Optional[datetime] = None,
) -> Optional[ScheduledTask]:
    """Update task config. Recomputes next_run_at if interval/start_at changed."""
    task = get_task(db, task_id)
    if not task:
        return None
    if name is not None:
        task.name = name
    if description is not None:
        task.description = description
    if enabled is not None:
        task.enabled = enabled
    if interval_unit is not None:
        task.interval_unit = interval_unit
    if interval_value is not None:
        task.interval_value = interval_value
    if timezone is not None:
        task.timezone = timezone
    if start_at is not None:
        task.start_at = start_at
    # Recompute next_run_at from current schedule
    now = datetime.utcnow()
    base = task.last_run_at or task.start_at or now
    task.next_run_at = compute_next_run(
        task.interval_unit,
        task.interval_value,
        task.timezone,
        task.start_at,
        base,
    )
    task.updated_at = now
    db.commit()
    db.refresh(task)
    return task


def run_task_now(db: Session, task_id: str) -> Optional[dict]:
    """
    Run a task once immediately (manual trigger). Returns run summary or None if task not found.
    """
    task = get_task(db, task_id)
    if not task:
        return None
    run = None
    start = datetime.utcnow()
    try:
        run = create_run(db, task.id, status="started")
        handler = TASK_HANDLERS.get(task.key)
        if not handler:
            finish_run(
                db,
                run.id,
                status="skipped",
                duration_ms=int((datetime.utcnow() - start).total_seconds() * 1000),
                summary={"reason": "no handler registered"},
            )
            next_run = compute_next_run(
                task.interval_unit,
                task.interval_value,
                task.timezone,
                task.start_at,
                datetime.utcnow(),
            )
            update_task_after_run(
                db, task.id, "skipped", None, {"reason": "no handler registered"}, next_run
            )
            return {"run_id": run.id, "status": "skipped", "summary": {"reason": "no handler registered"}}
        summary = handler(db, task)
        duration_ms = int((datetime.utcnow() - start).total_seconds() * 1000)
        finish_run(db, run.id, status="success", duration_ms=duration_ms, summary=summary or {})
        next_run = compute_next_run(
            task.interval_unit,
            task.interval_value,
            task.timezone,
            task.start_at,
            datetime.utcnow(),
        )
        update_task_after_run(db, task.id, "success", None, summary, next_run)
        return {"run_id": run.id, "status": "success", "summary": summary or {}}
    except Exception as e:
        duration_ms = int((datetime.utcnow() - start).total_seconds() * 1000)
        err_msg = str(e)
        if run:
            finish_run(db, run.id, status="failed", duration_ms=duration_ms, error=err_msg)
        next_run = compute_next_run(
            task.interval_unit,
            task.interval_value,
            task.timezone,
            task.start_at,
            datetime.utcnow(),
        )
        update_task_after_run(db, task.id, "failed", err_msg, None, next_run)
        return {"run_id": run.id if run else None, "status": "failed", "error": err_msg}


def create_run(db: Session, task_id: str, status: str = "started") -> ScheduledTaskRun:
    """Create a run record and commit."""
    run = ScheduledTaskRun(task_id=task_id, status=status)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def finish_run(
    db: Session,
    run_id: str,
    status: str,
    duration_ms: Optional[int] = None,
    summary: Optional[dict] = None,
    error: Optional[str] = None,
) -> None:
    """Update run with finished_at, status, duration_ms, summary, error."""
    run = db.query(ScheduledTaskRun).filter(ScheduledTaskRun.id == run_id).first()
    if not run:
        return
    run.finished_at = datetime.utcnow()
    run.status = status
    run.duration_ms = duration_ms
    run.summary = summary
    run.error = error
    db.commit()


def update_task_after_run(
    db: Session,
    task_id: str,
    last_status: str,
    last_error: Optional[str],
    summary: Optional[dict],
    next_run_at: datetime,
) -> None:
    """Update task last_run_at, last_status, last_error, next_run_at."""
    task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
    if not task:
        return
    task.last_run_at = datetime.utcnow()
    task.last_status = last_status
    task.last_error = last_error
    task.next_run_at = next_run_at
    task.updated_at = datetime.utcnow()
    db.commit()


def run_due_tasks(db: Session) -> None:
    """
    Find due tasks, run their handlers, persist run logs and update next_run_at.
    Handlers are looked up by task.key; unknown keys are skipped (run marked skipped).
    """
    due = get_due_tasks(db)
    if not due:
        return
    for task in due:
        run = None
        start = datetime.utcnow()
        try:
            run = create_run(db, task.id, status="started")
            handler = TASK_HANDLERS.get(task.key)
            if not handler:
                finish_run(
                    db,
                    run.id,
                    status="skipped",
                    duration_ms=int((datetime.utcnow() - start).total_seconds() * 1000),
                    summary={"reason": "no handler registered"},
                )
                update_task_after_run(
                    db,
                    task.id,
                    last_status="skipped",
                    last_error=None,
                    summary={"reason": "no handler registered"},
                    next_run_at=compute_next_run(
                        task.interval_unit,
                        task.interval_value,
                        task.timezone,
                        task.start_at,
                        start,
                    ),
                )
                logger.warning("Scheduled task %s has no registered handler", task.key)
                continue
            summary = handler(db, task)
            duration_ms = int((datetime.utcnow() - start).total_seconds() * 1000)
            finish_run(db, run.id, status="success", duration_ms=duration_ms, summary=summary or {})
            next_run = compute_next_run(
                task.interval_unit,
                task.interval_value,
                task.timezone,
                task.start_at,
                datetime.utcnow(),
            )
            update_task_after_run(
                db, task.id, last_status="success", last_error=None, summary=summary, next_run_at=next_run
            )
            logger.info("Scheduled task %s completed: %s", task.key, summary)
        except Exception as e:
            duration_ms = int((datetime.utcnow() - start).total_seconds() * 1000)
            err_msg = str(e)
            if run:
                finish_run(
                    db,
                    run.id,
                    status="failed",
                    duration_ms=duration_ms,
                    error=err_msg,
                )
            next_run = compute_next_run(
                task.interval_unit,
                task.interval_value,
                task.timezone,
                task.start_at,
                datetime.utcnow(),
            )
            update_task_after_run(
                db, task.id, last_status="failed", last_error=err_msg, summary=None, next_run_at=next_run
            )
            logger.exception("Scheduled task %s failed: %s", task.key, err_msg)
