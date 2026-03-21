"""Add eta column to inbound_shipments.

Revision ID: 103_inbound_shipment_eta
Revises: 102_order_line_nested_export
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "103_inbound_shipment_eta"
down_revision = "102_order_line_nested_export"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("inbound_shipments", sa.Column("eta", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("inbound_shipments", "eta")
