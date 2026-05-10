"""Seed scheduled task `form_sla_overdue_scan`.

Periodically scans form SLA trackers (stock_inquiry / purchase_request /
sponsorship_form / complaint) for response/resolution due_at past now and
escalates them via the access-agent tier chain.

Revision ID: 179_seed_form_sla_overdue_scan
Revises: 178_form_sla_configs
Create Date: 2026-05-09
"""
from alembic import op
from sqlalchemy import text


revision = "179_seed_form_sla_overdue_scan"
down_revision = "178_form_sla_configs"
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
                'form_sla_overdue_scan',
                'Form SLA Overdue Scan',
                'Escalate form SLA trackers (stock_inquiry / purchase_request / sponsorship_form / complaint) past response or resolution due_at to the next access-agent tier.',
                true,
                'minutes',
                2,
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
        text("DELETE FROM scheduled_tasks WHERE key = 'form_sla_overdue_scan'")
    )
