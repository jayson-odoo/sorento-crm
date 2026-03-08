"""Add line_status to inbound_shipment_lines for n8n / API.

Revision ID: 081_line_status
Revises: 080_users_tier
Create Date: 2026-03-08

Stores computed line-level status: in_transit, allocated, partially_allocated,
received, partially_received (derived from quantity_shipped, allocated, received).
"""
from alembic import op
import sqlalchemy as sa


revision = "081_line_status"
down_revision = "080_users_tier"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inbound_shipment_lines",
        sa.Column("line_status", sa.String(50), nullable=False, server_default="in_transit"),
    )


def downgrade() -> None:
    op.drop_column("inbound_shipment_lines", "line_status")
