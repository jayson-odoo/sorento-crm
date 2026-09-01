"""Spec registry: the plausibility cap becomes a field, and the hidden readers become rows.

S2 of `PLAN-spec-rules-readable.md`, AC-A.5 and AC-A.6.

Two things, one revision, because they are one decision: what the rule list on the
Product specifications screen is allowed to leave out. The answer is nothing.

* `product_spec_registry.max_value` (numeric, null) - AC-A.5. Seeded 5000 on every
  millimetre key, which is where `MAX_PLAUSIBLE_MM` lived: a constant in the derivation
  engine that said the same thing about a 6 mm glass thickness and a 1.8 m bath, and that
  nobody could look at, let alone change. Blank means no cap.

* The readers that ran OUTSIDE the rule list, backfilled onto the keys a human has taken
  ownership of - AC-A.6. `configured_rules` prefers a key's stored rules over the shipped
  ones entirely ("change one and they become yours"), so a reader that was never a row
  would simply vanish for those keys. `class` holds 33 hand-written rules on the live
  database and three readers ran underneath them, none of which appeared on any screen.

  Where each goes is where it RAN, not the top of the list:

    - `dim_length` / `dim_width` / `dim_height` / `thickness` / `diameter` / `depth`:
      the column and the size block PREPENDED. Curated data outranked parsed text, and it
      goes on outranking it.
    - `class` / `brand`: the name head, the category and the brand field APPENDED. They
      were fallbacks under whatever a human wrote, and 20,697 of 23,063 live products sit
      in a category that carries a class - a category row on top would re-class the
      catalogue on the strength of a filing code.

  Every added row is tagged `shipped_backfill` so the downgrade can take back exactly
  what it put in and nothing else.

* Code rules are MOVED below the text rules of the same key. The engine this revision
  lands with runs a key's list in order, full stop; the engine it replaces ran every text
  rule before any code rule wherever the row sat, so `class` could hold "code contains
  SRTSC -> Seat Cover" on TOP of 32 rules that all outranked it and the screen could not
  be read as what the engine did. Moving the row changes nothing about what either engine
  derives - the old one already ran it there - and makes the list honest. It is not
  reversed on downgrade for the same reason: the order it leaves behind is the order the
  old engine used.

Hand-written and guarded with `IF NOT EXISTS` / inspector checks throughout, for the
reason 443 and 419 state: the shared dev database is a prod copy whose `alembic_version`
points at another lane's head, so this is applied there by hand and re-running it has to
be a no-op rather than a failure.

Revision ID: 450_spec_rules_readable
Revises: 448_merge_s6b_ptag
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "450_spec_rules_readable"
down_revision = "449_flyer_reading_code_overrides"
branch_labels = None
depends_on = None

# The engine's `_DIM_RE` and `_SINGLE_DIM_RE`, copied rather than imported: a migration is
# frozen and the module is not, and a later edit to the engine must not silently change
# what this revision wrote. `tests/test_migration_450_spec_rules_backfill.py` pins these
# against `shipped_rules()` so the copy cannot drift unnoticed while it still matters.
_DIM_PATTERN = (
    r"(?:[LWHDlwhd]\s*)?(\d+(?:\.\d+)?)\s*(?:MM|mm)?\s*[xX*]\s*"
    r"(?:[LWHDlwhd]\s*)?(\d+(?:\.\d+)?)\s*(?:MM|mm)?"
    r"(?:\s*[xX*]\s*(?:[LWHDlwhd]\s*)?(\d+(?:\.\d+)?)\s*(?:MM|mm)?)?"
    r"(?:\s*[xX*]\s*(?:[LWHDlwhd]\s*)?(\d+(?:\.\d+)?)\s*(?:MM|mm)?)?"
)
_LONE_SIZE_PATTERN = r"(?<![A-Z0-9X])(\d{2,4})\s*MM\b"
_ROUND_OR_SQUARE = {"shape": ["round", "square"]}

_BACKFILL_TAG = "shipped_backfill"
_SEED_MARKER = "_seed"
_CODE_KINDS = ("code_suffix", "code_contains", "code_starts_with")


def _column(name: str) -> dict:
    return {
        "match": "from_field",
        "pattern": f"column:{name}",
        "unless": _ROUND_OR_SQUARE,
        "builder": {"kind": "from_field", "field": f"column:{name}"},
        _SEED_MARKER: True,
    }


def _triple(position: int, *, when_round: bool) -> dict:
    row = {
        "match": "regex",
        "pattern": _DIM_PATTERN,
        "capture": position,
        "source": "description",
        "builder": {"kind": "size_triple", "position": position},
        _SEED_MARKER: True,
    }
    row["applies_when" if when_round else "unless"] = _ROUND_OR_SQUARE
    return row


# {spec_key: (rows, "before" | "after")}
_HIDDEN_READERS: dict[str, tuple[list[dict], str]] = {
    "dim_length": (
        [
            _column("dimensions_length"),
            _triple(1, when_round=False),
            {
                "match": "regex",
                "pattern": _LONE_SIZE_PATTERN,
                "capture": 1,
                "source": "size_text",
                "unless": _ROUND_OR_SQUARE,
                _SEED_MARKER: True,
            },
        ],
        "before",
    ),
    "dim_width": ([_column("dimensions_width"), _triple(2, when_round=False)], "before"),
    "dim_height": ([_column("dimensions_height"), _triple(3, when_round=False)], "before"),
    "thickness": (
        [_triple(4, when_round=False), _triple(3, when_round=True)],
        "before",
    ),
    "diameter": ([_triple(1, when_round=True)], "before"),
    "depth": ([_triple(2, when_round=True)], "before"),
    "class": (
        [
            {
                "match": "name_head",
                "pattern": "class_tail",
                "builder": {"kind": "name_head"},
                _SEED_MARKER: True,
            },
            {
                "match": "from_field",
                "pattern": "category",
                "builder": {"kind": "from_field", "field": "category"},
                _SEED_MARKER: True,
            },
        ],
        "after",
    ),
    "brand": (
        [
            {
                "match": "from_field",
                "pattern": "brand",
                "builder": {"kind": "from_field", "field": "brand"},
                _SEED_MARKER: True,
            }
        ],
        "after",
    ),
}


def _has_column(bind) -> bool:
    return "max_value" in {
        column["name"]
        for column in sa.inspect(bind).get_columns("product_spec_registry")
    }


def _identity(rule: dict) -> tuple:
    """A rule's identity for dedupe purposes: what it reads and how, not its tags.

    `builder`/`_seed_marker` differ between a row this migration would add and the
    same reader already sitting untouched on a key someone saved through the UI
    before this revision ran (dev DB's `dim_length` on 31 Aug) - comparing on the
    engine fields alone is what makes those two rows recognisably the same reader.
    """
    return (
        str(rule.get("match") or "").lower(),
        str(rule.get("pattern") or ""),
        rule.get("capture"),
        str(rule.get("source") or "any").lower(),
    )


def _owned_rows(bind):
    return bind.execute(
        sa.text(
            "SELECT spec_key, derivation_rules FROM product_spec_registry "
            "WHERE spec_key = ANY(:keys) AND jsonb_array_length(derivation_rules) > 0"
        ),
        {"keys": list(_HIDDEN_READERS)},
    ).fetchall()


def _store(bind, spec_key: str, rules: list) -> None:
    bind.execute(
        sa.text(
            "UPDATE product_spec_registry SET derivation_rules = CAST(:rules AS jsonb) "
            "WHERE spec_key = :key"
        ),
        {"key": spec_key, "rules": json.dumps(rules)},
    )


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_column(bind):
        op.add_column(
            "product_spec_registry",
            sa.Column("max_value", sa.Numeric(12, 3), nullable=True),
        )

    bind.execute(
        sa.text(
            "UPDATE product_spec_registry SET max_value = 5000 "
            "WHERE unit = 'mm' AND max_value IS NULL"
        )
    )

    for spec_key, stored in _owned_rows(bind):
        rows = list(stored or [])
        if any(rule.get(_BACKFILL_TAG) for rule in rows):
            continue  # already backfilled; re-running is a no-op
        # A key whose shipped rows arrived through a UI save rather than through this
        # migration already carries them, untagged (S3) - adding a second copy would
        # duplicate the reader instead of merely surfacing it. Left untagged: the
        # pre-existing row is the business's own save, not this migration's backfill,
        # so the downgrade must not touch it either.
        existing = {_identity(rule) for rule in rows}
        added = [
            dict(rule, **{_BACKFILL_TAG: True})
            for rule in _HIDDEN_READERS[spec_key][0]
            if _identity(rule) not in existing
        ]
        # The code rules go where the old engine ran them: after every text rule.
        text_rows = [rule for rule in rows if rule.get("match") not in _CODE_KINDS]
        code_rows = [rule for rule in rows if rule.get("match") in _CODE_KINDS]
        rows = text_rows + code_rows
        placement = _HIDDEN_READERS[spec_key][1]
        _store(bind, spec_key, added + rows if placement == "before" else rows + added)


def downgrade() -> None:
    bind = op.get_bind()

    for spec_key, stored in _owned_rows(bind):
        rows = [rule for rule in (stored or []) if not rule.get(_BACKFILL_TAG)]
        if len(rows) != len(stored or []):
            _store(bind, spec_key, rows)

    if _has_column(bind):
        op.drop_column("product_spec_registry", "max_value")
