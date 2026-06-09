"""Complaint resolved status: add resolved_at / resolved_by columns.

The customer-service team closes an approved complaint via a new "Resolve" action
(status -> 'resolved'), which also resolves the customer-service form-SLA stage.
These columns record who resolved it and when, mirroring rejected_at / rejected_by.

Revision ID: 227_complaint_resolved_status
Revises: 226_respond_templates
Create Date: 2026-06-09
"""

import sqlalchemy as sa
from alembic import op


revision = "227_complaint_resolved_status"
down_revision = "226_respond_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("complaints", sa.Column("resolved_at", sa.DateTime(timezone=False), nullable=True))
    op.add_column("complaints", sa.Column("resolved_by", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("complaints", "resolved_by")
    op.drop_column("complaints", "resolved_at")
