"""R2 — CS-routing predicate engine (pure, DB-free).

A CS-routing pin (``respond_contact_cs_routing``) carries ``match_conditions`` — an
array of ``{field, operator, value}`` predicates, AND-combined — evaluated against a
form's own header field values. Resolution picks the matching row with the lowest
admin-set ``priority`` (``created_at`` tiebreak). An empty condition list is a
wildcard that always matches.

Kept dependency-free (no SQLAlchemy, no DB) so it is exhaustively unit-testable and
reusable from both the resolver and any future config-preview endpoint.

UAC: documentation/plans/forms/form-cs-routing-conditions-acceptance-criteria.md
(Groups ME + RES).
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Optional

# Operators supported in v1. `contains`/`not_contains` are string-only (the config
# UI hides them for enum/numeric fields; the resolver still evaluates them safely).
VALID_OPERATORS = ("equals", "not_equals", "contains", "not_contains")


def predicate_passes(predicate: dict, form_values: dict) -> bool:
    """Evaluate one ``{field, operator, value}`` predicate against a form's fields.

    A NULL/absent form field never ``equals``/``contains`` a concrete value (ME-6);
    ``not_equals``/``not_contains`` treat a NULL field as "does not equal / does not
    contain". An unknown operator never matches (defensive)."""
    field = predicate.get("field")
    operator = predicate.get("operator")
    value = predicate.get("value")
    actual = form_values.get(field)

    if operator == "equals":
        return actual is not None and str(actual) == str(value)
    if operator == "not_equals":
        return actual is None or str(actual) != str(value)
    if operator == "contains":
        return actual is not None and str(value) in str(actual)
    if operator == "not_contains":
        return actual is None or str(value) not in str(actual)
    return False


def row_matches(match_conditions: Optional[list], form_values: dict) -> bool:
    """A row matches when EVERY predicate passes (AND). Empty/None = wildcard."""
    if not match_conditions:
        return True
    return all(predicate_passes(p, form_values) for p in match_conditions)


def _sort_key(row: Any):
    # Lower priority wins (pure admin order); created_at breaks ties deterministically.
    priority = getattr(row, "priority", 0) or 0
    created_at = getattr(row, "created_at", None)
    # created_at may be None on freshly-built objects; push those last, stably.
    return (priority, created_at is None, created_at)


def rank_matching_rows(rows: Iterable[Any], form_values: dict) -> list:
    """Return the matching rows ordered by (priority asc, created_at asc)."""
    matched = [r for r in rows if row_matches(getattr(r, "match_conditions", None), form_values)]
    return sorted(matched, key=_sort_key)


def select_pin_row(rows: Iterable[Any], form_values: dict) -> Optional[Any]:
    """Pick the single winning routing row for a form, or None (→ round-robin)."""
    ranked = rank_matching_rows(rows, form_values)
    return ranked[0] if ranked else None


def canonical_conditions(match_conditions: Optional[list]) -> str:
    """Deterministic string for the uniqueness index / dedup.

    Normalizes predicate key order and list order so logically-equal condition sets
    collide (one pin per distinct condition set for a given contact+use_case). The
    SAME normalization must back the DB unique index (see migration)."""
    conds = match_conditions or []
    normalized = sorted(
        (
            {
                "field": c.get("field"),
                "operator": c.get("operator"),
                "value": c.get("value"),
            }
            for c in conds
        ),
        key=lambda c: (str(c["field"]), str(c["operator"]), str(c["value"])),
    )
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
