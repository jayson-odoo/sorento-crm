"""Flip complaints.required_on_site_support default to false; reset existing rows.

Revision ID: 186_complaint_required_on_site_support_default_false
Revises: 185_complaint_required_on_site_support
Create Date: 2026-05-10
"""
import sqlalchemy as sa
from alembic import op


revision = "186_complaint_required_on_site_support_default_false"
down_revision = "185_complaint_required_on_site_support"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "complaints",
        "required_on_site_support",
        server_default=sa.false(),
    )
    op.execute("UPDATE complaints SET required_on_site_support = false")


def downgrade() -> None:
    op.alter_column(
        "complaints",
        "required_on_site_support",
        server_default=sa.true(),
    )
