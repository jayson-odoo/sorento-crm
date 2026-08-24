"""Backfill products.dimensions_length/width/height from description LxWxH pattern.

Revision ID: 154_products_dimensions_backfill
Revises: 153_products_currency_default_myr

Only fills columns that are currently NULL - preserves any existing manually-set values.
Source convention: descriptions like 'CABANA HONEYCOMB KITCHEN SINK (650x450x210MM)' use
length × width × height in mm/cm/m.
"""

from alembic import op
from decimal import Decimal


revision = "154_products_dimensions_backfill"
down_revision = "153_products_currency_default_myr"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.services.product_service import parse_dimensions_from_description

    conn = op.get_bind()
    rows = conn.exec_driver_sql(
        "SELECT id, description, dimensions_length, dimensions_width, dimensions_height "
        "FROM products WHERE description IS NOT NULL AND description <> ''"
    ).fetchall()

    updated = 0
    for r in rows:
        # SQLAlchemy Row supports index access; columns selected in fixed order above.
        pid, desc, cur_l, cur_w, cur_h = r[0], r[1], r[2], r[3], r[4]
        if cur_l is not None and cur_w is not None and cur_h is not None:
            continue
        parsed_l, parsed_w, parsed_h = parse_dimensions_from_description(desc)
        if parsed_l is None and parsed_w is None and parsed_h is None:
            continue

        new_l = cur_l if cur_l is not None else parsed_l
        new_w = cur_w if cur_w is not None else parsed_w
        new_h = cur_h if cur_h is not None else parsed_h
        if (new_l, new_w, new_h) == (cur_l, cur_w, cur_h):
            continue

        conn.exec_driver_sql(
            "UPDATE products SET dimensions_length = %s, dimensions_width = %s, dimensions_height = %s "
            "WHERE id = %s",
            (
                str(new_l) if new_l is not None else None,
                str(new_w) if new_w is not None else None,
                str(new_h) if new_h is not None else None,
                pid,
            ),
        )
        updated += 1

    print(f"[154_products_dimensions_backfill] backfilled dimensions for {updated} products")


def downgrade() -> None:
    # Backfill is non-destructive (only filled NULLs). No safe automatic reversal.
    pass
