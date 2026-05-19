"""Backfill customers master from distinct orders.debtor_name.

Many orders carry `debtor_name` (free text) without a matching `customers` row
(e.g. project / cash debtors imported from legacy Sage). The MCP layer now
requires UUID-only entity refs, so every distinct debtor needs a customers.id
to resolve to. This migration inserts a customers row per distinct debtor name
that doesn't already have one. Idempotent — re-run safely.

Sibling migration 207 backfills orders.customer_id from this seed.

Revision ID: 206_customers_backfill_from_orders
Revises: 205_attachments_upload_batch_id
Create Date: 2026-05-19
"""
from __future__ import annotations

from alembic import op


revision = "206_customers_backfill_from_orders"
down_revision = "205_attachments_upload_batch_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO customers (id, customer_code, customer_name, customer_type, is_active, created_at)
        SELECT
            gen_random_uuid(),
            COALESCE(
                NULLIF(btrim(src.debtor_code), ''),
                'DBR-' || substr(md5(lower(btrim(src.debtor_name))), 1, 10)
            ) AS customer_code,
            btrim(src.debtor_name) AS customer_name,
            'company' AS customer_type,
            TRUE AS is_active,
            now() AS created_at
        FROM (
            SELECT DISTINCT debtor_name, debtor_code
            FROM orders
            WHERE debtor_name IS NOT NULL
              AND btrim(debtor_name) <> ''
              AND deleted_at IS NULL
        ) src
        WHERE NOT EXISTS (
            SELECT 1 FROM customers c
            WHERE lower(btrim(c.customer_name)) = lower(btrim(src.debtor_name))
        )
        ON CONFLICT (customer_code) DO NOTHING;
        """
    )


def downgrade() -> None:
    # Non-reversible: we can't tell which customers were seeded by this migration
    # versus those created through normal application flows. Leave rows in place.
    pass
