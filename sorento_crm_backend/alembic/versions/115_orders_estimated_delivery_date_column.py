"""Rename orders.promised_delivery_date → estimated_delivery_date; sync list_query_fields.

Revision ID: 115_orders_estimated_delivery_date_column
Revises: 114_drop_order_items
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "115_orders_estimated_delivery_date_column"
down_revision = "114_drop_order_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "orders" not in insp.get_table_names():
        return

    cols = {c["name"] for c in insp.get_columns("orders")}
    if "promised_delivery_date" in cols and "estimated_delivery_date" not in cols:
        op.execute(
            'ALTER TABLE orders RENAME COLUMN promised_delivery_date TO estimated_delivery_date'
        )

    # List query metadata: field_key + compile_key (runtime uses Order attribute name)
    op.execute(
        sa.text(
            """
            UPDATE list_query_fields AS f
            SET field_key = 'estimated_delivery_date',
                compile_key = 'order.estimated_delivery_date'
            FROM list_query_resources AS r
            WHERE f.resource_id = r.id
              AND r.resource_key = 'orders'
              AND f.field_key = 'promised_delivery_date'
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "orders" not in insp.get_table_names():
        return

    cols = {c["name"] for c in insp.get_columns("orders")}
    if "estimated_delivery_date" in cols and "promised_delivery_date" not in cols:
        op.execute(
            'ALTER TABLE orders RENAME COLUMN estimated_delivery_date TO promised_delivery_date'
        )

    op.execute(
        sa.text(
            """
            UPDATE list_query_fields AS f
            SET field_key = 'promised_delivery_date',
                compile_key = 'order.promised_delivery_date'
            FROM list_query_resources AS r
            WHERE f.resource_id = r.id
              AND r.resource_key = 'orders'
              AND f.field_key = 'estimated_delivery_date'
            """
        )
    )
