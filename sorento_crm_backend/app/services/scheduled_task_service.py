"""Service for scheduled task execution and run logging."""
import logging
import threading
from datetime import datetime, timedelta
from typing import Callable, Optional, Any, Dict

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.scheduled_task import ScheduledTask, ScheduledTaskRun

logger = logging.getLogger(__name__)

# Type for task handlers: (db, task) -> summary dict
TaskHandler = Callable[[Session, ScheduledTask], dict[str, Any]]

# Registry of task key -> handler. Populated when handlers are registered.
TASK_HANDLERS: dict[str, TaskHandler] = {}


def _task_schedule_args(task: ScheduledTask) -> tuple[str, int, str, Optional[datetime]]:
    interval_unit = str(getattr(task, "interval_unit"))
    interval_value = int(getattr(task, "interval_value"))
    timezone_value = str(getattr(task, "timezone"))
    start_at_raw = getattr(task, "start_at", None)
    start_at_value = start_at_raw if isinstance(start_at_raw, datetime) else None
    return interval_unit, interval_value, timezone_value, start_at_value


def _task_id(task: ScheduledTask) -> str:
    return str(getattr(task, "id"))


def _task_key(task: ScheduledTask) -> str:
    return str(getattr(task, "key"))


def _run_id(run: ScheduledTaskRun) -> str:
    return str(getattr(run, "id"))


def register_handler(key: str, handler: TaskHandler) -> None:
    """Register a handler for a scheduled task key."""
    TASK_HANDLERS[key] = handler


def _interval_delta(interval_unit: str, interval_value: int) -> timedelta:
    if interval_unit == "seconds":
        return timedelta(seconds=interval_value)
    if interval_unit == "minutes":
        return timedelta(minutes=interval_value)
    if interval_unit == "hours":
        return timedelta(hours=interval_value)
    if interval_unit == "days":
        return timedelta(days=interval_value)
    return timedelta(minutes=15)


def compute_next_run(
    interval_unit: str,
    interval_value: int,
    timezone: str,
    start_at: Optional[datetime],
    from_time: datetime,
) -> datetime:
    """Display-only next-run estimate. Due-check is frequency-based at query time.

    Rules:
    - If `start_at` is in the future, next run = `start_at` (UI shows when task will first fire).
    - Otherwise next run = `from_time + interval` (typically last_run + interval).
    """
    delta = _interval_delta(interval_unit, interval_value)
    if start_at and start_at > from_time:
        return start_at
    return from_time + delta


def _is_task_due(task: ScheduledTask, now: datetime) -> bool:
    """Frequency-driven: task fires if start_at has passed AND
    (never ran OR `now - last_run >= interval`).
    """
    start_at = getattr(task, "start_at", None)
    if isinstance(start_at, datetime) and start_at > now:
        return False
    last_run = getattr(task, "last_run_at", None)
    if not isinstance(last_run, datetime):
        return True
    delta = _interval_delta(
        str(getattr(task, "interval_unit")),
        int(getattr(task, "interval_value")),
    )
    return (now - last_run) >= delta


def get_due_tasks(db: Session) -> list[ScheduledTask]:
    """Return enabled tasks due now per frequency. `next_run_at` is display-only."""
    now = datetime.utcnow()
    enabled = db.query(ScheduledTask).filter(ScheduledTask.enabled.is_(True)).all()
    return [t for t in enabled if _is_task_due(t, now)]


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
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[ScheduledTask]:
    """Update task config. Recomputes next_run_at if interval/start_at changed."""
    task = get_task(db, task_id)
    if not task:
        return None
    if name is not None:
        setattr(task, "name", name)
    if description is not None:
        setattr(task, "description", description)
    if enabled is not None:
        setattr(task, "enabled", enabled)
    if interval_unit is not None:
        setattr(task, "interval_unit", interval_unit)
    if interval_value is not None:
        setattr(task, "interval_value", interval_value)
    if timezone is not None:
        setattr(task, "timezone", timezone)
    if start_at is not None:
        setattr(task, "start_at", start_at)
    if metadata is not None:
        task_metadata = getattr(task, "metadata_", None)
        metadata_map: Dict[str, Any] = (
            dict(task_metadata) if isinstance(task_metadata, dict) else {}
        )
        for k, v in metadata.items():
            if v is None:
                metadata_map.pop(k, None)
            else:
                metadata_map[k] = v
        setattr(task, "metadata_", metadata_map or None)
    # Recompute next_run_at from current schedule
    now = datetime.utcnow()
    last_run_at = getattr(task, "last_run_at", None)
    start_at_value = getattr(task, "start_at", None)
    base_time = (
        last_run_at
        if isinstance(last_run_at, datetime)
        else start_at_value
        if isinstance(start_at_value, datetime)
        else now
    )
    interval_unit_value, interval_value_value, timezone_value, task_start_at = _task_schedule_args(task)
    setattr(task, "next_run_at", compute_next_run(
        interval_unit_value,
        interval_value_value,
        timezone_value,
        task_start_at,
        base_time,
    ))
    setattr(task, "updated_at", now)
    db.commit()
    db.refresh(task)
    return task


def _execute_task_run(
    task_id: str,
    run_id: str,
    task_key: str,
    requested_by_user_id: Optional[str],
) -> None:
    """Run handler in a fresh DB session. Intended to run inside a background thread."""
    bg_db: Session = SessionLocal()
    start = datetime.utcnow()
    try:
        task = bg_db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
        if not task:
            logger.warning("run_task_now background: task %s vanished", task_id)
            return
        handler = TASK_HANDLERS.get(task_key)
        if not handler:
            finish_run(
                bg_db,
                run_id,
                status="skipped",
                duration_ms=int((datetime.utcnow() - start).total_seconds() * 1000),
                summary={"reason": "no handler registered"},
            )
            next_run = compute_next_run(*_task_schedule_args(task), datetime.utcnow())
            update_task_after_run(
                bg_db, _task_id(task), "skipped", None,
                {"reason": "no handler registered"}, next_run,
            )
            return
        if requested_by_user_id:
            setattr(task, "_manual_run_requested_by_user_id", str(requested_by_user_id))
        try:
            summary = handler(bg_db, task)
            duration_ms = int((datetime.utcnow() - start).total_seconds() * 1000)
            finish_run(bg_db, run_id, status="success", duration_ms=duration_ms, summary=summary or {})
            next_run = compute_next_run(*_task_schedule_args(task), datetime.utcnow())
            update_task_after_run(bg_db, _task_id(task), "success", None, summary, next_run)
        except Exception as e:
            logger.exception("Scheduled task %s failed in background", task_key)
            duration_ms = int((datetime.utcnow() - start).total_seconds() * 1000)
            err_msg = str(e)
            try:
                bg_db.rollback()
            except Exception:
                pass
            finish_run(bg_db, run_id, status="failed", duration_ms=duration_ms, error=err_msg)
            next_run = compute_next_run(*_task_schedule_args(task), datetime.utcnow())
            update_task_after_run(bg_db, _task_id(task), "failed", err_msg, None, next_run)
    finally:
        try:
            bg_db.close()
        except Exception:
            pass


def run_task_now(db: Session, task_id: str, requested_by_user_id: Optional[str] = None) -> Optional[dict]:
    """
    Trigger a manual run asynchronously. Creates the run record synchronously
    (so the caller gets a run_id), then dispatches the handler in a background
    thread. Returns immediately with status="started"; clients should poll
    /scheduled-tasks/{task_id}/runs for completion.
    """
    task = get_task(db, task_id)
    if not task:
        return None

    run = create_run(db, _task_id(task), status="started")
    run_id = _run_id(run)
    task_key = _task_key(task)
    task_id_str = _task_id(task)

    thread = threading.Thread(
        target=_execute_task_run,
        args=(task_id_str, run_id, task_key, requested_by_user_id),
        name=f"scheduled-task-run-{task_key}-{run_id[:8]}",
        daemon=True,
    )
    thread.start()

    return {
        "run_id": run_id,
        "status": "started",
        "async": True,
        "message": "Task run started in background. Poll the runs endpoint for status.",
    }


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
    setattr(run, "finished_at", datetime.utcnow())
    setattr(run, "status", status)
    setattr(run, "duration_ms", duration_ms)
    setattr(run, "summary", summary)
    setattr(run, "error", error)
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
    setattr(task, "last_run_at", datetime.utcnow())
    setattr(task, "last_status", last_status)
    setattr(task, "last_error", last_error)
    setattr(task, "next_run_at", next_run_at)
    setattr(task, "updated_at", datetime.utcnow())
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
            run = create_run(db, _task_id(task), status="started")
            handler = TASK_HANDLERS.get(_task_key(task))
            if not handler:
                finish_run(
                    db,
                    _run_id(run),
                    status="skipped",
                    duration_ms=int((datetime.utcnow() - start).total_seconds() * 1000),
                    summary={"reason": "no handler registered"},
                )
                update_task_after_run(
                    db,
                    _task_id(task),
                    last_status="skipped",
                    last_error=None,
                    summary={"reason": "no handler registered"},
                    next_run_at=compute_next_run(
                        *_task_schedule_args(task),
                        start,
                    ),
                )
                logger.warning("Scheduled task %s has no registered handler", _task_key(task))
                continue
            summary = handler(db, task)
            duration_ms = int((datetime.utcnow() - start).total_seconds() * 1000)
            finish_run(db, _run_id(run), status="success", duration_ms=duration_ms, summary=summary or {})
            next_run = compute_next_run(
                *_task_schedule_args(task),
                datetime.utcnow(),
            )
            update_task_after_run(
                db, _task_id(task), last_status="success", last_error=None, summary=summary, next_run_at=next_run
            )
            logger.info("Scheduled task %s completed: %s", _task_key(task), summary)
        except Exception as e:
            duration_ms = int((datetime.utcnow() - start).total_seconds() * 1000)
            err_msg = str(e)
            if run:
                finish_run(
                    db,
                    _run_id(run),
                    status="failed",
                    duration_ms=duration_ms,
                    error=err_msg,
                )
            next_run = compute_next_run(
                *_task_schedule_args(task),
                datetime.utcnow(),
            )
            update_task_after_run(
                db, _task_id(task), last_status="failed", last_error=err_msg, summary=None, next_run_at=next_run
            )
            logger.exception("Scheduled task %s failed: %s", _task_key(task), err_msg)
