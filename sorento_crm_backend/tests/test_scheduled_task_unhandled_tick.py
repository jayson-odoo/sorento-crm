"""A scheduler that cannot run a task must not consume the task's tick.

`_is_task_due` measures from `last_run_at`. The old no-handler branch called
`update_task_after_run`, which stamps `last_run_at = now()`. So a process WITHOUT the
handler suppressed the task for a whole interval, and any process that DID have the
handler never saw it as due.

That only bites when more than one scheduler shares a database, which is exactly what
happens locally (a worker per git worktree, each on a different branch) and briefly
during a rolling deploy (the old image still running while the migration that seeds a
new task key has already landed).

Measured on the dev database before the fix: `form_action_commit` had 441 skipped runs
against 504 successes - 47% of ticks eaten by two workers on branches predating the
handler. The visible symptom was a 15s grace-window sweep taking 45s+, which reads as
"the WhatsApp message was never sent".

Everything runs inside `blank_session()` - a scratch schema whose writes are discarded -
so the shared dev database is never touched.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from app.models.scheduled_task import ScheduledTask
from app.services.scheduled_task_service import (
    TASK_HANDLERS,
    register_handler,
    run_due_tasks,
)

from ._pg_fixture import blank_session, unique_code


def _due_task(db, key: str) -> ScheduledTask:
    """A task last run long enough ago to be due on a 15s interval."""
    task = ScheduledTask(
        key=key,
        name="Unhandled tick probe",
        description="seeded by test_scheduled_task_unhandled_tick",
        enabled=True,
        interval_unit="seconds",
        interval_value=15,
        timezone="UTC",
        last_run_at=datetime.utcnow() - timedelta(minutes=5),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def test_unhandled_task_stays_due_for_a_process_that_can_run_it():
    with blank_session() as db:
        key = f"probe_unhandled_{unique_code()}"
        task = _due_task(db, key)
        before = task.last_run_at

        # This process has no handler for the key - as a worker on an older branch does
        # not have `form_action_commit`.
        TASK_HANDLERS.pop(key, None)
        run_due_tasks(db)

        db.refresh(task)
        # The tick was NOT consumed: still due, so the instance that owns the handler
        # picks it up on its own next sweep.
        assert task.last_run_at == before
        # ...but the operator can still see that something is unhandled.
        assert task.last_status == "skipped"
        assert "no handler" in (task.last_error or "")


def test_unhandled_task_writes_no_run_row():
    """At a 15s interval a run row per tick is ~5.7k rows/day for work nobody did."""
    from app.models.scheduled_task import ScheduledTaskRun

    with blank_session() as db:
        key = f"probe_unhandled_{unique_code()}"
        task = _due_task(db, key)
        TASK_HANDLERS.pop(key, None)

        run_due_tasks(db)

        runs = (
            db.query(ScheduledTaskRun)
            .filter(ScheduledTaskRun.task_id == task.id)
            .count()
        )
        assert runs == 0


def test_a_handled_task_still_consumes_its_tick():
    """The fix must not stop a real handler from advancing the schedule."""
    with blank_session() as db:
        key = f"probe_handled_{unique_code()}"
        task = _due_task(db, key)
        before = task.last_run_at

        calls: list[str] = []

        def _handler(db_, task_):
            calls.append(str(task_.key))
            return {"ok": True}

        register_handler(key, _handler)
        try:
            run_due_tasks(db)
        finally:
            TASK_HANDLERS.pop(key, None)

        db.refresh(task)
        assert calls == [key]
        assert task.last_status == "success"
        assert task.last_run_at is not None and task.last_run_at > before


def test_a_skipped_task_is_immediately_due_for_a_process_with_the_handler():
    """Peers on older builds still stamp `last_run_at` when they skip. A process that
    owns the handler must treat a skipped task as due regardless, or one stale worker
    starves the whole fleet."""
    from datetime import datetime

    with blank_session() as db:
        key = f"probe_skipfast_{unique_code()}"
        task = _due_task(db, key)
        # An old-code peer just consumed the tick: fresh last_run_at, skipped status.
        task.last_run_at = datetime.utcnow()
        task.last_status = "skipped"
        db.commit()

        calls: list[str] = []
        register_handler(key, lambda db_, task_: calls.append(str(task_.key)) or {"ok": True})
        try:
            run_due_tasks(db)
        finally:
            TASK_HANDLERS.pop(key, None)

        assert calls == [key], "the handler-owning process must reclaim a skipped task"
        db.refresh(task)
        assert task.last_status == "success"
