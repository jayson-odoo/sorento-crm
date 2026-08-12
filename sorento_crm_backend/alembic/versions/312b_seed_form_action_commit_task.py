"""seed the form_action_commit scheduled task (idempotent)

The cron row that drives the form-action grace-window sweep is runtime data, not
schema, so it would never reach prod without a seed. Guarded by NOT EXISTS on the
unique key, so re-running is safe.

15s matches the takeover sweep. The grace windows in play are ~10s, and the lazy
commit on GET /form-actions/current already covers anyone actually looking at the
form - this sweep is for the ones nobody has open.

Revision ID: 312b_seed_form_action_task
"""
from alembic import op


revision = "312b_seed_form_action_task"
down_revision = "312a_sla_form_actions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO scheduled_tasks
            (id, key, name, description, enabled, interval_unit, interval_value,
             timezone, created_at, updated_at)
        SELECT gen_random_uuid(),
               'form_action_commit',
               'Form Action Grace Commit',
               'Executes form-SLA actions whose grace window has closed. Voids any '
               'whose premise changed while they waited (the form was decided or moved '
               'on by someone else).',
               true, 'seconds', 15, 'UTC', now(), now()
        WHERE NOT EXISTS (
            SELECT 1 FROM scheduled_tasks WHERE key = 'form_action_commit'
        );
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM scheduled_tasks WHERE key = 'form_action_commit';")
