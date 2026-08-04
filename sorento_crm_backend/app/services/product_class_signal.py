"""Make the class and brand encoded in `category_code` machine-readable.

`product_categories.category_name` is a verbatim copy of `category_code` on all 175
live rows, so the two most valuable ranking signals in the catalog are sitting in a
string nothing reads. The codes decompose as `<BRAND>-<CLASS>`:

    SRT-KS  ->  Sorento  Kitchen Sink
    CB-FT   ->  Cabana   Tap and Fitting
    BRT-WC  ->  Bravat   Water Closet

Class matters more than any other spec key because its coverage is total: every
product has a category, whereas `dimensions_length` is populated on 14.6% of rows and
`item_type` on none. It is therefore the largest single boost in the spec-search
ranker, which is also why an unmapped code must never be guessed at: a wrong class is
the most damaging value the ranker can be handed.

Scope is deliberately the pilot class only (jayson-odoo/sorento-crm#72, the T0 tracer).
Widening is adding entries to `CLASS_SUFFIXES`, not changing this module.

Contract: documentation/plans/products/spec-search-acceptance-criteria.md
AC-T0a-01 .. AC-T0a-05.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.product import ProductCategory

# The `<BRAND>-` half of a category code. Known in full because the brand set is
# small and closed; a code whose prefix is absent here is reported, never guessed.
BRAND_PREFIXES: dict[str, str] = {
    "SRT": "Sorento",
    "CB": "Cabana",
    "M": "Mocha",
    "BRT": "Bravat",
}

# The `-<CLASS>` half. PILOT SCOPE: kitchen sink only. Every other suffix in the live
# catalog (FT, BA, WB, SH, FC, WC, JC, ...) is intentionally absent, so T0 runs against
# 1,016 codes and the remaining 173 categories are reported as unmapped rather than
# silently half-classified. T2 widens this map.
CLASS_SUFFIXES: dict[str, str] = {
    "KS": "Kitchen Sink",
}

# Customer language is not catalog language. Matched case-insensitively alongside the
# class label itself. Malay terms included because the corpus is bilingual.
CLASS_SYNONYMS: dict[str, list[str]] = {
    "Kitchen Sink": ["kitchen sink", "sink", "sinki", "dapur"],
}

# Categories that carry no class meaning at all. Flagged non-searchable so they cannot
# masquerade as a class once the ranker starts trusting `class_label`.
NON_SEARCHABLE_CODES: frozenset[str] = frozenset({"MISC", "PROJECT", "SRTPART", "VD"})


def signal_for_code(category_code: str) -> tuple[str | None, str | None] | None:
    """(class_label, brand_hint) for a category code, or None when it is unmapped.

    Returns `(None, None)` for a known-meaningless code so the caller can tell
    "deliberately blank" apart from "we do not recognise this", which is the
    difference between a clean row and one that needs a human.
    """
    code = (category_code or "").strip().upper()
    if not code:
        return None
    if code in NON_SEARCHABLE_CODES:
        return (None, None)

    prefix, _, suffix = code.partition("-")
    if not suffix:
        return None

    brand = BRAND_PREFIXES.get(prefix)
    class_label = CLASS_SUFFIXES.get(suffix)
    if class_label is None:
        return None
    return (class_label, brand)


def _desired_row(code: str) -> dict | None:
    """The values this code should hold, or None when the code is unmapped."""
    signal = signal_for_code(code)
    if signal is None:
        return None
    class_label, brand_hint = signal
    return {
        "class_label": class_label,
        "brand_hint": brand_hint,
        "search_synonyms": CLASS_SYNONYMS.get(class_label or "", []),
        "is_searchable": class_label is not None,
    }


def backfill_category_signals(db: Session, *, commit: bool = False) -> dict:
    """Set the class signal on every category whose stored value is wrong.

    Set-where-mismatch, deliberately, NOT update-where-null: this backfill is expected
    to be re-run every time the map grows, and update-where-null cannot repair a row a
    previous run got wrong. Idempotent, so a re-run with nothing to fix writes nothing.

    An unmapped code is left untouched and returned in `unmapped`. Reporting it is the
    point: a category nobody has classified is invisible to spec search, and the only
    way that surfaces is if the job says so.
    """
    updated = 0
    unmapped: list[str] = []

    for row in db.query(ProductCategory).all():
        desired = _desired_row(row.category_code)
        if desired is None:
            unmapped.append(row.category_code)
            continue

        changed = False
        for field, value in desired.items():
            if getattr(row, field) != value:
                setattr(row, field, value)
                changed = True
        if changed:
            updated += 1

    db.flush()
    if commit:
        db.commit()

    return {"updated": updated, "unmapped": sorted(unmapped), "unmapped_count": len(unmapped)}


def resolve_classes_for_term(db: Session, term: str) -> list[str]:
    """Class labels a customer's word refers to, matched on label or synonym.

    Case-insensitive and whitespace-tolerant, because this is fed raw customer text.
    Non-searchable categories can never match. Returns a sorted list rather than one
    value: a term may legitimately span classes once the map widens.
    """
    needle = (term or "").strip().lower()
    if not needle:
        return []

    found: set[str] = set()
    rows = (
        db.query(ProductCategory)
        .filter(ProductCategory.is_searchable.is_(True))
        .filter(ProductCategory.class_label.isnot(None))
        .all()
    )
    for row in rows:
        label = row.class_label or ""
        if label.lower() == needle:
            found.add(label)
            continue
        synonyms = row.search_synonyms or []
        if any(str(s).strip().lower() == needle for s in synonyms):
            found.add(label)

    return sorted(found)
