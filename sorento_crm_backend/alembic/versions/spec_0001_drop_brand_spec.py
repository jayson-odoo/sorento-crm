"""Remove the Brand specification; the product's brand field is the only brand (#1286, S0).

Owner ruling, 26 Sep 2026 (Q1, Q2, Q4, PR #1290): the Brand specification is redundant. The
product already carries `products.brand_id`, and that field is the only brand. Every reader
of the specification now reads the product's brand (PLAN-product-specs-non-technical-26sep.md
D1 to D3; the readers are listed as R1 to R10 in evidence-product-specs-non-technical.md).

1. `brands.is_searchable`, not null, default true ("Customers can ask for this brand"). It
   replaces the removed row's `excluded_values`: OTHERS and NO LOGO are how the catalogue
   records the ABSENCE of a brand, so they are seeded false.
2. The `brand` row of `product_spec_registry` is deleted. Its typed values, words, labels,
   exclusions and value weights are logged at WARNING first, so the deploy log keeps them.
3. Active verification stamps whose hash was made over values that still carried `brand`
   are re-hashed over the same values without it, so removing brand does not read as a
   change a person has to re-check. The hash is a frozen copy of
   `product_spec_write.canonical_values_hash` (a migration must not change when app code
   does).
4. `brand` entries are stripped from every stamp's `invalidated_diff`.
5. Open `product_spec_exceptions` rows on `brand` are deleted.
6. `brand` is stripped from every row's `values` and `provenance`. `rendered_text` is left
   as it is: the sentence still leads with the brand, and the next re-read renders it from
   the product's brand field.

Idempotent: every step selects only what still mentions brand, so a second run changes
nothing.

Downgrade drops the column only. The deleted rows and the stripped values are not put back:
they are in the WARNING log, and nothing reads them any more.

Revision ID: spec_0001_drop_brand
Revises: sales_0002_team_leader
Create Date: 2026-09-26
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation

from alembic import op
from sqlalchemy import text

revision = "spec_0001_drop_brand"
down_revision = "sales_0002_team_leader"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

_BRAND = "brand"
_NOT_SEARCHABLE = ("OTHERS", "NO LOGO")
_AUTHORED = ("human", "supplier", "flyer")


# --------------------------------------------------------------------------- #
# frozen copy of product_spec_write.canonical_values_hash (26 Sep 2026)
# --------------------------------------------------------------------------- #
def _canonical_value(raw):
    if raw is None:
        return None
    if isinstance(raw, bool):
        return ["bool", raw]
    if isinstance(raw, (int, float, Decimal)):
        try:
            return ["num", format(Decimal(str(raw)).normalize(), "f")]
        except (InvalidOperation, ValueError):
            return ["str", str(raw).strip()]
    if isinstance(raw, (list, tuple)):
        items = [_canonical_value(item) for item in raw]
        items = [item for item in items if item is not None]
        items.sort(key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")))
        return ["list", items]
    if isinstance(raw, Mapping):
        return ["map", {str(k): _canonical_value(v) for k, v in sorted(raw.items())}]
    stripped = str(raw).strip()
    return ["str", stripped] if stripped else None


def _canonical_entry(entry):
    if isinstance(entry, Mapping):
        raw, unit = entry.get("value"), entry.get("unit")
    else:
        raw, unit = entry, None
    value = _canonical_value(raw)
    if value is None:
        return None
    canonical = {"v": value}
    folded = str(unit).strip().casefold() if unit is not None else ""
    if folded:
        canonical["u"] = folded
    return canonical


def _values_hash(values) -> str:
    canonical = {}
    for key, entry in (values or {}).items():
        reduced = _canonical_entry(entry)
        if reduced is not None:
            canonical[str(key)] = reduced
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


# --------------------------------------------------------------------------- #
# the steps
# --------------------------------------------------------------------------- #
def _add_is_searchable(bind) -> None:
    op.execute(
        "ALTER TABLE brands ADD COLUMN IF NOT EXISTS is_searchable boolean NOT NULL DEFAULT true"
    )
    flipped = bind.execute(
        text(
            "UPDATE brands SET is_searchable = false"
            " WHERE upper(trim(brand_name)) = ANY(:names) AND is_searchable"
            " RETURNING brand_code, brand_name"
        ),
        {"names": list(_NOT_SEARCHABLE)},
    ).all()
    for code, name in flipped:
        logger.warning("spec_0001: brand %s (%s) set not searchable", name, code)


def _delete_registry_row(bind) -> None:
    row = (
        bind.execute(
            text(
                "SELECT user_values, value_labels, suppressed_values, user_synonyms,"
                " excluded_values, value_weights, derivation_rules"
                " FROM product_spec_registry WHERE spec_key = :key"
            ),
            {"key": _BRAND},
        )
        .mappings()
        .first()
    )
    if row is None:
        return
    logger.warning(
        "spec_0001: deleting the brand specification row: %s",
        json.dumps({k: row[k] for k in row.keys()}, default=str, sort_keys=True),
    )
    bind.execute(text("DELETE FROM product_spec_registry WHERE spec_key = :key"), {"key": _BRAND})


def _rehash_active_stamps(bind) -> None:
    """Re-hash a live stamp made over values that still carry brand.

    Only when the stamp's hash IS the hash of the code's current values (the copy
    `current_values_hash` reads: the lowest product id with a spec row). A stamp that
    already disagrees with them is stale for another reason and is left alone.
    """
    rows = (
        bind.execute(
            text(
                'SELECT v.id, v.product_code, v.values_hash, c."values" AS vals'
                " FROM product_spec_verifications v"
                " CROSS JOIN LATERAL ("
                '   SELECT ps."values" FROM product_specifications ps'
                "   JOIN products p ON p.id = ps.product_id"
                "   WHERE p.product_code = v.product_code"
                "   ORDER BY p.id LIMIT 1"
                " ) c"
                ' WHERE v.invalidated_at IS NULL AND c."values" ? :key'
            ),
            {"key": _BRAND},
        )
        .mappings()
        .all()
    )
    for row in rows:
        values = dict(row["vals"] or {})
        if _values_hash(values) != row["values_hash"]:
            continue
        values.pop(_BRAND, None)
        bind.execute(
            text("UPDATE product_spec_verifications SET values_hash = :hash WHERE id = :id"),
            {"hash": _values_hash(values), "id": row["id"]},
        )
        logger.warning(
            "spec_0001: re-hashed the active verification of %s without brand",
            row["product_code"],
        )


def _strip_invalidated_diffs(bind) -> None:
    rows = (
        bind.execute(
            text(
                "SELECT id, product_code, invalidated_diff FROM product_spec_verifications"
                " WHERE invalidated_diff IS NOT NULL"
                " AND jsonb_typeof(invalidated_diff -> 'changed') = 'array'"
                " AND EXISTS ("
                "   SELECT 1 FROM jsonb_array_elements(invalidated_diff -> 'changed') e"
                "   WHERE e ->> 'spec_key' = :key"
                " )"
            ),
            {"key": _BRAND},
        )
        .mappings()
        .all()
    )
    for row in rows:
        diff = dict(row["invalidated_diff"] or {})
        dropped = [e for e in diff.get("changed") or [] if (e or {}).get("spec_key") == _BRAND]
        diff["changed"] = [
            e for e in diff.get("changed") or [] if (e or {}).get("spec_key") != _BRAND
        ]
        bind.execute(
            text(
                "UPDATE product_spec_verifications"
                " SET invalidated_diff = CAST(:diff AS jsonb) WHERE id = :id"
            ),
            {"diff": json.dumps(diff), "id": row["id"]},
        )
        logger.warning(
            "spec_0001: stripped brand from the verification diff of %s: %s",
            row["product_code"],
            json.dumps(dropped, default=str),
        )


def _delete_open_exceptions(bind) -> None:
    deleted = bind.execute(
        text(
            "DELETE FROM product_spec_exceptions"
            " WHERE spec_key = :key AND resolved_at IS NULL"
            " RETURNING product_code, reason"
        ),
        {"key": _BRAND},
    ).all()
    for code, reason in deleted:
        logger.warning("spec_0001: deleted the open brand exception on %s (%s)", code, reason)


def _strip_values(bind) -> None:
    # A value a person typed is named one by one; everything derivation wrote is counted.
    authored = (
        bind.execute(
            text(
                'SELECT p.product_code, ps."values" -> :key AS typed, ps.provenance -> :key AS stamp'
                " FROM product_specifications ps JOIN products p ON p.id = ps.product_id"
                " WHERE ps.provenance -> :key ->> 'source' = ANY(:authored)"
                " ORDER BY p.product_code"
            ),
            {"key": _BRAND, "authored": list(_AUTHORED)},
        )
        .mappings()
        .all()
    )
    for row in authored:
        logger.warning(
            "spec_0001: clearing a brand set by hand on %s: %s (%s)",
            row["product_code"],
            json.dumps(row["typed"], default=str),
            json.dumps(row["stamp"], default=str, sort_keys=True),
        )
    stripped = bind.execute(
        text(
            'UPDATE product_specifications SET "values" = "values" - :key,'
            " provenance = provenance - :key"
            ' WHERE "values" ? :key OR provenance ? :key'
            " RETURNING id"
        ),
        {"key": _BRAND},
    ).all()
    if stripped:
        logger.warning(
            "spec_0001: stripped brand from %s product specification rows (%s set by hand)",
            len(stripped),
            len(authored),
        )


def upgrade() -> None:
    bind = op.get_bind()
    _add_is_searchable(bind)
    _delete_registry_row(bind)
    # Before the values are stripped: the re-hash needs the values the stamp was made over.
    _rehash_active_stamps(bind)
    _strip_invalidated_diffs(bind)
    _delete_open_exceptions(bind)
    _strip_values(bind)


def downgrade() -> None:
    op.execute("ALTER TABLE brands DROP COLUMN IF EXISTS is_searchable")
