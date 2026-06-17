"""Add attachment storage accessibility audit columns + seed daily scheduled task.

Revision ID: 234_attachment_storage_status
Revises: 233_attachment_type_is_direct_access
Create Date: 2026-06-16

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "234_attachment_storage_status"
down_revision = "233_attachment_type_is_direct_access"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "attachments",
        sa.Column(
            "storage_status",
            sa.String(length=20),
            nullable=False,
            server_default="unchecked",
        ),
    )
    op.add_column(
        "attachments",
        sa.Column("storage_checked_at", sa.DateTime(timezone=False), nullable=True),
    )
    op.create_index(
        "ix_attachments_storage_status", "attachments", ["storage_status"]
    )

    # Seed the daily audit task. next_run_at = now() so the first heartbeat runs it.
    op.execute(
        text(
            """
            INSERT INTO scheduled_tasks (
                key, name, description, enabled, interval_unit, interval_value,
                timezone, start_at, next_run_at, created_at, updated_at
            ) VALUES
            (
                'attachment_storage_audit',
                'Attachment Storage Audit',
                'List each storage bucket and flag attachments whose object is missing (storage_status).',
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
    op.execute(
        text("DELETE FROM scheduled_tasks WHERE key = 'attachment_storage_audit'")
    )
    op.drop_index("ix_attachments_storage_status", table_name="attachments")
    op.drop_column("attachments", "storage_checked_at")
    op.drop_column("attachments", "storage_status")
