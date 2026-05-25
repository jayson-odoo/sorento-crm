"""Add quantity to complaints.

Revision ID: 213_complaints_quantity
Revises: 212_seed_pr_sponsorship_approved_automation
Create Date: 2026-05-25

The complaint portal form was missing a quantity field for the number of
affected/defective items. Stored as free text to mirror stock_inquiry.quantity
(values like "10" or "5 boxes").
"""
from alembic import op
import sqlalchemy as sa


revision = "213_complaints_quantity"
down_revision = "212_seed_pr_sponsorship_approved_automation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("complaints", sa.Column("quantity", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("complaints", "quantity")
