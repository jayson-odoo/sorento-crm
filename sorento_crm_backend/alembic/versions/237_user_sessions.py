"""Staff rolling sessions: user_sessions table.

Opaque DB-backed sessions for CRM staff login (clone of portal_tokens, keyed to
users instead of Respond.io contacts). Replaces stateless NextAuth JWT validation
with revocable, sliding 30-day sessions. See
docs/plans/PLAN-staff-rolling-sessions-fastapi-auth.md.

Revision ID: 237_user_sessions
Revises: 932195fa2398
Create Date: 2026-06-21
"""
from alembic import op
import sqlalchemy as sa


revision = "237_user_sessions"
down_revision = "932195fa2398"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("token", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("rolling", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_user_sessions_token", "user_sessions", ["token"], unique=True)
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_user_sessions_expires_at", table_name="user_sessions")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_index("ix_user_sessions_token", table_name="user_sessions")
    op.drop_table("user_sessions")
