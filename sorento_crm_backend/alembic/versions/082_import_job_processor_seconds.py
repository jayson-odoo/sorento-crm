"""Set import_job_processor default interval to 10 seconds.

Revision ID: 082_import_job_seconds
Revises: 081_line_status
Create Date: 2026-03-08
"""
from alembic import op
from sqlalchemy import text


revision = "082_import_job_seconds"
down_revision = "081_line_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        text(
            """
            UPDATE scheduled_tasks
            SET interval_unit = 'seconds',
                interval_value = 10,
                next_run_at = now() AT TIME ZONE 'utc',
                updated_at = now() AT TIME ZONE 'utc'
            WHERE key = 'import_job_processor'
            """
        )
    )


def downgrade() -> None:
    op.execute(
        text(
            """
            UPDATE scheduled_tasks
            SET interval_unit = 'minutes',
                interval_value = 1,
                updated_at = now() AT TIME ZONE 'utc'
            WHERE key = 'import_job_processor'
            """
        )
    )
