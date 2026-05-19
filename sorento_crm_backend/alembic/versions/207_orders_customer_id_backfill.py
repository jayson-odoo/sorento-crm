"""Backfill orders.customer_id from customers (matched on debtor_name).

Runs after 206 seeded the customers master from distinct debtor names. The MCP
list endpoints accept customer_ids (UUID) and filter Order.customer_id IN (...),
so legacy rows with NULL customer_id are invisible until backfilled.

Idempotent: only writes where the existing customer_id IS DISTINCT FROM the
match. Re-runnable as a cron / post-deploy step until OrderService.create is
updated to upsert customer inline.

Revision ID: 207_orders_customer_id_backfill
Revises: 206_customers_backfill_from_orders
Create Date: 2026-05-19
"""
from __future__ import annotations

from alembic import op


revision = "207_orders_customer_id_backfill"
down_revision = "206_customers_backfill_from_orders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE orders o
        SET customer_id = c.id
        FROM customers c
        WHERE o.debtor_name IS NOT NULL
          AND lower(btrim(o.debtor_name)) = lower(btrim(c.customer_name))
          AND (o.customer_id IS DISTINCT FROM c.id);
        """
    )


def downgrade() -> None:
    # Non-reversible: we don't know which customer_id values predated this run.
    pass
