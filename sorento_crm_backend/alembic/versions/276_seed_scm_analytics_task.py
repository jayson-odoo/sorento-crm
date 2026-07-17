"""Seed scheduled task `scm_analytics` (SCM M2 nightly analytics recompute).

Registers the configurable ``scheduled_tasks`` row that the scheduler heartbeat
drives on the worker/scheduler process (gated behind ``ENABLE_SCHEDULER``). The
handler ``_handler_scm_analytics`` runs ``analytics_service.run_analytics`` — a
full-catalog recompute of demand rate, ABC/XYZ classification and supplier
performance — and writes one ``scm.scm_analytics_run`` log row per run.

Cadence is configurable: this seeds the nightly default (``days`` / 1). The
interval, enablement and an optional ``metadata`` ``{scope, config}`` can be
edited via the scheduled-tasks API/UI with no code change.

Revision ID: 276_seed_scm_analytics_task
Revises: 275_scm_so_req_deliv
Create Date: 2026-07-16
"""
from alembic import op
from sqlalchemy import text


revision = "276_seed_scm_analytics_task"
down_revision = "275_scm_so_req_deliv"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        text(
            """
            INSERT INTO scheduled_tasks (
                key, name, description, enabled, interval_unit, interval_value,
                timezone, start_at, next_run_at, created_at, updated_at
            ) VALUES (
                'scm_analytics',
                'SCM Analytics Recompute',
                'Full SCM analytics recompute (demand rate, ABC/XYZ classification, supplier performance). Writes one scm_analytics_run log row per run. Nightly by default; cadence configurable.',
                true,
                'days',
                1,
                'UTC',
                NULL,
                now() AT TIME ZONE 'utc',
                now() AT TIME ZONE 'utc',
                now() AT TIME ZONE 'utc'
            )
            ON CONFLICT (key) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.execute(text("DELETE FROM scheduled_tasks WHERE key = 'scm_analytics'"))
