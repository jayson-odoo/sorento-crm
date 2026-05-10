"""Add required_on_site_support boolean to complaints (default false).

Revision ID: 185_complaint_required_on_site_support
Revises: 184_portal_token_verified_at
Create Date: 2026-05-10
"""
import sqlalchemy as sa
from alembic import op


revision = "185_complaint_required_on_site_support"
down_revision = "184_portal_token_verified_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "complaints",
        sa.Column(
            "required_on_site_support",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("complaints", "required_on_site_support")
