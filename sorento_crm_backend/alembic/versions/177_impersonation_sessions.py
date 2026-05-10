"""Impersonation sessions table.

Stores active and historical admin-impersonates-user sessions. Partial unique
index on ``admin_user_id WHERE ended_at IS NULL`` enforces at most one active
session per admin.

Revision ID: 177_impersonation_sessions
Revises: 176_attachment_field_links
Create Date: 2026-05-09
"""

import sqlalchemy as sa
from alembic import op


revision = "177_impersonation_sessions"
down_revision = "176_attachment_field_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "impersonation_sessions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "admin_user_id",
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
            "started_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("ended_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("started_ip", sa.String(length=100), nullable=True),
        sa.Column("started_user_agent", sa.String(length=500), nullable=True),
    )
    op.create_index(
        "ix_impersonation_sessions_admin_user_id",
        "impersonation_sessions",
        ["admin_user_id"],
    )
    op.create_index(
        "ix_impersonation_sessions_target_user_id",
        "impersonation_sessions",
        ["target_user_id"],
    )
    op.create_index(
        "uq_impersonation_sessions_active_admin",
        "impersonation_sessions",
        ["admin_user_id"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_impersonation_sessions_active_admin",
        table_name="impersonation_sessions",
    )
    op.drop_index(
        "ix_impersonation_sessions_target_user_id",
        table_name="impersonation_sessions",
    )
    op.drop_index(
        "ix_impersonation_sessions_admin_user_id",
        table_name="impersonation_sessions",
    )
    op.drop_table("impersonation_sessions")
