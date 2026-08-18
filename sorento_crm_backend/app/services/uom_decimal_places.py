"""Canonical UOM divisibility: classify a unit's name, and backfill the column.

`units_of_measure.decimal_places` (front-planning plan section 6.4, AC-F12) says how
finely a unit may be counted: `EA` is 0 and refuses `2.5`, `kg` at 3 accepts it. It is a
property of the UNIT, never SCM arithmetic precision and never a planning knob, and it is
deliberately NOT inferred from `conversion_factor`.

Two rules the plan fixes and this module implements literally:

* **Classification reads the NAME only, never the code.** A unit coded `EA` but named
  `Kilogram` is a measure unit. Codes in the live master are abbreviations that were
  chosen for the printout, so reading them would get exactly the units that matter
  backwards.
* **A measure unit takes the greatest fractional scale ACTUALLY OBSERVED** in the
  transaction columns, after trailing zeroes are removed, capped at 4. Nothing is
  inferred from the column type (all six are `Numeric(15, 4)`, which would give every
  unit 4) and **no quantity row is ever rewritten** - this reads history, it does not
  correct it.

Everything else - a count name, an unknown name, a measure unit with no transactions -
resolves to `0`, which is also the rollout fallback for a row nobody has classified.

The module speaks raw SQL and imports no model, so the migration that adds the column can
call `backfill_uom_decimal_places` directly with its own connection, on a database whose
ORM metadata does not match the revision being applied.
"""
from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import text

#: Exact count aliases (plan 6.4). Indivisible: half of one is not a thing.
COUNT_NAMES: frozenset[str] = frozenset({
    "ea", "each", "piece", "pieces", "unit", "units", "pc", "pcs", "set", "sets",
})

#: Exact measure aliases (plan 6.4). Divisible, so their scale is measured, not assumed.
MEASURE_NAMES: frozenset[str] = frozenset({
    "kg", "kilogram", "kilograms", "g", "gram", "grams",
    "m", "meter", "meters", "metre", "metres",
    "cm", "centimeter", "centimeters", "centimetre", "centimetres",
    "l", "liter", "liters", "litre", "litres",
    "ml", "milliliter", "milliliters", "millilitre", "millilitres",
    "m2", "m²", "square meter", "square meters", "square metre", "square metres",
    "m3", "m³", "cubic meter", "cubic meters", "cubic metre", "cubic metres",
})

#: Hard ceiling on an observed scale (plan 6.4).
MAX_DECIMAL_PLACES = 4

#: What an unclassified unit gets, during rollout and forever after.
DEFAULT_DECIMAL_PLACES = 0

UomClass = Literal["count", "measure", "unknown"]

# The six transaction columns the plan names, each joined to its product's base UOM.
# `rtrim(...,'0')` drops trailing zeroes first, so 2.50000 is scale 1 rather than 5, and
# split_part on a value with no decimal point yields '' (scale 0) rather than a stray
# reading off an integer whose trailing zeroes rtrim also removed.
_OBSERVED_SCALE_SQL = """
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


def classify_uom_name(name: str | None) -> UomClass:
    """`count` / `measure` / `unknown` for a unit NAME, lowercased and trimmed.

    The code is never an input. See the module docstring for why.
    """
    key = (name or "").strip().lower()
    if key in COUNT_NAMES:
        return "count"
    if key in MEASURE_NAMES:
        return "measure"
    return "unknown"


def backfill_uom_decimal_places(bind: Any) -> int:
    """Give every unclassified unit its `decimal_places`. Returns the rows written.

    "Unclassified" is `decimal_places IS NULL` (which is every row while the migration
    holds the column nullable) **or** `= 0` (the rollout fallback a row lands on once the
    default is in place). A unit somebody has actually carried a value on - anything above
    0 - is never overwritten, so a re-run corrects a row left on the fallback without
    undoing a deliberate edit.

    Tolerates an empty database: with no units it writes nothing, which is what a fresh
    `alembic upgrade head` needs.

    `bind` is a Session or a Connection - anything with `.execute`. No ORM model is
    touched, so a migration may call this with its own connection.
    """
    rows = bind.execute(text(
        "SELECT id::text AS id, uom_name FROM units_of_measure "
        "WHERE decimal_places IS NULL OR decimal_places = 0"
    )).mappings().all()
    if not rows:
        return 0

    measure_ids = [
        r["id"] for r in rows if classify_uom_name(r["uom_name"]) == "measure"
    ]
    observed: dict[str, int] = {}
    if measure_ids:
        for row in bind.execute(
            text(_OBSERVED_SCALE_SQL), {"uom_ids": measure_ids}
        ).mappings().all():
            observed[row["uom_id"]] = min(int(row["scale"] or 0), MAX_DECIMAL_PLACES)

    written = 0
    for r in rows:
        if classify_uom_name(r["uom_name"]) == "measure":
            value = observed.get(r["id"], DEFAULT_DECIMAL_PLACES)
        else:
            # A count name and an unrecognised name are the same answer: whole units.
            value = DEFAULT_DECIMAL_PLACES
        bind.execute(
            text("UPDATE units_of_measure SET decimal_places = :v WHERE id::text = :id"),
            {"v": value, "id": r["id"]},
        )
        written += 1
    return written
