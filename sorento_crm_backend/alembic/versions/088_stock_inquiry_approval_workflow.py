"""Add stock inquiry approval workflow fields (rejection/reopen audit).

Revision ID: 088_stock_inquiry_approval
Revises: 087_document_numbering_rules
Create Date: 2026-03-14

"""
from alembic import op
import sqlalchemy as sa


revision = "088_stock_inquiry_approval"
down_revision = "087_document_numbering_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stock_inquiries", sa.Column("rejection_reason", sa.Text(), nullable=True))
    op.add_column("stock_inquiries", sa.Column("rejected_at", sa.DateTime(timezone=False), nullable=True))
    op.add_column("stock_inquiries", sa.Column("rejected_by", sa.Text(), nullable=True))
    op.add_column("stock_inquiries", sa.Column("reopen_reason", sa.Text(), nullable=True))
    op.add_column("stock_inquiries", sa.Column("reopened_at", sa.DateTime(timezone=False), nullable=True))
    op.add_column("stock_inquiries", sa.Column("reopened_by", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("stock_inquiries", "reopened_by")
    op.drop_column("stock_inquiries", "reopened_at")
    op.drop_column("stock_inquiries", "reopen_reason")
    op.drop_column("stock_inquiries", "rejected_by")
    op.drop_column("stock_inquiries", "rejected_at")
    op.drop_column("stock_inquiries", "rejection_reason")
