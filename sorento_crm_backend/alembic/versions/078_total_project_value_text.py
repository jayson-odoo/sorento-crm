"""Add total_project_value_text for descriptive values (e.g. BULK ORDER EST RM1.6MIL).

Revision ID: 078_total_project_value_text
Revises: 077_pr_sponsorship_fields
Create Date: 2026-02-21
"""
from alembic import op
import sqlalchemy as sa


revision = "078_total_project_value_text"
down_revision = "077_pr_sponsorship_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "purchase_requests",
        sa.Column("total_project_value_text", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("purchase_requests", "total_project_value_text")
