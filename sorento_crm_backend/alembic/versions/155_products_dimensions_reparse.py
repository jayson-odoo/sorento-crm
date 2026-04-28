"""Re-parse and overwrite products.dimensions_length/width/height from descriptions.

Revision ID: 155_products_dimensions_reparse
Revises: 154_products_dimensions_backfill

Migration 154 ran with an earlier parser that mis-sliced 4-tuple descriptions like
'1000×500×200×0.7MM' (took the last 3 numbers). The parser has since been fixed to take
the first 3. This migration re-parses every product description and overwrites the
dimension columns whenever the parser yields a non-empty triplet.

Overwrite (not preserve) is intentional: products were just bulk-imported and dimensions
came from descriptions in the first place; no manual edits to protect at this point.
"""

from alembic import op


revision = "155_products_dimensions_reparse"
down_revision = "154_products_dimensions_backfill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.services.product_service import parse_dimensions_from_description

    conn = op.get_bind()
    rows = conn.exec_driver_sql(
        "SELECT id, description FROM products WHERE description IS NOT NULL AND description <> ''"
    ).fetchall()

    updated = 0
    for r in rows:
        pid, desc = r[0], r[1]
        parsed_l, parsed_w, parsed_h = parse_dimensions_from_description(desc)
        if parsed_l is None and parsed_w is None and parsed_h is None:
            continue

        conn.exec_driver_sql(
            "UPDATE products SET dimensions_length = %s, dimensions_width = %s, dimensions_height = %s "
            "WHERE id = %s",
            (
                str(parsed_l) if parsed_l is not None else None,
                str(parsed_w) if parsed_w is not None else None,
                str(parsed_h) if parsed_h is not None else None,
                pid,
            ),
        )
        updated += 1

    print(f"[155_products_dimensions_reparse] re-parsed dimensions for {updated} products")


def downgrade() -> None:
    pass
