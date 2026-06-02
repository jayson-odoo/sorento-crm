"""Re-sync customers + transporters from orders (catch-up backfill).

Migrations 200 / 206 / 207 seeded master rows + FKs once. Orders created after
those migrations bypassed the seed flow until `OrderService.create_order` /
`update_order` learned to upsert inline. This migration re-runs the same
idempotent INSERT / UPDATE blocks so existing rows are aligned before the new
inline upsert takes over.

Safe to run multiple times — every statement is gated on missing / mismatched
state so re-runs are no-ops once the system converges.

Revision ID: 219_resync_orders_customer_transporter
Revises: 218_attachment_type_field_linkage
Create Date: 2026-06-01
"""
from __future__ import annotations

from alembic import op


revision = "219_resync_orders_customer_transporter"
down_revision = "218_attachment_type_field_linkage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Seed missing transporters from distinct orders.transporter.
    op.execute(
        """
        INSERT INTO transporters (id, code, name, normalized_name, created_at)
        SELECT
            gen_random_uuid(),
            btrim(src.transporter) AS code,
            btrim(src.transporter) AS name,
            lower(btrim(src.transporter)) AS normalized_name,
            now()
        FROM (
            SELECT DISTINCT transporter
            FROM orders
            WHERE transporter IS NOT NULL AND btrim(transporter) <> ''
        ) src
        ON CONFLICT (normalized_name) DO NOTHING;
        """
    )

    # 2. Re-point orders.transporter_id where text matches a transporter row
    #    but the FK is NULL or stale.
    op.execute(
        """
        UPDATE orders o
        SET transporter_id = t.id
        FROM transporters t
        WHERE o.transporter IS NOT NULL
          AND lower(btrim(o.transporter)) = t.normalized_name
          AND (o.transporter_id IS DISTINCT FROM t.id);
        """
    )

    # 3. Seed missing customers from distinct (debtor_code, debtor_name) PAIRS.
    #    Pair-level dedup so a single Sage code (e.g. "300-D093") that hosts
    #    multiple distinct trading names ("Deluxe Home Center (KTN)", "Deluxe
    #    Home Center AC (I)") produces one customers row per name. NOT EXISTS
    #    gate is also pair-level so re-runs are no-ops.
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

    # 4. Re-point orders.customer_id by the PAIR — matches the pair-level
    #    dedup above. Falls back to debtor_name-only match when the order has
    #    no debtor_code so legacy rows still get an FK.
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
    # Non-reversible: we cannot distinguish rows seeded here from rows created
    # via normal application flow. Leave master + FKs in place.
    pass
