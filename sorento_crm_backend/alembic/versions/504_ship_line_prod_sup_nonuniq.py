"""A supplier's own carton split is legal: two shipment lines of one (shipment, product,
supplier), not one.

S4 (AC-D1, `scm-supplier-documents-pi-first`): migration 374 made `(shipment_id, product_
id, supplier_id)` UNIQUE so a second factory's packing list could not overwrite the
first's - Kailu's own carton split (SRTSC14-GM shipping 50 pcs in one carton and 35 in
another, at different prices per carton) needs the SAME key to repeat, since convert now
writes one shipment line per MATCHED packing row rather than one per (product, supplier).
Dropped and recreated non-unique, still indexed for the lookups that filter on it.

Downgrade merges duplicates back exactly as 374's own downgrade does: quantities and
cartons summed into the oldest line, the rest deleted (no allocation to reassign -
`spo_allocations` is keyed by (shipment, product), never by line).

Revision ID: 504_ship_line_prod_sup_nonuniq
Revises: 503_scm_pi_seal_ref
Create Date: 2026-09-10
"""
from alembic import op
import sqlalchemy as sa

revision = "504_ship_line_prod_sup_nonuniq"
down_revision = "503_scm_pi_seal_ref"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("uk_inbound_shipment_lines_ship_prod_sup", table_name="inbound_shipment_lines")
    op.create_index(
        "ix_inbound_shipment_lines_ship_prod_sup",
        "inbound_shipment_lines",
        ["shipment_id", "product_id", "supplier_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_inbound_shipment_lines_ship_prod_sup", table_name="inbound_shipment_lines")

    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
UPDATE inbound_shipment_lines l
SET quantity_shipped = agg.total_qty, cartons_count = agg.total_cartons
FROM (
    SELECT shipment_id, product_id, supplier_id,
           (array_agg(id ORDER BY created_at, id))[1] AS keep_id,
           SUM(quantity_shipped) AS total_qty, SUM(cartons_count) AS total_cartons
    FROM inbound_shipment_lines
    GROUP BY shipment_id, product_id, supplier_id
    HAVING COUNT(*) > 1
) agg
WHERE l.shipment_id = agg.shipment_id AND l.product_id = agg.product_id
  AND l.supplier_id IS NOT DISTINCT FROM agg.supplier_id AND l.id = agg.keep_id
            """
        )
    )
    conn.execute(
        sa.text(
            """
DELETE FROM inbound_shipment_lines l
USING (
    SELECT shipment_id, product_id, supplier_id,
           (array_agg(id ORDER BY created_at, id))[1] AS keep_id
    FROM inbound_shipment_lines
    GROUP BY shipment_id, product_id, supplier_id
    HAVING COUNT(*) > 1
) agg
WHERE l.shipment_id = agg.shipment_id AND l.product_id = agg.product_id
  AND l.supplier_id IS NOT DISTINCT FROM agg.supplier_id AND l.id != agg.keep_id
            """
        )
    )
    op.execute(
        "CREATE UNIQUE INDEX uk_inbound_shipment_lines_ship_prod_sup "
        "ON inbound_shipment_lines (shipment_id, product_id, supplier_id) "
        "NULLS NOT DISTINCT"
    )
