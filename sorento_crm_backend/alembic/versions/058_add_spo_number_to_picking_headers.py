"""Add spo_number to picking_headers (GRN header link to SPO).

Revision ID: 058_spo_number_picking_headers
Revises: 057_attachment_access_levels
Create Date: 2026-02-19

"""
from alembic import op
import sqlalchemy as sa


revision = "058_spo_number_picking_headers"
down_revision = "057_attachment_access_levels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "picking_headers",
        sa.Column("spo_number", sa.String(50), nullable=True),
    )
    op.create_index(
        "ix_picking_headers_spo_number",
        "picking_headers",
        ["spo_number"],
    )


def downgrade() -> None:
    op.drop_index("ix_picking_headers_spo_number", table_name="picking_headers")
    op.drop_column("picking_headers", "spo_number")
