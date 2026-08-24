"""Drive a scheduled task through every overdue state and show what each surface reports.

Verification aid for UAC OBS-S2-01..S2-11. Answers, against the real DB, the
question the old implementation could not: for a given lateness, do the health
card and the alert email agree, and does the alert say something actionable?

Runs inside a transaction that is always rolled back - the DB is untouched.

    venv/bin/python scripts/simulate_overdue_states.py [task_key]
"""
import sys
from datetime import datetime, timedelta

from app.database import SessionLocal
from app.models.scheduled_task import ScheduledTask
from app.api.v1.system import health as health_mod
from app.services import system_health_alert_service as alert_svc
from app.services.scheduled_task_service import (
    compute_due_at,
    compute_grace,
    get_overdue_tasks,
    resolve_grace_percent,
)


def main() -> int:
    key = sys.argv[1] if len(sys.argv) > 1 else None
    db = SessionLocal()
    try:
        q = db.query(ScheduledTask).filter(ScheduledTask.enabled.is_(True))
        task = q.filter(ScheduledTask.key == key).first() if key else q.order_by(ScheduledTask.key).first()
        if task is None:
            print(f"No enabled task found{f' for key {key!r}' if key else ''}.")
            return 1

        # Quiesce every other task so the output isolates this one.
        others = [t for t in q.all() if t.id != task.id]
        for other in others:
            other.last_run_at = datetime.utcnow()

        now = datetime.utcnow()
        pct = resolve_grace_percent(db)
        grace = compute_grace(task, pct)
        interval = compute_due_at(task) - (task.last_run_at or task.created_at)

        print(f"task      : {task.key} ({task.name})")
        print(f"interval  : every {task.interval_value} {task.interval_unit}")
        print(f"grace     : {grace.total_seconds():.0f}s  ({pct}% of interval, clamped)")
        print()

        scenarios = [
            ("healthy - ran just now", timedelta(seconds=1)),
            ("late, inside grace", interval + grace * 0.5),
            ("exactly at due + grace (boundary)", interval + grace),
            ("overdue - past grace", interval + grace + timedelta(seconds=90)),
            ("badly overdue", interval * 20),
        ]

        print(f"{'scenario':36} {'ran ago':>12} {'card':>6} {'alert':>7}  agree")
        print("-" * 78)
        for label, ago in scenarios:
            task.last_run_at = now - ago
            db.flush()

            card = health_mod._scheduled_tasks_health(db, now)
            is_bad, detail = alert_svc._eval_scheduled_tasks(db, now)
            shared = {o.task.key for o in get_overdue_tasks(db, now)}

            alerts = task.key in detail
            agree = (card.overdue == len(shared)) and (alerts == (task.key in shared))
            print(
                f"{label:36} {ago.total_seconds()/60:>10.1f}m "
                f"{card.overdue:>6} {'YES' if alerts else 'no':>7}  "
                f"{'ok' if agree else 'MISMATCH'}"
            )

        # Show the actual email body for the overdue case - the thing that was
        # previously just a bare list of task keys.
        task.last_run_at = now - (interval * 20)
        db.flush()
        _, detail = alert_svc._eval_scheduled_tasks(db, now)
        print("\nalert email body:\n")
        print(detail)

        return 0
    finally:
        db.rollback()  # nothing above is ever committed
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
