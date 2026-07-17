"""SCM M1 — add sales_orders.requested_delivery_date.

The M1 sales-order surface (D14) surfaces a customer-requested delivery date
distinct from ``order_date`` (when the SO was raised). Adds a nullable Date
column so the create/edit form and the list/detail can round-trip it.

Idempotent: uses ADD COLUMN IF NOT EXISTS because the local demo DB may already
carry the column (applied out-of-band alongside the M0 objects).

Revision ID: 275_scm_so_req_deliv
Revises: 274_scm_m0_views_reg
Create Date: 2026-07-15
"""
from alembic import op


revision = "275_scm_so_req_deliv"
down_revision = "274_scm_m0_views_reg"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE sales_orders ADD COLUMN IF NOT EXISTS requested_delivery_date date"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE sales_orders DROP COLUMN IF EXISTS requested_delivery_date")
