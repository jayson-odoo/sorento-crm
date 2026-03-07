"""Add requested_approval_by_user_id to purchase_requests.

Revision ID: 066_requested_approval_by
Revises: 065_view_tokens
Create Date: 2026-02-21

"""
from alembic import op
import sqlalchemy as sa


revision = "066_requested_approval_by"
down_revision = "065_view_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "purchase_requests",
        sa.Column("requested_approval_by_user_id", sa.String(100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("purchase_requests", "requested_approval_by_user_id")
