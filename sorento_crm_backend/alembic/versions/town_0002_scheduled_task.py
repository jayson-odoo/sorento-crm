"""SORENTO-TOWN: the town snapshot job becomes a `scheduled_tasks` row (SCHEDULED-TASKS-GRID).

It ran as a bare APScheduler job, so System Management > Scheduled Tasks never listed it and a
failed company build was a log line only. Seed-only and idempotent (NOT EXISTS), so a DB that
converges through create_all upgrades cleanly. `next_run_at` stays NULL: the heartbeat treats a
row that never ran as due, the same as every seeded task.

Revision ID: town_0002_scheduled_task
Revises: (re-parented onto main's head by scripts/alembic-reparent.sh)
"""
import sqlalchemy as sa
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "town_0002_scheduled_task"
down_revision = "town_0001_town_days"
branch_labels = None
depends_on = None

# Owner ruling (9 Nov, Q3 b): outside these hours the task is not due, writes no run row and
# is not overdue (`scheduled_task_service._active_window`). Same hours as the tick's own guard
# (`app/services/town/snapshot.py` OPEN_MINUTE / CLOSE_MINUTE), which stays for Run now.
ACTIVE_WINDOW = '{"active_window": {"start": "07:00", "end": "22:05", "timezone": "Asia/Kuala_Lumpur"}}'


def upgrade() -> None:
    op.execute(sa.text(
        """
        INSERT INTO scheduled_tasks
            (id, key, name, description, enabled, interval_unit, interval_value,
             timezone, metadata, created_at, updated_at)
        SELECT gen_random_uuid(),
               'town_snapshot',
               'Sorento town snapshot',
               'Rebuilds each active company''s town snapshot, 07:00-22:05 Malaysia time. '
               'A company that fails to build is named in the last error.',
               true, 'minutes', 3, 'UTC', CAST(:window AS JSONB), now(), now()
        WHERE NOT EXISTS (SELECT 1 FROM scheduled_tasks WHERE key = 'town_snapshot');
        """
    ).bindparams(window=ACTIVE_WINDOW))


def downgrade() -> None:
    op.execute("DELETE FROM scheduled_tasks WHERE key = 'town_snapshot'")
