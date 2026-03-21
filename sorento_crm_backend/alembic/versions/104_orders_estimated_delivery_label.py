"""Rename orders list field label promised_delivery_date → Estimated delivery.

Revision ID: 104_orders_estimated_delivery_label
Revises: 103_inbound_shipment_eta
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "104_orders_estimated_delivery_label"
down_revision = "103_inbound_shipment_eta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE list_query_fields AS f
            SET label = 'Estimated delivery'
            FROM list_query_resources AS r
            WHERE f.resource_id = r.id
              AND r.resource_key = 'orders'
              AND f.field_key = 'promised_delivery_date'
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE list_query_fields AS f
            SET label = 'Promised delivery'
            FROM list_query_resources AS r
            WHERE f.resource_id = r.id
              AND r.resource_key = 'orders'
              AND f.field_key = 'promised_delivery_date'
            """
        )
    )
