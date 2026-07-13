"""Seed scheduled task: n8n_liveness_ping (System Health observability WS1d).

Hourly probe of the dedicated n8n `system-healthcheck-ping` workflow. Proves the
CRM<->n8n round-trip is alive during quiet (zero-upload) periods. The watchdog
(WS3) reads the latest `n8n_healthcheck` integration_log to alert on a dead probe.

Revision ID: 266_seed_n8n_liveness_ping
Revises: 265_health_observability
"""
from alembic import op
from sqlalchemy import text


revision = "266_seed_n8n_liveness_ping"
down_revision = "265_health_observability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        text(
            """
            INSERT INTO scheduled_tasks (
                key, name, description, enabled, interval_unit, interval_value,
                timezone, start_at, next_run_at, metadata, created_at, updated_at
            ) VALUES (
                'n8n_liveness_ping',
                'n8n liveness ping',
                'Hourly probe of the n8n system-healthcheck-ping workflow (webhook -> immediate /status callback, no data). Creates an n8n_healthcheck integration_log; the watchdog alerts if the latest probe is not success.',
                true,
                'hours',
                1,
                'UTC',
                NULL,
                now() AT TIME ZONE 'utc',
                '{}'::jsonb,
                now() AT TIME ZONE 'utc',
                now() AT TIME ZONE 'utc'
            )
            ON CONFLICT (key) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.execute(text("DELETE FROM scheduled_tasks WHERE key = 'n8n_liveness_ping'"))
