"""AutoCount GRN ingest S17: Decimal picking quantities + supplier on header.

1a — widen the picking quantity columns Integer -> Numeric(15,4) so AutoCount's
fractional quantities ("2.5") stop truncating. The generated discrepancy column
depends on two of them, so drop + recreate it around the base-column alters
(Postgres can't ALTER TYPE a column a generated column reads).

1b — add supplier_code + supplier_id to picking_headers (captured-if-resolvable;
a miss keeps the code with supplier_id NULL).

Idempotent (existence-checked) so a create_all DB that already has the widened
types / new columns is a no-op. Chains on the autocount head (309).

Revision ID: 310_autocount_grn_decimal_supplier
Revises: 309_autocount_so_po_pricing
"""
from alembic import op
import sqlalchemy as sa


revision = "310_autocount_grn_decimal_supplier"
down_revision = "309_autocount_so_po_pricing"
branch_labels = None
depends_on = None

_UUID = sa.dialects.postgresql.UUID

# scm.receipt_lead_v reads picking_lines.qty_accepted / qty_rejected, so it must
# be dropped before ALTER TYPE and recreated after. Definition kept verbatim.
_RECEIPT_LEAD_V = """
CREATE VIEW scm.receipt_lead_v AS
 SELECT po.id AS po_id,
    po.supplier_id,
    pl.product_id,
    po.issue_date,
    ph.picking_date AS receipt_date,
    ph.picking_date - po.issue_date AS lead_days,
    ph.inspection_status,
    pl.qty_accepted,
    pl.qty_rejected
   FROM picking_headers ph
     JOIN picking_lines pl ON pl.picking_header_id = ph.id
     JOIN purchase_order_lines pol ON pol.id = pl.po_line_id
     JOIN purchase_orders po ON po.id = pol.purchase_order_id
  WHERE ph.picking_type::text = 'goods_received'::text
    AND ph.source_entity_type::text = 'purchase_order'::text
"""


def _view_exists(conn) -> bool:
    return bool(
        conn.execute(
            sa.text(
                "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE c.relkind='v' AND n.nspname='scm' AND c.relname='receipt_lead_v'"
            )
        ).scalar()
    )


def _col(conn, table: str, name: str):
    return next((c for c in sa.inspect(conn).get_columns(table) if c["name"] == name), None)


def _is_numeric(conn, table: str, name: str) -> bool:
    c = _col(conn, table, name)
    return bool(c) and isinstance(c["type"], sa.Numeric) and not isinstance(c["type"], sa.Integer)


def upgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())

    # --- 1a: widen picking_lines quantities -------------------------------
    if "picking_lines" in tables and not _is_numeric(conn, "picking_lines", "quantity_expected"):
        # scm.receipt_lead_v reads qty_accepted/qty_rejected -> drop it first.
        view_present = _view_exists(conn)
        if view_present:
            op.execute("DROP VIEW scm.receipt_lead_v")
        # Drop the generated discrepancy (depends on expected/picked).
        op.execute("ALTER TABLE picking_lines DROP COLUMN IF EXISTS quantity_discrepancy")
        for c in ("qty_accepted", "qty_rejected", "quantity_expected", "quantity_picked"):
            op.execute(
                f"ALTER TABLE picking_lines ALTER COLUMN {c} TYPE numeric(15,4) USING {c}::numeric"
            )
        op.execute(
            "ALTER TABLE picking_lines ADD COLUMN quantity_discrepancy numeric(15,4) "
            "GENERATED ALWAYS AS (quantity_expected - quantity_picked) STORED NOT NULL"
        )
        if view_present:
            op.execute(_RECEIPT_LEAD_V)

    # --- 1a: widen picking_headers aggregate totals -----------------------
    if "picking_headers" in tables:
        for c in ("total_items_picked", "total_items_discrepancy"):
            if not _is_numeric(conn, "picking_headers", c):
                op.execute(
                    f"ALTER TABLE picking_headers ALTER COLUMN {c} TYPE numeric(15,4) USING {c}::numeric"
                )

    # --- 1b: supplier on the picking header -------------------------------
    if "picking_headers" in tables:
        existing = {c["name"] for c in sa.inspect(conn).get_columns("picking_headers")}
        if "supplier_code" not in existing:
            op.add_column("picking_headers", sa.Column("supplier_code", sa.String(50), nullable=True))
        if "supplier_id" not in existing:
            op.add_column(
                "picking_headers",
                sa.Column("supplier_id", _UUID(as_uuid=False),
                          sa.ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True),
            )


def downgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())
    if "picking_headers" in tables:
        existing = {c["name"] for c in sa.inspect(conn).get_columns("picking_headers")}
        if "supplier_id" in existing:
            op.drop_column("picking_headers", "supplier_id")
        if "supplier_code" in existing:
            op.drop_column("picking_headers", "supplier_code")
    if "picking_lines" in tables and _is_numeric(conn, "picking_lines", "quantity_expected"):
        view_present = _view_exists(conn)
        if view_present:
            op.execute("DROP VIEW scm.receipt_lead_v")
        op.execute("ALTER TABLE picking_lines DROP COLUMN IF EXISTS quantity_discrepancy")
        for c in ("qty_accepted", "qty_rejected", "quantity_expected", "quantity_picked"):
            op.execute(
                f"ALTER TABLE picking_lines ALTER COLUMN {c} TYPE integer USING round({c})::integer"
            )
        op.execute(
            "ALTER TABLE picking_lines ADD COLUMN quantity_discrepancy integer "
            "GENERATED ALWAYS AS (quantity_expected - quantity_picked) STORED NOT NULL"
        )
        if view_present:
            op.execute(_RECEIPT_LEAD_V)
