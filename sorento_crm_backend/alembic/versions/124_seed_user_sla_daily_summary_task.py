"""Seed scheduled task: user_sla_daily_summary (daily SLA summary per user).

Revision ID: 124_user_sla_daily_summary
Revises: 123_inbound_line_metrics
Create Date: 2026-03-31

"""
from alembic import op
from sqlalchemy import text


revision = "124_user_sla_daily_summary"
down_revision = "123_inbound_line_metrics"
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
                'user_sla_daily_summary',
                'User SLA daily summary',
                'Sends each active user a daily performance summary (responded/resolved from SLA event logs) and outstanding assigned conversations. Use task metadata send_in_app and send_email (default true) to control delivery channels.',
                true,
                'days',
                1,
                'UTC',
                NULL,
                now() AT TIME ZONE 'utc',
                '{"send_in_app": true, "send_email": true}'::jsonb,
                now() AT TIME ZONE 'utc',
                now() AT TIME ZONE 'utc'
            )
            ON CONFLICT (key) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.execute(text("DELETE FROM scheduled_tasks WHERE key = 'user_sla_daily_summary'"))
