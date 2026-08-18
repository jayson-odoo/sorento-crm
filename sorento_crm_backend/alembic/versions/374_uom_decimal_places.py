"""Canonical UOM divisibility: `units_of_measure.decimal_places` (front planning 6.4).

How finely a unit may be counted, `0..4`. `EA` is 0 and refuses `2.5`; `kg` at 3 accepts
it. The SCM product plan freezes this per run (`order_summary_row.uom_decimal_places`) so
a later edit here cannot move a run that is already calculated.

Three steps, in this order, because the backfill can only see NULL as "not classified
yet":

1. add the column NULLABLE;
2. backfill it with the FROZEN copy below - classification reads the unit NAME only (never
   the code, so `EA` named `Kilogram` is a measure unit), a measure name takes the
   greatest fractional scale actually observed in `order_lines.quantity`,
   `sales_order_lines.qty_ordered` / `qty_delivered` / `qty_required` and
   `purchase_order_lines.qty_ordered` / `qty_received` after trailing zeroes are dropped,
   capped at 4, and every count or unrecognised name takes 0. **No quantity row is
   rewritten**;
3. make it NOT NULL with server default 0 and the `0..4` CHECK.

**Why the backfill is copied here rather than imported.** The live twin is
`app.services.uom_decimal_places`, which the service layer still owns and which an admin
re-runs to re-value a row sitting on the 0 fallback. This migration must NOT import it: a
migration describes a point in history, and importing live code makes a from-zero replay
run TOMORROW's rule against YESTERDAY's schema. That is the exact outage migrations 340 and
346 recorded (`tests/scm/test_committed_v_migration_chain.py`), where an imported view body
referenced a column a later migration adds. The name lists, the observed-scale SQL and the
"NULL or 0" predicate below are therefore a verbatim snapshot as of this revision; when the
service's rule changes, the fix is a NEW migration, never an edit to this one.

**Behaviour on a row the backfill cannot value** - an unknown name, or a measure unit with
no transactions to measure - **is 0**, and that is also what step 3's default gives any row
inserted afterwards. So the rollout fallback survives: nothing is left NULL, nothing is
guessed, and a unit that genuinely needs decimals is corrected by an admin edit (or by
re-running the backfill, which re-values a row still sitting on the 0 fallback and leaves a
carried value alone).

Empty database is a supported case: the backfill selects no rows and writes nothing, so a
fresh `alembic upgrade head` passes through it untouched.

Revision ID: 374_uom_decimal_places
Revises: 373_merge_scm_stage0_1a
Create Date: 2026-08-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "374_uom_decimal_places"
down_revision = "373_merge_scm_stage0_1a"
branch_labels = None
depends_on = None


# --------------------------------------------------------------------------- #
# The backfill AS OF THIS REVISION. Live twin: app/services/uom_decimal_places.py
# (which keeps running for admin re-runs). Frozen here on purpose - see the module
# docstring. Do not edit; write a new migration instead.
# --------------------------------------------------------------------------- #

_COUNT_NAMES_374 = frozenset({
    "ea", "each", "piece", "pieces", "unit", "units", "pc", "pcs", "set", "sets",
})

_MEASURE_NAMES_374 = frozenset({
    "kg", "kilogram", "kilograms", "g", "gram", "grams",
    "m", "meter", "meters", "metre", "metres",
    "cm", "centimeter", "centimeters", "centimetre", "centimetres",
    "l", "liter", "liters", "litre", "litres",
    "ml", "milliliter", "milliliters", "millilitre", "millilitres",
    "m2", "m²", "square meter", "square meters", "square metre", "square metres",
    "m3", "m³", "cubic meter", "cubic meters", "cubic metre", "cubic metres",
})

_MAX_DECIMAL_PLACES_374 = 4
_DEFAULT_DECIMAL_PLACES_374 = 0

_OBSERVED_SCALE_SQL_374 = """
    WITH q AS (
        SELECT p.base_uom_id AS uom_id, ol.quantity AS qty
        FROM order_lines ol JOIN products p ON p.id = ol.product_id
        UNION ALL
        SELECT p.base_uom_id, sol.qty_ordered
        FROM sales_order_lines sol JOIN products p ON p.id = sol.product_id
        UNION ALL
        SELECT p.base_uom_id, sol.qty_delivered
        FROM sales_order_lines sol JOIN products p ON p.id = sol.product_id
        UNION ALL
        SELECT p.base_uom_id, sol.qty_required
        FROM sales_order_lines sol JOIN products p ON p.id = sol.product_id
        UNION ALL
        SELECT p.base_uom_id, pol.qty_ordered
        FROM purchase_order_lines pol JOIN products p ON p.id = pol.product_id
        UNION ALL
        SELECT p.base_uom_id, pol.qty_received
        FROM purchase_order_lines pol JOIN products p ON p.id = pol.product_id
    )
    SELECT uom_id::text AS uom_id,
           MAX(length(split_part(rtrim(qty::text, '0'), '.', 2))) AS scale
    FROM q
    WHERE qty IS NOT NULL
      AND uom_id IS NOT NULL
      AND uom_id::text = ANY(:uom_ids)
    GROUP BY uom_id
"""


def _classify_374(name):
    key = (name or "").strip().lower()
    if key in _COUNT_NAMES_374:
        return "count"
    if key in _MEASURE_NAMES_374:
        return "measure"
    return "unknown"


def _backfill_374(bind) -> int:
    """Value every unclassified unit. "Unclassified" is NULL (every row while this
    migration holds the column nullable) or 0 (the rollout fallback); a carried value
    above 0 is never overwritten. Empty database writes nothing."""
    rows = bind.execute(text(
        "SELECT id::text AS id, uom_name FROM units_of_measure "
        "WHERE decimal_places IS NULL OR decimal_places = 0"
    )).mappings().all()
    if not rows:
        return 0

    measure_ids = [r["id"] for r in rows if _classify_374(r["uom_name"]) == "measure"]
    observed = {}
    if measure_ids:
        for row in bind.execute(
            text(_OBSERVED_SCALE_SQL_374), {"uom_ids": measure_ids}
        ).mappings().all():
            observed[row["uom_id"]] = min(
                int(row["scale"] or 0), _MAX_DECIMAL_PLACES_374)

    written = 0
    for r in rows:
        if _classify_374(r["uom_name"]) == "measure":
            value = observed.get(r["id"], _DEFAULT_DECIMAL_PLACES_374)
        else:
            # A count name and an unrecognised name are the same answer: whole units.
            value = _DEFAULT_DECIMAL_PLACES_374
        bind.execute(
            text("UPDATE units_of_measure SET decimal_places = :v WHERE id::text = :id"),
            {"v": value, "id": r["id"]},
        )
        written += 1
    return written


def upgrade() -> None:
    op.add_column(
        "units_of_measure",
        sa.Column("decimal_places", sa.SmallInteger(), nullable=True),
    )

    _backfill_374(op.get_bind())

    op.execute(
        "UPDATE units_of_measure SET decimal_places = 0 WHERE decimal_places IS NULL"
    )
    op.alter_column(
        "units_of_measure",
        "decimal_places",
        existing_type=sa.SmallInteger(),
        nullable=False,
        server_default=sa.text("0"),
    )
    op.create_check_constraint(
        "ck_units_of_measure_decimal_places",
        "units_of_measure",
        "decimal_places >= 0 AND decimal_places <= 4",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_units_of_measure_decimal_places", "units_of_measure", type_="check"
    )
    op.drop_column("units_of_measure", "decimal_places")
