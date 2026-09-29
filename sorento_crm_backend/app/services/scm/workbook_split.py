"""The workbook split every export offers (PLAN-low-stock-export-split-25sep, "second case"
of PLAN-stock-debt-filters-totals-export-24sep R5/A7): None / Supplier / Category /
Supplier x Category.

Lifted out of `stock_debt_service` (its own `_sanitize_sheet_title` / `_unique_sheet_title`
and the grouping loop inside `_render_workbook`) now that a second workbook - the low stock
report - pays for it. Pure functions, no DB: both callers pass in the rows and the two key
callables, and get back sheet titles / grouped rows.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

from app.services.error_handler import AppException

#: The four values every split-aware export accepts (R1/R6: `low_stock_report_service` and
#: `export_order_summary` both validate against this).
SPLIT_VALUES: Tuple[str, ...] = ("none", "supplier", "category", "supplier_category")

#: Excel forbids these in a sheet title; stripped rather than replaced, so a forbidden
#: character never leaves a stray placeholder character behind.
_FORBIDDEN_TITLE_CHARS = "[]:*?/\\"


def sanitize_sheet_title(raw: str, *, limit: int = 31) -> str:
    """Strip the characters Excel refuses in a sheet title - the eight forbidden symbols,
    C0 control characters (`ch < " "`; a name lifted from free text can carry one), and
    leading/trailing apostrophes (Excel's own separate rule) - then cut to `limit` (Excel's
    own cap is 31; a caller pairing two sheets per group passes a tighter one so the
    ` - Low` suffix still fits, A4).

    `rstrip()` runs AGAIN after the cut: measured on the prod copy, 10 of 71 real supplier
    names cut at 25 landed on a trailing space, which printed a tab like
    `"CHAOZHOU CHAOAN FENGTANG  - Low"` (review fix round, security). A result that
    sanitises to Excel's own reserved name, case-insensitively, becomes "History sheet"
    instead - Excel refuses a sheet literally named "History" in any case. Never empty: a
    title that sanitises to nothing still needs a tab to sit on.
    """
    cleaned = (
        "".join(ch for ch in raw if ch not in _FORBIDDEN_TITLE_CHARS and ch >= " ")
        .strip()
        .strip("'")
    )
    cut = cleaned[:limit].rstrip()
    if not cut:
        return "Sheet"
    if cut.lower() == "history":
        return "History sheet"
    return cut


def unique_sheet_title(
    raw: str, used: Set[str], *, limit: int = 31, reserve: Tuple[str, ...] = (),
) -> str:
    """`sanitize_sheet_title`, then a ` (2)`/` (3)`/... suffix for a title that collides
    with one already taken - two supplier/category pairs whose names agree on the first
    `limit` characters must not silently overwrite one sheet with the other.

    Comparisons are CASE-INSENSITIVE (`used` holds LOWERCASED titles): Excel and openpyxl
    both treat tab names case-insensitively, and openpyxl's own silent rename on a
    collision it does not know about can still produce a 32-character tab that makes Excel
    repair the file on open (review fix round, security).

    `reserve` names the OTHER suffix(es) a caller is about to pair with this same base (the
    low stock report's own `" - Low"` sheet, written alongside the base) - a candidate is
    accepted only when the candidate ITSELF and every `candidate + suffix` for `suffix` in
    `reserve` are all free, and on acceptance every one of them is added to `used` in the
    same step. This is what lets both tabs of a pair reserve their titles together, so an
    unrelated later group can never be handed the exact string this pair's own `" - Low"`
    sheet is about to use.
    """
    def _free(candidate: str) -> bool:
        if candidate.lower() in used:
            return False
        return all(f"{candidate}{suffix}".lower() not in used for suffix in reserve)

    def _claim(candidate: str) -> str:
        used.add(candidate.lower())
        for suffix in reserve:
            used.add(f"{candidate}{suffix}".lower())
        return candidate

    base = sanitize_sheet_title(raw, limit=limit)
    if _free(base):
        return _claim(base)
    for n in range(2, 1000):
        suffix = f" ({n})"
        candidate = base[: limit - len(suffix)] + suffix
        if _free(candidate):
            return _claim(candidate)
    raise AppException(500, "Could not title every export sheet uniquely.")


def split_rows(
    rows: Sequence[dict],
    split: str,
    *,
    supplier: Callable[[dict], Optional[str]],
    category: Callable[[dict], Optional[str]],
) -> List[Tuple[str, List[dict]]]:
    """Group `rows` by `split` ("supplier", "category", or anything else read as
    "supplier_category" - `"none"` is the caller's own business, since each workbook has
    its own fixed title for the unsplit sheet).

    A blank/None supplier or category folds into "No supplier" / "No category". A group's
    rows keep the CALLER's own input order; groups themselves are returned in SANITISED
    title order, case-insensitive, so the grouping and the sheet order agree with what the
    workbook prints without a second sort anywhere downstream. `supplier_category` names
    only the pairs that actually have a row - never the full cross product.
    """
    groups: Dict[str, List[dict]] = {}
    for row in rows:
        supplier_label = supplier(row) or "No supplier"
        category_label = category(row) or "No category"
        if split == "supplier":
            key = supplier_label
        elif split == "category":
            key = category_label
        else:
            key = f"{supplier_label} - {category_label}"
        groups.setdefault(key, []).append(row)

    ordered_keys = sorted(groups, key=lambda raw: sanitize_sheet_title(raw).lower())
    return [(key, groups[key]) for key in ordered_keys]
