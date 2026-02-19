"""Create notifications and notification_deliveries tables

Revision ID: 045_notifications
Revises: 044_import_jobs_updated_at
Create Date: 2026-02-16

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "045_notifications"
down_revision = "044_import_jobs_updated_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("type", sa.String(80), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("data", postgresql.JSONB(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("source_entity_type", sa.String(80), nullable=True),
        sa.Column("source_entity_id", sa.String(255), nullable=True),
        sa.Column("event_type", sa.String(80), nullable=True),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_type", "notifications", ["type"])
    op.create_index("ix_notifications_source_entity_type", "notifications", ["source_entity_type"])
    op.create_index("ix_notifications_source_entity_id", "notifications", ["source_entity_id"])
    op.create_index("ix_notifications_event_type", "notifications", ["event_type"])
    op.create_index("ix_notifications_user_id_created_at", "notifications", ["user_id", "created_at"])
    op.create_unique_constraint(
        "uq_notification_user_source_event",
        "notifications",
        ["user_id", "source_entity_type", "source_entity_id", "event_type"],
    )

    op.create_table(
        "notification_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("notification_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("sent_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_notification_deliveries_notification_id", "notification_deliveries", ["notification_id"])
    op.create_index("ix_notification_deliveries_channel", "notification_deliveries", ["channel"])
    op.create_index("ix_notification_deliveries_notification_id_channel", "notification_deliveries", ["notification_id", "channel"])


def downgrade() -> None:
    op.drop_table("notification_deliveries")
    op.drop_table("notifications")
