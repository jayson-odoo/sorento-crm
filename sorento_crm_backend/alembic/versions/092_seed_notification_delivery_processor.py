"""Seed scheduled task: notification_delivery_processor for outgoing email/push.

Revision ID: 092_notification_delivery
Revises: 091_rejected_from
Create Date: 2026-03-14

"""
from alembic import op
from sqlalchemy import text


revision = "092_notification_delivery"
down_revision = "091_rejected_from"
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
                'notification_delivery_processor',
                'Notification Delivery Processor',
                'Process outgoing notification emails and web push from the queue.',
                true,
                'seconds',
                10,
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
    op.execute(
        text("DELETE FROM scheduled_tasks WHERE key = 'notification_delivery_processor'")
    )
