"""Seed scheduled task: promotion_active_window (auto-deactivate promotions outside date range).

Revision ID: 139_seed_promotion_active_window_task
Revises: 138_form_inbound_shipment_access_levels
Create Date: 2026-04-13

"""
from alembic import op
from sqlalchemy import text


revision = "139_seed_promotion_active_window_task"
down_revision = "138_form_inbound_shipment_access_levels"
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
                'promotion_active_window',
                'Promotion active window',
                'Sets promotions to inactive when the Malaysia calendar date is before start or after end.',
                true,
                'hours',
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
    op.execute(text("DELETE FROM scheduled_tasks WHERE key = 'promotion_active_window'"))
