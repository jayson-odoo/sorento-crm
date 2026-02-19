"""Enforce unique product_code and resolve existing duplicates

Resolves duplicate product_code values by keeping the oldest product per code
and deleting the rest. For duplicates with stock records, CASCADE deletion applies.
Reassigns inbound_shipment_lines and picking_lines (RESTRICT FK) to the survivor
before deleting duplicates. Adds UNIQUE constraint on products.product_code.

Revision ID: 048_product_code_unique
Revises: 047_smtp_settings
Create Date: 2026-02-17

"""
from alembic import op
import sqlalchemy as sa


revision = "048_product_code_unique"
down_revision = "047_smtp_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()

    # 1. Find duplicate product_codes and resolve: keep oldest (by created_at, id), delete rest
    # Reassign inbound_shipment_lines and picking_lines from duplicates to survivor before delete

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
                    -- Reassign inbound_shipment_lines from duplicates to survivor
                    UPDATE inbound_shipment_lines
                    SET product_id = survivor_id
                    WHERE product_id = ANY(dup_ids);

                    -- Reassign picking_lines from duplicates to survivor
                    UPDATE picking_lines
                    SET product_id = survivor_id
                    WHERE product_id = ANY(dup_ids);

                    -- Delete duplicate products (CASCADE handles stock, product_suppliers, etc.)
                    DELETE FROM products
                    WHERE id = ANY(dup_ids);
                END IF;
            END LOOP;
        END $$;
    """))

    # 2. Ensure UNIQUE constraint on product_code
    # Drop non-unique index if it exists (Prisma/Alembic may have ix_products_product_code)
    connection.execute(sa.text("DROP INDEX IF EXISTS ix_products_product_code"))
    # Check if any unique constraint on product_code already exists (Prisma uses Product_product_code_key)
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
    # Remove unique constraint - allow duplicates again (not recommended)
    connection = op.get_bind()
    result = connection.execute(sa.text("""
        SELECT 1 FROM pg_constraint
        WHERE conname = 'products_product_code_key' AND conrelid = 'products'::regclass
    """))
    if result.fetchone() is not None:
        op.drop_constraint("products_product_code_key", "products", type_="unique")
    op.create_index("ix_products_product_code", "products", ["product_code"], unique=False)
