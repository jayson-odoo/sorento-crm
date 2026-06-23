"""add notification_subscriptions (coverage delegation)

Revision ID: 240_notif_subs
Revises: 239_tm_rr_optout
Create Date: 2026-06-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "240_notif_subs"
down_revision = "239_tm_rr_optout"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_subscriptions",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "subscriber_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_notification_subscriptions_subscriber_id",
        "notification_subscriptions",
        ["subscriber_id"],
    )
    op.create_index(
        "ix_notification_subscriptions_target_user_id",
        "notification_subscriptions",
        ["target_user_id"],
    )
    op.create_index(
        "uq_notification_subscriptions_subscriber_target",
        "notification_subscriptions",
        ["subscriber_id", "target_user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_notification_subscriptions_subscriber_target",
        table_name="notification_subscriptions",
    )
    op.drop_index(
        "ix_notification_subscriptions_target_user_id",
        table_name="notification_subscriptions",
    )
    op.drop_index(
        "ix_notification_subscriptions_subscriber_id",
        table_name="notification_subscriptions",
    )
    op.drop_table("notification_subscriptions")
