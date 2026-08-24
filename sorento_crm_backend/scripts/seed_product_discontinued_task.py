"""Idempotent seed for the product-discontinued notification scheduled task.

Creates (or leaves untouched) the ``product_discontinued_check`` row in
``scheduled_tasks`` so the heartbeat batcher runs every 15 minutes. Safe to
re-run; only inserts when the key is absent. Prod has no git repo - run via
the backend venv after deploy:

    python -m scripts.seed_product_discontinued_task
"""
from __future__ import annotations

from app.database import SessionLocal
from app.models.scheduled_task import ScheduledTask

KEY = "product_discontinued_check"


def main() -> None:
    db = SessionLocal()
    try:
        existing = db.query(ScheduledTask).filter(ScheduledTask.key == KEY).first()
        if existing:
            print(f"[seed] {KEY} already exists (enabled={existing.enabled}, "
                  f"every {existing.interval_value} {existing.interval_unit}) - no change")
            return
        task = ScheduledTask(
            key=KEY,
            name="Product Discontinued Notification",
            description=(
                "Reports newly-discontinued products (batched) to subscribed staff. "
                "Each run notifies once with the count + a deep link to the product "
                "list filtered to that batch."
            ),
            enabled=True,
            interval_unit="minutes",
            interval_value=15,
            timezone="UTC",
        )
        db.add(task)
        db.commit()
        print(f"[seed] created {KEY} (every 15 minutes, enabled)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
