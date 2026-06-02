"""Re-seed customers by (debtor_code, debtor_name) PAIR after the composite
unique index landed in migration 220.

Migration 219 may have applied to production BEFORE its body was switched from
`ON CONFLICT (customer_code) DO NOTHING` to a pair-level NOT EXISTS guard. In
that case, rows like (300-D093, "Deluxe Home Centre Sdn Bhd (A/C I)") were
silently skipped because a different name already owned the 300-D093 code.

This migration re-runs the pair-based seed + pair-based FK re-point against
the current orders table. Idempotent — every statement gates on missing /
mismatched state so re-runs converge.

Revision ID: 221_resync_customer_pairs
Revises: 220_customers_composite_unique
Create Date: 2026-06-01
"""
from __future__ import annotations

from alembic import op


revision = "221_resync_customer_pairs"
down_revision = "220_customers_composite_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Seed missing customers by PAIR. The NOT EXISTS guard matches both
    #    code AND name (case + whitespace normalized) so a code that already
    #    exists with a different name no longer blocks the new (code, name)
    #    row from being created.
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
              AND lower(btrim(c.customer_code)) = lower(
                  COALESCE(
                      NULLIF(btrim(src.debtor_code), ''),
                      'DBR-' || substr(md5(lower(btrim(src.debtor_name))), 1, 10)
                  )
              )
        );
        """
    )

    # 2. Re-point orders.customer_id to the matching (code, name) PAIR. Falls
    #    back to name-only + deterministic DBR-hash code for rows missing
    #    debtor_code so legacy orders still resolve. Skips rows already
    #    correctly pointed.
    op.execute(
        """
        UPDATE orders o
        SET customer_id = c.id
        FROM customers c
        WHERE o.debtor_name IS NOT NULL
          AND lower(btrim(o.debtor_name)) = lower(btrim(c.customer_name))
          AND (
              (
                  o.debtor_code IS NOT NULL
                  AND btrim(o.debtor_code) <> ''
                  AND lower(btrim(o.debtor_code)) = lower(btrim(c.customer_code))
              )
              OR (
                  (o.debtor_code IS NULL OR btrim(o.debtor_code) = '')
                  AND lower(btrim(c.customer_code)) = 'dbr-' || substr(md5(lower(btrim(o.debtor_name))), 1, 10)
              )
          )
          AND (o.customer_id IS DISTINCT FROM c.id);
        """
    )


def downgrade() -> None:
    # Non-reversible — we cannot tell which rows were seeded here vs created
    # via normal application flow.
    pass
