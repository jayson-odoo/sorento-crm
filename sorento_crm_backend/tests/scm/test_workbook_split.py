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
    # The three RETURNED titles, not `used`'s own internal casing - `used` is documented
    # to hold lowercased entries (case-insensitive collision tracking), which is an
    # implementation detail this test must not pin.
    assert {first, second, third} == {
        "Same title", "Same title (2)", "Same title (3)",
    }

    # Within a tight limit, the numbered suffix still fits - the base is cut to make room.
    tight_used: set[str] = set()
    base_only = wbs.unique_sheet_title("C" * 20, tight_used, limit=10)
    assert base_only == "C" * 10
    collided = wbs.unique_sheet_title("C" * 20, tight_used, limit=10)
    assert collided == "C" * 6 + " (2)", collided
    assert len(collided) <= 10


# =========================================================================== #
# Reviewer round (kill test): `unique_sheet_title` and `sanitize_sheet_title` gain three
# behaviours the FIRST pass missed. WRITTEN BEFORE THE FIX LANDS - the current
# `workbook_split.py` compares titles with plain Python string/set equality (case-
# SENSITIVE) and has no `reserve` parameter, so these are RED until the coder's fix lands.
# =========================================================================== #

def test_unique_sheet_title_is_case_insensitive():
    """Excel folds sheet TAB names case-insensitively - "Acme" and "ACME" are the SAME name
    to Excel even though `"Acme" != "ACME"` in Python. A `used: set[str]` compared with
    plain string equality lets both through as if they were different sheets; the second
    one must collide and take the ` (2)` suffix, exactly as if the caller had asked for
    "Acme" twice.
    """
    wbs = _wbs()
    used: set[str] = set()

    first = wbs.unique_sheet_title("Acme", used)
    assert first == "Acme"
    second = wbs.unique_sheet_title("ACME", used)
    assert second == "ACME (2)", (
        "a title that only differs in CASE from one already taken must still collide"
    )


def test_unique_sheet_title_reserve_blocks_every_suffixed_form():
    """New keyword `reserve: tuple[str, ...] = ()` - the SUFFIXES a caller is about to
    append to the SAME base (the low stock workbook's own `f"{base} - Low"` beside `base`
    itself: one title-uniqueness budget shared by a pair, not two independent calls that
    can each pick a name the other is about to collide with). A candidate is accepted only
    when the candidate AND every `candidate + suffix` in `reserve` are free
    (case-insensitive), and taking it marks ALL of them used.
    """
    wbs = _wbs()

    # "Foo" is free standing alone, but the SAME pair is about to also claim "Foo - Low" -
    # `reserve` must check that reservation before handing out the bare "Foo".
    used: set[str] = set()
    base = wbs.unique_sheet_title("Foo", used, limit=25, reserve=(" - Low",))
    assert base == "Foo"
    # `used` is documented to hold LOWERCASED entries (case-insensitive collision
    # tracking) - compared lowercased here rather than pinning that internal casing as
    # if it were the observable contract.
    assert used >= {"foo", "foo - low"}, used

    # A LATER, genuinely different key that happens to equal the first pair's RESERVED
    # form (not its base) must also be treated as taken.
    second = wbs.unique_sheet_title("Foo - Low", used, limit=25, reserve=(" - Low",))
    assert second == "Foo - Low (2)", (
        "\"Foo - Low\" was already reserved by the first pair's own suffix - it must not "
        "be handed out bare"
    )

    # And the reverse order: a prior pair's reserved suffix "X - Low" blocks a LATER bare
    # candidate "X" from taking the name outright.
    used2: set[str] = set()
    wbs.unique_sheet_title("X - Low", used2, limit=25, reserve=(" - Low",))
    third = wbs.unique_sheet_title("X", used2, limit=25, reserve=(" - Low",))
    assert third == "X (2)", (
        "a prior pair's reserved \"X - Low\" must block a later bare \"X\", not just an "
        "exact repeat of \"X - Low\" itself"
    )


def test_sanitize_sheet_title_strips_control_chars_apostrophes_and_never_trails_a_space():
    """`sanitize_sheet_title` gains three more Excel-tab rules beyond the forbidden-
    punctuation set already covered above:

    * C0 control characters (tab, `\\x01`, newline, ...) are stripped, not just
      `[]:*?/\\`.
    * A leading/trailing apostrophe is stripped - Excel itself refuses a sheet name that
      starts or ends with one.
    * The cut to `limit` is RSTRIPPED afterwards, so a cut that lands mid-word never
      leaves a trailing space in the title Excel actually shows.
    * The single reserved name "History" (Excel's own built-in change-log sheet, any
      case) maps to "History sheet" rather than colliding with a sheet Excel will not let
      exist under that name.
    """
    wbs = _wbs()

    assert wbs.sanitize_sheet_title("\tA\x01B\n") == "AB", (
        "C0 control characters must be stripped, not just the Excel-forbidden punctuation"
    )
    assert wbs.sanitize_sheet_title("'Quoted'") == "Quoted", (
        "a leading/trailing apostrophe must be stripped"
    )
    assert wbs.sanitize_sheet_title(
        "CHAOZHOU CHAOAN FENGTANG DAFUYUAN", limit=25,
    ) == "CHAOZHOU CHAOAN FENGTANG", (
        "raw[:25] lands exactly on the space after FENGTANG - the cut result must be "
        "RSTRIPPED, not left ending in a trailing space"
    )
    assert wbs.sanitize_sheet_title("History") == "History sheet", (
        "Excel reserves the literal name \"History\" for its own sheet"
    )
    assert wbs.sanitize_sheet_title("HISTORY") == "History sheet", (
        "the reserved-name check is case-insensitive, like every other rule here"
    )
