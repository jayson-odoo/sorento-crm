"""Seed initial scheduled tasks: respond_contacts_sync, integration_log_retry, import_job_processor.

Revision ID: 072_seed_scheduled_tasks
Revises: 071_scheduled_tasks
Create Date: 2026-02-21

"""
from alembic import op
from sqlalchemy import text


revision = "072_seed_scheduled_tasks"
down_revision = "071_scheduled_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # next_run_at set to now() so first heartbeat can run them
    op.execute(
        text(
            """
            INSERT INTO scheduled_tasks (
                key, name, description, enabled, interval_unit, interval_value,
                timezone, start_at, next_run_at, created_at, updated_at
            ) VALUES
            (
                'respond_contacts_sync',
                'Respond.io Contact Sync',
                'Sync Respond.io contacts missing backend_id: list, upsert local, set custom field.',
                true,
                'minutes',
                15,
                'UTC',
                NULL,
                now() AT TIME ZONE 'utc',
                now() AT TIME ZONE 'utc',
                now() AT TIME ZONE 'utc'
            ),
            (
                'integration_log_retry',
                'Integration Log Retry',
                'Process pending integration logs that are ready for retry.',
                true,
                'minutes',
                2,
                'UTC',
                NULL,
                now() AT TIME ZONE 'utc',
                now() AT TIME ZONE 'utc',
                now() AT TIME ZONE 'utc'
            ),
            (
                'import_job_processor',
                'Import Job Processor',
                'Process RQ import jobs from the queue.',
                true,
                'minutes',
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
    op.execute(
        text(
            "DELETE FROM scheduled_tasks WHERE key IN ('respond_contacts_sync', 'integration_log_retry', 'import_job_processor')"
        )
    )
