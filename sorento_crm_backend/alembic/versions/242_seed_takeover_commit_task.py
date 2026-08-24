"""seed the takeover_request_commit scheduled task (idempotent)

The cron row that drives the takeover-cooldown commit sweep is runtime data, not
schema - so it would never reach prod without a seed. This data migration inserts it
if absent, so every environment gets it on `alembic upgrade head`. Safe to re-run:
guarded by NOT EXISTS on the unique key. See PLAN-takeover-cooldown (Q5/AC-COMMIT-7).

Revision ID: 242_seed_takeover
Revises: 241_sla_takeover
Create Date: 2026-06-23
"""
from alembic import op


revision = "242_seed_takeover"
down_revision = "241_sla_takeover"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO scheduled_tasks
            (id, key, name, description, enabled, interval_unit, interval_value,
             timezone, created_at, updated_at)
        SELECT gen_random_uuid(),
               'takeover_request_commit',
               'Takeover Cooldown Commit',
               'Commits pending SLA takeover requests whose cooldown has elapsed '
               'unchallenged, after re-validating the task is still takeable. Voids '
               'requests whose premise changed (resolved / reassigned / escalated / '
               'initiator ineligible).',
               true, 'seconds', 15, 'UTC', now(), now()
        WHERE NOT EXISTS (
            SELECT 1 FROM scheduled_tasks WHERE key = 'takeover_request_commit'
        );
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM scheduled_tasks WHERE key = 'takeover_request_commit';"
    )
