"""Make inbound_shipments.shipment_number nullable (n8n posts rows before number is assigned).

Revision ID: 191_inbound_shipment_number_nullable
Revises: 189_warehouse_name_nullable
Create Date: 2026-05-14
"""
import sqlalchemy as sa
from alembic import op


revision = "191_inbound_shipment_number_nullable"
down_revision = "189_warehouse_name_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "inbound_shipments",
        "shipment_number",
        existing_type=sa.String(length=50),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "inbound_shipments",
        "shipment_number",
        existing_type=sa.String(length=50),
        nullable=False,
    )
