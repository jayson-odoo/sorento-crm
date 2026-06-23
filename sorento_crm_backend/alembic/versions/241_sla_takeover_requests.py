"""sla_takeover_requests table + system_settings.takeover_cooldown_seconds

Takeover cooldown feature (PLAN-takeover-cooldown): a pending-intent takeover with a
veto window. New table holds the intent lifecycle; new settings column holds the global
cooldown (seconds, 0 = instant).

Revision ID: 241_sla_takeover
Revises: 240_notif_subs
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "241_sla_takeover"
down_revision = "240_notif_subs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "system_settings",
        sa.Column(
            "takeover_cooldown_seconds",
            sa.Integer(),
            nullable=False,
            server_default="60",
        ),
    )

    op.create_table(
        "sla_takeover_requests",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "tracking_id",
            UUID(as_uuid=False),
            sa.ForeignKey("conversation_sla_tracking.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "initiator_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "contested_assignee_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("team_id", UUID(as_uuid=False), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("commit_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("resolution_reason", sa.String(32), nullable=True),
        sa.Column(
            "resolved_by_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=False), nullable=True),
    )
    op.create_index(
        "ix_sla_takeover_requests_tracking_id", "sla_takeover_requests", ["tracking_id"]
    )
    op.create_index(
        "ix_sla_takeover_requests_status_commit_at",
        "sla_takeover_requests",
        ["status", "commit_at"],
    )
    # At most one pending takeover per tracking.
    op.create_index(
        "uq_sla_takeover_requests_one_pending",
        "sla_takeover_requests",
        ["tracking_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("uq_sla_takeover_requests_one_pending", table_name="sla_takeover_requests")
    op.drop_index("ix_sla_takeover_requests_status_commit_at", table_name="sla_takeover_requests")
    op.drop_index("ix_sla_takeover_requests_tracking_id", table_name="sla_takeover_requests")
    op.drop_table("sla_takeover_requests")
    op.drop_column("system_settings", "takeover_cooldown_seconds")
