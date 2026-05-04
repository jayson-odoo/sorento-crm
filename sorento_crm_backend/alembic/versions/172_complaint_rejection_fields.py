"""Add rejection_reason / rejected_at / rejected_by to complaints.

Mirrors the existing reject audit fields on stock_inquiries / purchase_requests
so that rejecting a complaint records who rejected it, when, and the supplied
reason. Approve does not require these fields.

Revision ID: 172_complaint_rejection_fields
Revises: 171_seed_complaint_decision_rbac
Create Date: 2026-05-05
"""

import sqlalchemy as sa
from alembic import op


revision = "172_complaint_rejection_fields"
down_revision = "171_seed_complaint_decision_rbac"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("complaints", sa.Column("rejection_reason", sa.Text(), nullable=True))
    op.add_column(
        "complaints",
        sa.Column("rejected_at", sa.DateTime(timezone=False), nullable=True),
    )
    op.add_column("complaints", sa.Column("rejected_by", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("complaints", "rejected_by")
    op.drop_column("complaints", "rejected_at")
    op.drop_column("complaints", "rejection_reason")
