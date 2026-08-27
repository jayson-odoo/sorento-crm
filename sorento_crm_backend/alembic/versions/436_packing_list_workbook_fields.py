"""The container packing list holds what the FSCU workbook prints: line measurements, container costs.

Revision ID: 436_pl_workbook_fields
Revises: 435_proforma_line_weights
Create Date: 2026-08-27

Ms Tee's own container workbook (`FSCU8103365.xlsx`, sheet `RMB`) is the specification, and
the CRM could not produce it because three sorts of fact had nowhere to live.

* **The container's own header.** `SEAL NO`, `SHIPPER` and the forwarder's `SO :` reference
  are printed at the top of every one of those sheets and existed nowhere on
  `inbound_shipments`. `CONSIGNEE`, `CHINA AGENT` (`china_forwarder`), `FREE DAYS` and
  `DELIVERY WAREHOUSE` already do, so they are not re-added here.
* **The container's costs.** Clearance, China freight and the insurance rate are TYPED per
  container (the captain's ruling, 27 Aug): the sheet apportions each of them between
  SORENTO and MOCHA by that company's share of the volume (clearance, freight) or of the
  amount (insurance), so all three are one number per container and not per line.
* **The line's measurements.** Material, pieces per carton and the carton's L / W / H are
  what the sheet computes `CTN QTY`, `CBM / CTN` and `TOTAL CBM` from, and the net / gross
  weight per carton are what it computes `TOTAL NW` / `TOTAL GW` from. They come off the
  supplier's proforma invoice or packing list and are editable on the packing list
  afterwards, so they are columns on the line rather than anything derived.

`inbound_shipment_lines.weight_per_carton` STAYS. It has been the only weight on the line
since the beginning and 0 rows would gain anything from being rewritten; the workbook reads
`gross_weight_per_carton` and falls back to it when the new column is null.

`scm.proforma_invoice_line` gains the same measurements MINUS the weights, which migration
435 added last night. The conversion to a draft packing list copies all of them across, so
the workbook is printable from a container that was never re-typed.

The columns are ALSO declared on the models (`app/models/procurement.py`, `app/models/scm.py`)
so a create_all database is the same shape as a migrated one, and `seed()` is importable for
the same reason 428's and 435's are: a CI database is built with create_all and never runs a
migration body.
"""
import sqlalchemy as sa
from alembic import op

revision = "436_pl_workbook_fields"
down_revision = "435_proforma_line_weights"
branch_labels = None
depends_on = None

DOC_TYPE = "proforma_invoice"

#: What the container itself carries. Everything else the sheet's header block prints is
#: already a column (container, ETD, ETA, consignee, china forwarder, free days, warehouse).
_SHIPMENT_COLUMNS = [
    ("seal_number", sa.String(50)),
    ("shipper", sa.String(255)),
    # The forwarder's own booking reference, printed as `SO :` and again as `订单号:` in the
    # footer. Named for what it is rather than "SO", which in this codebase is a sales order.
    ("forwarder_order_ref", sa.String(100)),
    ("clearance_cost", sa.Numeric(15, 2)),
    ("china_freight_cost", sa.Numeric(15, 2)),
    # A RATE, not a cost: the sheet multiplies the company's share of the amount by it.
    ("insurance_rate", sa.Numeric(15, 4)),
]

#: What a line carries. Lengths in centimetres because that is the unit the sheet's
#: `SIZE (CM)` block is in, and converting on the way in would make the stored number
#: disagree with the paper the supplier sent.
_LINE_COLUMNS = [
    ("material", sa.String(255)),
    # Numeric, not Integer: a factory that packs 2.5 sets per carton states 2.5, and
    # `CTN QTY = QTY / PCS PER CTN` has to divide by what it actually said.
    ("pcs_per_carton", sa.Numeric(15, 4)),
    ("carton_length_cm", sa.Numeric(10, 2)),
    ("carton_width_cm", sa.Numeric(10, 2)),
    ("carton_height_cm", sa.Numeric(10, 2)),
    ("net_weight_per_carton", sa.Numeric(10, 3)),
    ("gross_weight_per_carton", sa.Numeric(10, 3)),
]

#: The same measurements on the PROFORMA line, minus the weights (migration 435).
_PI_LINE_COLUMNS = [
    ("material", sa.String(255)),
    ("pcs_per_carton", sa.Numeric(15, 4)),
    ("carton_length_cm", sa.Numeric(10, 2)),
    ("carton_width_cm", sa.Numeric(10, 2)),
    ("carton_height_cm", sa.Numeric(10, 2)),
]

#: (field, alias) for the `proforma_invoice` doc type. One row per NORMALISED key -
#: `normalize_header` folds case, drops punctuation and whitespace, so `PCS / CTN` and
#: `PCS/CTN` are the same row and only one is seeded.
#:
#: `carton_size` is the COMBINED spelling: a supplier who prints one `外箱尺寸` cell writes
#: `62*53*40` in it, and the reader splits that into the three columns. Seeded beside the
#: separate L / W / H spellings rather than instead of them, because both shapes are real -
#: the FSCU sheet has three columns, the pre-loading list has one cell.
_ALIASES = [
    ("material", "材质"),
    ("material", "材料"),
    ("material", "MATERIAL"),
    ("pcs_per_carton", "装箱数"),
    ("pcs_per_carton", "装箱量"),
    ("pcs_per_carton", "每箱数量"),
    ("pcs_per_carton", "PCS / CTN"),
    ("pcs_per_carton", "PCS PER CTN"),
    ("carton_size", "外箱尺寸"),
    ("carton_size", "箱规"),
    ("carton_size", "外箱规格"),
    ("carton_size", "SIZE"),
    ("carton_size", "SIZE (CM)"),
    ("carton_size", "CARTON SIZE"),
    ("carton_length_cm", "外箱长"),
    ("carton_length_cm", "长"),
    ("carton_length_cm", "L"),
    ("carton_width_cm", "外箱宽"),
    ("carton_width_cm", "宽"),
    ("carton_width_cm", "W"),
    ("carton_height_cm", "外箱高"),
    ("carton_height_cm", "高"),
    ("carton_height_cm", "H"),
]


def seed(bind) -> int:
    """Insert the measurement aliases. Idempotent, importable - mirrors 435's `seed`."""
    inserted = 0
    for field, alias in _ALIASES:
        res = bind.execute(
            sa.text(
                """
                INSERT INTO import_field_alias (doc_type, field, alias, locale)
                VALUES (:d, :f, :a, 'en')
                ON CONFLICT (doc_type, field, alias) DO NOTHING
                """
            ),
            {"d": DOC_TYPE, "f": field, "a": alias},
        )
        inserted += res.rowcount or 0
    return inserted


def upgrade() -> None:
    for name, type_ in _SHIPMENT_COLUMNS:
        op.add_column("inbound_shipments", sa.Column(name, type_, nullable=True))
    for name, type_ in _LINE_COLUMNS:
        op.add_column("inbound_shipment_lines", sa.Column(name, type_, nullable=True))
    for name, type_ in _PI_LINE_COLUMNS:
        op.add_column(
            "proforma_invoice_line", sa.Column(name, type_, nullable=True), schema="scm"
        )
    seed(op.get_bind())


def downgrade() -> None:
    bind = op.get_bind()
    for field, alias in _ALIASES:
        bind.execute(
            sa.text(
                "DELETE FROM import_field_alias "
                "WHERE doc_type = :d AND field = :f AND alias = :a"
            ),
            {"d": DOC_TYPE, "f": field, "a": alias},
        )
    for name, _type in reversed(_PI_LINE_COLUMNS):
        op.drop_column("proforma_invoice_line", name, schema="scm")
    for name, _type in reversed(_LINE_COLUMNS):
        op.drop_column("inbound_shipment_lines", name)
    for name, _type in reversed(_SHIPMENT_COLUMNS):
        op.drop_column("inbound_shipments", name)
