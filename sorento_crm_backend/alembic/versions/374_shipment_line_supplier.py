"""Whose lines these are: a supplier on inbound_shipment_lines, and volume/remarks.

One container carries several factories' goods, and a packing list arrives per
factory. `uk_inbound_shipment_lines_shipment_product` said one row per product
per shipment, so the second factory's upload for the same container REPLACED the
first factory's lines - the data-loss bug this revision exists to end.

Line identity becomes `(shipment_id, product_id, supplier_id)`. A NULL supplier
is a key of its own rather than "matches nothing", which is what `NULLS NOT
DISTINCT` (PG 15+; local 17, CI 16, prod 15) buys: the legacy n8n PDF path,
which names no supplier, keeps behaving as it always did instead of being able
to insert the same product twice.

`supplier_id` is backfilled from the header, so every line that already exists is
owned by the supplier its shipment already names - not left NULL to be guessed at
later. `cbm` and `remarks` are two facts the workbook reader already parsed and
threw away; the consolidated packing list needs volume for the company split and
the supplier's own remark beside the derived ones.

This revision also rejoins the graph: two heads existed
(`373_merge_372_flyer_specs`, `373_merge_media_into_main`), so `down_revision` is
both of them and `alembic upgrade head` has one target again.

Revision ID: 374_shipment_line_supplier
Revises: 373_merge_372_flyer_specs, 373_merge_media_into_main
Create Date: 2026-08-17

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic. 26 characters, within the varchar(32)
# an `alembic stamp` provisions (tests/test_alembic_revision_ids.py).
revision = "374_shipment_line_supplier"
down_revision = (
    "373_merge_372_flyer_specs",
    "373_merge_media_into_main",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inbound_shipment_lines",
        sa.Column("supplier_id", postgresql.UUID(as_uuid=False), nullable=True),
    )
    op.add_column(
        "inbound_shipment_lines",
        sa.Column("cbm", sa.Numeric(12, 4), nullable=True),
    )
    op.add_column(
        "inbound_shipment_lines",
        sa.Column("remarks", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_inbound_shipment_lines_supplier_id",
        "inbound_shipment_lines",
        "suppliers",
        ["supplier_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_inbound_shipment_lines_supplier_id",
        "inbound_shipment_lines",
        ["supplier_id"],
    )

    # Backfill: a line belongs to the supplier its shipment already names. JOIN-based
    # "set where it disagrees" rather than "set where NULL" so a re-run corrects a
    # previous bad run instead of skipping it.
    op.execute(
        sa.text(
            """
UPDATE inbound_shipment_lines l
SET supplier_id = s.supplier_id
FROM inbound_shipments s
WHERE l.shipment_id = s.id
  AND s.supplier_id IS NOT NULL
  AND l.supplier_id IS DISTINCT FROM s.supplier_id
            """
        )
    )

    op.drop_constraint(
        "uk_inbound_shipment_lines_shipment_product",
        "inbound_shipment_lines",
        type_="unique",
    )
    # NULLS NOT DISTINCT so a supplier-less line (the n8n PDF path) is still one row
    # per product, exactly as the dropped constraint made it. Written as raw DDL
    # because alembic's op.create_index has no flag for it.
    op.execute(
        "CREATE UNIQUE INDEX uk_inbound_shipment_lines_ship_prod_sup "
        "ON inbound_shipment_lines (shipment_id, product_id, supplier_id) "
        "NULLS NOT DISTINCT"
    )


def downgrade() -> None:
    op.drop_index("uk_inbound_shipment_lines_ship_prod_sup", table_name="inbound_shipment_lines")

    # Going back to one row per (shipment, product) means the per-supplier rows this
    # revision made possible have to be merged, the way 055 merged the duplicates it
    # found: quantities summed into the oldest row, the rest deleted. The supplier of the
    # merged row is whichever the oldest carried, and the other one is lost - which is the
    # honest cost of going back to a schema that cannot express it.
    #
    # Unlike 055 there is no allocation to reassign: `spo_allocations` pointed at a line
    # by `inbound_shipment_lines_id` then, and migration 126 dropped that column. An
    # allocation is keyed by (shipment, product) now, so merging lines does not orphan
    # one.
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
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
            """
        )
    )
    conn.execute(
        sa.text(
            """
DELETE FROM inbound_shipment_lines l
USING (
    SELECT shipment_id, product_id,
           (array_agg(id ORDER BY created_at, id))[1] AS keep_id
    FROM inbound_shipment_lines
    GROUP BY shipment_id, product_id
    HAVING COUNT(*) > 1
) agg
WHERE l.shipment_id = agg.shipment_id AND l.product_id = agg.product_id AND l.id != agg.keep_id
            """
        )
    )

    op.create_unique_constraint(
        "uk_inbound_shipment_lines_shipment_product",
        "inbound_shipment_lines",
        ["shipment_id", "product_id"],
    )
    op.drop_index("ix_inbound_shipment_lines_supplier_id", table_name="inbound_shipment_lines")
    op.drop_constraint(
        "fk_inbound_shipment_lines_supplier_id",
        "inbound_shipment_lines",
        type_="foreignkey",
    )
    op.drop_column("inbound_shipment_lines", "remarks")
    op.drop_column("inbound_shipment_lines", "cbm")
    op.drop_column("inbound_shipment_lines", "supplier_id")
