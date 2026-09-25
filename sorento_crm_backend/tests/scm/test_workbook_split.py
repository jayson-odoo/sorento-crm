"""PLAN-low-stock-export-split-25sep (#1229), test list items 1-3 (AC-1, AC-1b).

`app/services/scm/workbook_split.py` - lifted from `stock_debt_service`'s own
`_sanitize_sheet_title` / `_unique_sheet_title`, plus the new `split_rows` the low stock
report and Stock Debt both call once the lift lands (AC-2). Pure functions, no DB: these
three tests seed nothing and open no session.

WRITTEN BEFORE THE MODULE EXISTS (Phase 2 is test-first). The import lives INSIDE each test
(`_wbs()`), not at module top, so a missing module is one red test per function rather than
a collection error that hides the other two.
"""
from __future__ import annotations


def _wbs():
    """`app.services.scm.workbook_split` - the module the plan names. Imported per test so
    its absence reads as one explicit red test rather than a collection failure."""
    from app.services.scm import workbook_split

    return workbook_split


def test_split_rows_supplier_none_bucket_and_sort():
    """AC-1: `split_rows(rows, "supplier", ...)` keys on the supplier callable, folds a
    blank/None supplier into "No supplier", keeps a group's rows in their INPUT order, and
    orders the groups by the SANITISED key, case-insensitive - "alpha" (lower) sorts before
    "No supplier" and "Zeta" (upper) though the raw casing disagrees.
    """
    wbs = _wbs()
    rows = [
        {"id": 1, "supplier": "Zeta co"},
        {"id": 2, "supplier": None},
        {"id": 3, "supplier": "alpha co"},
        {"id": 4, "supplier": "Zeta co"},
    ]

    result = wbs.split_rows(
        rows, "supplier",
        supplier=lambda r: r["supplier"], category=lambda r: None,
    )

    assert [key for key, _ in result] == ["alpha co", "No supplier", "Zeta co"], result
    by_key = dict(result)
    assert [r["id"] for r in by_key["Zeta co"]] == [1, 4], (
        "a group's rows keep the caller's own input order"
    )
    assert [r["id"] for r in by_key["No supplier"]] == [2]
    assert [r["id"] for r in by_key["alpha co"]] == [3]


def test_split_rows_category_and_pairs_only_present():
    """AC-1: `split="category"` folds a blank/None category into "No category".
    `split="supplier_category"` keys on `"<supplier> - <category>"` and ONLY the pairs that
    actually have a row appear - four rows across two suppliers and two categories name
    just three pairs here, never the full 2x2 cross product, and a pair's rows accumulate
    across more than one input row.
    """
    wbs = _wbs()
    rows = [
        {"id": 1, "supplier": "Acme", "category": "Taps"},
        {"id": 2, "supplier": "Acme", "category": "Taps"},
        {"id": 3, "supplier": "Acme", "category": "Showers"},
        {"id": 4, "supplier": "Beta", "category": "Taps"},
        {"id": 5, "supplier": "Beta", "category": None},
    ]
    supplier = lambda r: r["supplier"]  # noqa: E731
    category = lambda r: r["category"]  # noqa: E731

    by_category = wbs.split_rows(rows, "category", supplier=supplier, category=category)
    assert [key for key, _ in by_category] == ["No category", "Showers", "Taps"], (
        by_category
    )
    cat_map = dict(by_category)
    assert [r["id"] for r in cat_map["Taps"]] == [1, 2, 4]
    assert [r["id"] for r in cat_map["No category"]] == [5]

    by_pair = wbs.split_rows(
        rows, "supplier_category", supplier=supplier, category=category,
    )
    # "Beta - Showers" never appears - no row names that pair (AC-1: only present pairs).
    assert [key for key, _ in by_pair] == [
        "Acme - Showers", "Acme - Taps", "Beta - No category", "Beta - Taps",
    ], by_pair
    pair_map = dict(by_pair)
    assert [r["id"] for r in pair_map["Acme - Taps"]] == [1, 2], (
        "a pair's rows accumulate across more than one input row, in input order"
    )
    assert [r["id"] for r in pair_map["Acme - Showers"]] == [3]
    assert [r["id"] for r in pair_map["Beta - Taps"]] == [4]
    assert [r["id"] for r in pair_map["Beta - No category"]] == [5]


def test_sanitize_and_unique_titles_with_limit():
    """AC-1b: `sanitize_sheet_title` strips `[]:*?/\\`, trims whitespace, cuts to `limit`
    (default 31), and never returns empty - a title that sanitises to nothing still needs a
    tab to sit on, so it falls back to "Sheet". `unique_sheet_title` appends " (2)", " (3)"
    on a collision, itself staying within `limit`.
    """
    wbs = _wbs()

    assert wbs.sanitize_sheet_title("A/B:C*D?E[F]G\\H") == "ABCDEFGH"
    assert wbs.sanitize_sheet_title("  padded  ") == "padded"
    assert wbs.sanitize_sheet_title("[]:*?/\\") == "Sheet", (
        "a title that sanitises to nothing must never be empty"
    )
    assert wbs.sanitize_sheet_title("A" * 40) == "A" * 31, "default limit is 31"
    assert wbs.sanitize_sheet_title("B" * 40, limit=25) == "B" * 25, (
        "a caller may ask for a tighter limit (the ' - Low' suffix room, A4)"
    )

    used: set[str] = set()
    first = wbs.unique_sheet_title("Same title", used)
    assert first == "Same title"
    second = wbs.unique_sheet_title("Same title", used)
    assert second == "Same title (2)", second
    third = wbs.unique_sheet_title("Same title", used)
    assert third == "Same title (3)", third
    assert used == {"Same title", "Same title (2)", "Same title (3)"}

    # Within a tight limit, the numbered suffix still fits - the base is cut to make room.
    tight_used: set[str] = set()
    base_only = wbs.unique_sheet_title("C" * 20, tight_used, limit=10)
    assert base_only == "C" * 10
    collided = wbs.unique_sheet_title("C" * 20, tight_used, limit=10)
    assert collided == "C" * 6 + " (2)", collided
    assert len(collided) <= 10
