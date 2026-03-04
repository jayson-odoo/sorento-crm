"""Add view_tokens table for public view links (no login).

Revision ID: 065_view_tokens
Revises: 064_complaints_assigned_to
Create Date: 2026-02-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "065_view_tokens"
down_revision = "064_complaints_assigned_to"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "view_tokens",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.String(100), nullable=False),
        sa.Column("token", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_view_tokens_token", "view_tokens", ["token"], unique=True)
    op.create_index("ix_view_tokens_entity", "view_tokens", ["entity_type", "entity_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_view_tokens_entity", table_name="view_tokens")
    op.drop_index("ix_view_tokens_token", table_name="view_tokens")
    op.drop_table("view_tokens")
