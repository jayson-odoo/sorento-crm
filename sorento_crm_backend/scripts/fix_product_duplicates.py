#!/usr/bin/env python3
"""
Standalone script to fix duplicate product_code values: trim spaces, deduplicate, add unique constraint.

Run from sorento_crm_backend/ with: python scripts/fix_product_duplicates.py

Uses the same DB connection as the app (from .env).
Handles cases like "PACKAGING BOX" vs "PACKAGING BOX " (trailing space).
"""

import os
import sys

# Add parent to path so we can import app config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database import engine


def main():
    with engine.connect() as conn:
        # 1. Drop unique constraint so TRIM won't violate it (e.g. "X" and "X " both trim to "X")
        conn.execute(text("ALTER TABLE products DROP CONSTRAINT IF EXISTS products_product_code_key"))
        conn.commit()

        # 2. Trim product_code for all products (remove leading/trailing spaces)
        conn.execute(text("""
            UPDATE products SET product_code = TRIM(product_code) WHERE product_code != TRIM(product_code)
        """))
        conn.commit()
        print("Trimmed product_code for all products.")

        # 3. Show duplicates before fix (after trim)
        result = conn.execute(text("""
            SELECT product_code, count(*) as cnt
            FROM products
            GROUP BY product_code
            HAVING count(*) > 1
        """))
        dups = list(result.fetchall())
        if dups:
            print(f"Found {len(dups)} duplicate product_code(s):")
            for row in dups:
                print(f"  - {row[0]}: {row[1]} rows")
        else:
            print("No duplicates found.")

        # 4. Deduplicate: keep oldest per product_code, reassign RESTRICT FKs, delete rest
        conn.execute(text("""
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
        conn.commit()
        print("Deduplication completed.")

        # 5. Add unique constraint if missing
        result = conn.execute(text("""
            SELECT 1 FROM pg_constraint c
            JOIN pg_attribute a ON a.attnum = ANY(c.conkey) AND a.attrelid = c.conrelid
            WHERE c.conrelid = 'products'::regclass AND c.contype = 'u' AND a.attname = 'product_code'
        """))
        if result.fetchone() is None:
            conn.execute(text("DROP INDEX IF EXISTS ix_products_product_code"))
            conn.execute(text("ALTER TABLE products ADD CONSTRAINT products_product_code_key UNIQUE (product_code)"))
            conn.commit()
            print("Unique constraint added.")
        else:
            print("Unique constraint already exists.")


if __name__ == "__main__":
    main()
