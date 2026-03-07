"""Add created_at to complaints.

Revision ID: 063_complaints_created_at
Revises: 062_drop_users_role_id
Create Date: 2026-02-21

"""
from alembic import op
import sqlalchemy as sa


revision = "063_complaints_created_at"
down_revision = "062_drop_users_role_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "complaints",
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("complaints", "created_at")
