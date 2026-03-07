"""Add assigned_to to complaints (Respond.io conversation assignee).

Revision ID: 064_complaints_assigned_to
Revises: 063_complaints_created_at
Create Date: 2026-02-21

"""
from alembic import op
import sqlalchemy as sa


revision = "064_complaints_assigned_to"
down_revision = "063_complaints_created_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "complaints",
        sa.Column("assigned_to", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("complaints", "assigned_to")
