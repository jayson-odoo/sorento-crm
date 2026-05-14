"""Contact impersonation sessions table.

Tracks an admin browsing the public submission portal as a contact (OTP gate
bypassed via verified_at on the minted portal_token). Partial unique index on
``admin_user_id WHERE ended_at IS NULL`` enforces at most one active contact
impersonation session per admin.

Revision ID: 194_contact_impersonation_sessions
Revises: 193_drop_promo_type
Create Date: 2026-05-15
"""

import sqlalchemy as sa
from alembic import op


revision = "194_contact_impersonation_sessions"
down_revision = "193_drop_promo_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contact_impersonation_sessions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "admin_user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("target_contact_id", sa.Text(), nullable=False),
        sa.Column("space_id", sa.Text(), nullable=False),
        sa.Column(
            "portal_token_id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            sa.ForeignKey("portal_tokens.id", ondelete="CASCADE"),
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
        "ix_contact_impersonation_admin_user_id",
        "contact_impersonation_sessions",
        ["admin_user_id"],
    )
    op.create_index(
        "ix_contact_impersonation_target_contact_id",
        "contact_impersonation_sessions",
        ["target_contact_id"],
    )
    op.create_index(
        "ix_contact_impersonation_portal_token_id",
        "contact_impersonation_sessions",
        ["portal_token_id"],
    )
    op.create_index(
        "uq_contact_impersonation_active_admin",
        "contact_impersonation_sessions",
        ["admin_user_id"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_contact_impersonation_active_admin",
        table_name="contact_impersonation_sessions",
    )
    op.drop_index(
        "ix_contact_impersonation_portal_token_id",
        table_name="contact_impersonation_sessions",
    )
    op.drop_index(
        "ix_contact_impersonation_target_contact_id",
        table_name="contact_impersonation_sessions",
    )
    op.drop_index(
        "ix_contact_impersonation_admin_user_id",
        table_name="contact_impersonation_sessions",
    )
    op.drop_table("contact_impersonation_sessions")
