"""Staleness ladder state on projects, plus the daily sweep's cron row (S5b, AC-H5/H6).

Revision ID: 317_staleness
Revises: 316_forecast_dials

Three columns, all derived-but-PERSISTED, which is a deliberate choice. The level could be
computed on every read from ``last_meaningful_activity_at`` and the status threshold, and the
list pages do exactly that arithmetic anyway -- but the ladder also has to notify exactly
once per rung. Persisting the level is what makes the daily sweep idempotent: it can tell
"this project just became unattended" from "this project has been unattended for a fortnight",
and only the first of those is worth an email.

``stale_since`` is the moment the project ENTERED the ladder, not the moment it last moved up
it: the useful sentence for a manager is "untouched since 3 March", not "warned on Tuesday".

The `scheduled_tasks` row is seeded here for the same reason migration 242 seeds the takeover
commit sweep -- a cron row is runtime data, so without a data migration it never reaches prod
and the feature silently does nothing. Idempotent via NOT EXISTS on the unique key.
"""
from alembic import op

revision = "317_staleness"
down_revision = "316_forecast_dials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE projects
            ADD COLUMN IF NOT EXISTS stale_level INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS stale_since TIMESTAMP WITHOUT TIME ZONE,
            ADD COLUMN IF NOT EXISTS stale_reason VARCHAR(16);

        CREATE INDEX IF NOT EXISTS ix_projects_stale_level
            ON projects (stale_level) WHERE stale_level > 0;

        INSERT INTO scheduled_tasks
            (id, key, name, description, enabled, interval_unit, interval_value,
             timezone, created_at, updated_at)
        SELECT gen_random_uuid(),
               'project_staleness_sweep',
               'Project Staleness Sweep',
               'Walks live projects once a day and moves each one up or off the staleness '
               'ladder: nudge the owner, then warn the owner and copy management, then mark '
               'the project Unattended so colleagues may request a takeover. Never '
               'reassigns anything.',
               true, 'hours', 24, 'Asia/Kuala_Lumpur', now(), now()
        WHERE NOT EXISTS (
            SELECT 1 FROM scheduled_tasks WHERE key = 'project_staleness_sweep'
        );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM scheduled_tasks WHERE key = 'project_staleness_sweep';
        DROP INDEX IF EXISTS ix_projects_stale_level;
        ALTER TABLE projects
            DROP COLUMN IF EXISTS stale_level,
            DROP COLUMN IF EXISTS stale_since,
            DROP COLUMN IF EXISTS stale_reason;
        """
    )
