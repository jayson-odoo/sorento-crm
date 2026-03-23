"""Drop legacy order_items table.

Revision ID: 114_drop_order_items
Revises: 113_inbound_shipment_estimated_arrival
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "114_drop_order_items"
down_revision = "113_inbound_shipment_estimated_arrival"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Legacy table cleanup: the app uses order_lines only.
    op.execute(sa.text("DROP TABLE IF EXISTS order_items CASCADE"))


def downgrade() -> None:
    # Intentionally left as no-op since order_items is legacy and should not be restored.
    pass
