"""Add rejected_from to stock_inquiries for reopen-to-correct-state.

Revision ID: 091_rejected_from
Revises: 090_sync_rbac
Create Date: 2026-03-14

"""
from alembic import op
import sqlalchemy as sa


revision = "091_rejected_from"
down_revision = "090_sync_rbac"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stock_inquiries",
        sa.Column("rejected_from", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("stock_inquiries", "rejected_from")
