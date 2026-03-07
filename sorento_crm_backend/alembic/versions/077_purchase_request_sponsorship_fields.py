"""Add sponsorship form and line pricing fields to purchase_requests.

Revision ID: 077_pr_sponsorship_fields
Revises: 076_entity_attachment_links
Create Date: 2026-02-21

- Header: delivery_address, total_project_value, sponsor_subject (sponsorship form).
- Lines: unit_price, total (for sponsorship form line totals; PR can leave null).
"""
from alembic import op
import sqlalchemy as sa


revision = "077_pr_sponsorship_fields"
down_revision = "076_entity_attachment_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "purchase_requests",
        sa.Column("delivery_address", sa.Text(), nullable=True),
    )
    op.add_column(
        "purchase_requests",
        sa.Column("total_project_value", sa.Numeric(15, 2), nullable=True),
    )
    op.add_column(
        "purchase_requests",
        sa.Column("sponsor_subject", sa.Text(), nullable=True),
    )
    op.add_column(
        "purchase_request_lines",
        sa.Column("unit_price", sa.Numeric(15, 2), nullable=True),
    )
    op.add_column(
        "purchase_request_lines",
        sa.Column("total", sa.Numeric(15, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("purchase_request_lines", "total")
    op.drop_column("purchase_request_lines", "unit_price")
    op.drop_column("purchase_requests", "sponsor_subject")
    op.drop_column("purchase_requests", "total_project_value")
    op.drop_column("purchase_requests", "delivery_address")
