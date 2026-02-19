"""Unique (shipment_id, product_id) on inbound_shipment_lines.

One row per product per inbound shipment. Existing duplicates are merged:
quantity_shipped and cartons_count are summed. SPO allocations pointing to
merged-away lines are reassigned to the kept line.

Revision ID: 055_inbound_shipment_line_unique_product
Revises: 054_spo_spo_product_wh_unique
Create Date: 2026-02-10

"""
from alembic import op
import sqlalchemy as sa


revision = "055_inbound_shipment_line_unique"
down_revision = "054_spo_spo_product_wh_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Use (array_agg(id ORDER BY created_at, id))[1] since PostgreSQL has no MIN(uuid)
    # 1. Update kept rows (first by created_at, id per shipment_id, product_id) with merged totals
    conn.execute(
        sa.text("""
UPDATE inbound_shipment_lines l
SET quantity_shipped = agg.total_qty, cartons_count = agg.total_cartons
FROM (
    SELECT shipment_id, product_id,
           (array_agg(id ORDER BY created_at, id))[1] AS keep_id,
           SUM(quantity_shipped) AS total_qty, SUM(cartons_count) AS total_cartons
    FROM inbound_shipment_lines
    GROUP BY shipment_id, product_id
    HAVING COUNT(*) > 1
) agg
WHERE l.shipment_id = agg.shipment_id AND l.product_id = agg.product_id AND l.id = agg.keep_id
        """)
    )

    # 2. Reassign spo_allocations from duplicate lines to the kept line
    conn.execute(
        sa.text("""
UPDATE spo_allocations sa
SET inbound_shipment_lines_id = map.keep_id
FROM (
    SELECT l.id AS line_id, agg.keep_id
    FROM inbound_shipment_lines l
    JOIN (
        SELECT shipment_id, product_id,
               (array_agg(id ORDER BY created_at, id))[1] AS keep_id
        FROM inbound_shipment_lines
        GROUP BY shipment_id, product_id
        HAVING COUNT(*) > 1
    ) agg ON l.shipment_id = agg.shipment_id AND l.product_id = agg.product_id
    WHERE l.id != agg.keep_id
) map
WHERE sa.inbound_shipment_lines_id = map.line_id
        """)
    )

    # 3. Delete duplicate lines (keep only one per shipment_id, product_id)
    conn.execute(
        sa.text("""
DELETE FROM inbound_shipment_lines l
USING (
    SELECT shipment_id, product_id,
           (array_agg(id ORDER BY created_at, id))[1] AS keep_id
    FROM inbound_shipment_lines
    GROUP BY shipment_id, product_id
    HAVING COUNT(*) > 1
) agg
WHERE l.shipment_id = agg.shipment_id AND l.product_id = agg.product_id AND l.id != agg.keep_id
        """)
    )

    # 4. Add unique constraint
    op.create_unique_constraint(
        "uk_inbound_shipment_lines_shipment_product",
        "inbound_shipment_lines",
        ["shipment_id", "product_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uk_inbound_shipment_lines_shipment_product",
        "inbound_shipment_lines",
        type_="unique",
    )
