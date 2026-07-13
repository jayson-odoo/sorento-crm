"""health_alert_state table + seed digest/watchdog scheduled tasks (WS3).

Revision ID: 267_health_alert_state_and_tasks
Revises: 266_seed_n8n_liveness_ping
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "267_health_alert_state_and_tasks"
down_revision = "266_seed_n8n_liveness_ping"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "health_alert_state",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("alert_key", sa.String(length=200), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False, server_default="ok"),
        sa.Column("last_alerted_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("last_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_health_alert_state_alert_key", "health_alert_state", ["alert_key"], unique=True)

    # Watchdog: frequent immediate-alert evaluator.
    op.execute(
        text(
            """
            INSERT INTO scheduled_tasks (
                key, name, description, enabled, interval_unit, interval_value,
                timezone, start_at, next_run_at, metadata, created_at, updated_at
            ) VALUES (
                'system_health_watchdog',
                'System health watchdog',
                'Every few minutes: evaluates immediate alert conditions (n8n liveness/failed integration logs, failed/overdue scheduled tasks, integration failure spikes) and notifies admins on transition (de-duped via health_alert_state).',
                true, 'minutes', 10, 'UTC', NULL, now() AT TIME ZONE 'utc',
                '{}'::jsonb, now() AT TIME ZONE 'utc', now() AT TIME ZONE 'utc'
            ) ON CONFLICT (key) DO NOTHING
            """
        )
    )

    # Daily digest.
    op.execute(
        text(
            """
            INSERT INTO scheduled_tasks (
                key, name, description, enabled, interval_unit, interval_value,
                timezone, start_at, next_run_at, metadata, created_at, updated_at
            ) VALUES (
                'system_health_daily_digest',
                'System health daily digest',
                'Daily: sends admins an in-app + email summary of system health (integrations, imports, scheduled tasks, email queue, audit volume, n8n liveness). Recipients from system_settings.health_notify_role_ids (fallback: admins).',
                true, 'days', 1, 'UTC', NULL, now() AT TIME ZONE 'utc',
                '{"send_in_app": true, "send_email": true}'::jsonb, now() AT TIME ZONE 'utc', now() AT TIME ZONE 'utc'
            ) ON CONFLICT (key) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.execute(text("DELETE FROM scheduled_tasks WHERE key IN ('system_health_watchdog','system_health_daily_digest')"))
    op.drop_index("ix_health_alert_state_alert_key", table_name="health_alert_state")
    op.drop_table("health_alert_state")
