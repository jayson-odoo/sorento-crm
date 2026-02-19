"""Re-run product_code deduplication and ensure unique constraint

Handles cases where migration 048 was not applied or duplicates were reintroduced.
Idempotent: safe to run even if no duplicates exist.
Keeps oldest product per code (by created_at, id), reassigns RESTRICT FKs, deletes rest.

Revision ID: 049_rerun_product_dedup
Revises: 048_product_code_unique
Create Date: 2026-02-19

"""
from alembic import op
import sqlalchemy as sa


revision = "049_rerun_product_dedup"
down_revision = "048_product_code_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()

    # 1. Re-run deduplication: keep oldest (by created_at, id) per product_code, delete rest
    connection.execute(sa.text("""
        DO $$
        DECLARE
            dup RECORD;
            survivor_id UUID;
            dup_ids UUID[];
        BEGIN
            FOR dup IN
                SELECT product_code,
                       array_agg(id ORDER BY created_at ASC, id ASC) AS ids
                FROM products
                GROUP BY product_code
                HAVING count(*) > 1
            LOOP
                survivor_id := dup.ids[1];
                dup_ids := dup.ids[2:array_length(dup.ids, 1)];

                IF array_length(dup_ids, 1) IS NOT NULL THEN
                    UPDATE inbound_shipment_lines
                    SET product_id = survivor_id
                    WHERE product_id = ANY(dup_ids);

                    UPDATE picking_lines
                    SET product_id = survivor_id
                    WHERE product_id = ANY(dup_ids);

                    DELETE FROM products
                    WHERE id = ANY(dup_ids);
                END IF;
            END LOOP;
        END $$;
    """))

    # 2. Ensure UNIQUE constraint exists on product_code
    connection.execute(sa.text("DROP INDEX IF EXISTS ix_products_product_code"))
    result = connection.execute(sa.text("""
        SELECT 1 FROM pg_constraint c
        JOIN pg_attribute a ON a.attnum = ANY(c.conkey) AND a.attrelid = c.conrelid
        WHERE c.conrelid = 'products'::regclass
          AND c.contype = 'u'
          AND a.attname = 'product_code'
    """))
    if result.fetchone() is None:
        op.create_unique_constraint(
            "products_product_code_key",
            "products",
            ["product_code"],
        )


def downgrade() -> None:
    # No-op: 048's downgrade already handles constraint removal.
    # This migration doesn't add new schema; it just re-runs data cleanup.
    pass
