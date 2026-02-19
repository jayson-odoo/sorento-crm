"""Trim product_code (remove leading/trailing spaces) and deduplicate

Trims all product_code values in products, then runs deduplication (keep oldest per
trimmed code), reassigns RESTRICT FKs, deletes rest. Ensures unique constraint.
Prevents "PACKAGING BOX" vs "PACKAGING BOX " from being treated as distinct.

Revision ID: 050_trim_product_code
Revises: 049_rerun_product_dedup
Create Date: 2026-02-19

"""
from alembic import op
import sqlalchemy as sa


revision = "050_trim_product_code"
down_revision = "049_rerun_product_dedup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()

    # 0. Drop unique constraint so TRIM won't violate it (e.g. "X" and "X " both trim to "X")
    result = connection.execute(sa.text("""
        SELECT 1 FROM pg_constraint WHERE conname = 'products_product_code_key' AND conrelid = 'products'::regclass
    """))
    if result.fetchone() is not None:
        op.drop_constraint("products_product_code_key", "products", type_="unique")

    # 1. Trim product_code for all products (remove leading/trailing spaces)
    connection.execute(sa.text("""
        UPDATE products
        SET product_code = TRIM(product_code)
        WHERE product_code != TRIM(product_code);
    """))

    # 2. Deduplicate: keep oldest (by created_at, id) per product_code, delete rest
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
                    UPDATE inbound_shipment_lines SET product_id = survivor_id WHERE product_id = ANY(dup_ids);
                    UPDATE picking_lines SET product_id = survivor_id WHERE product_id = ANY(dup_ids);
                    DELETE FROM products WHERE id = ANY(dup_ids);
                END IF;
            END LOOP;
        END $$;
    """))

    # 3. Ensure UNIQUE constraint exists on product_code
    connection.execute(sa.text("DROP INDEX IF EXISTS ix_products_product_code"))
    result = connection.execute(sa.text("""
        SELECT 1 FROM pg_constraint c
        JOIN pg_attribute a ON a.attnum = ANY(c.conkey) AND a.attrelid = c.conrelid
        WHERE c.conrelid = 'products'::regclass AND c.contype = 'u' AND a.attname = 'product_code'
    """))
    if result.fetchone() is None:
        op.create_unique_constraint(
            "products_product_code_key",
            "products",
            ["product_code"],
        )


def downgrade() -> None:
    pass
