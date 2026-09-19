"""Pure comparison functions for the AutoCount pull "Compare with my Excel" tab
(PLAN-autocount-pull-review.md, P11). No database access, no side effects - the
route (`app.api.v1.integrations.autocount_pull`) reads the pull's rows, the
browser posts its own parsed file, and this module is what decides where they
agree and where they do not.

`excel_rows` carry the manual-template column names (`Item Code`, `Description`,
`Desc 2`, `Item Group`, `Item Brand`, `Price`, `Is Active`) - what the browser
parses out of the checker's own workbook, the same shape `ProductService.
bulk_import_products` reads. `pull_rows` carry the RAW FoundryX snapshot-row
shape (`code`/`name`/`description`/`category_code`/`brand_code`/`list_price`/
`is_active`) - AC-CM-2 compares the Excel join against the pull's own
`description` field directly, never a mapped view row.

The Excel-side normalisation calls the manual import's OWN rules (Desc 2 join,
price parse/clamp, Is Active truthy rule, all lifted onto module-level
functions in `product_service.py` for exactly this reason) so this tab and the
manual upload can never quietly disagree on what counts as a match.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.product_service import (
    is_active_from_manual_value,
    join_description_and_desc2,
    parse_manual_list_price,
)


def _key(code: Any) -> str:
    return str(code or "").strip().upper()


def _excel_code(row: dict) -> str:
    return str(row.get("Item Code") or "").strip()


def _pull_code(row: dict) -> str:
    return str(row.get("code") or "").strip()


def _excel_description(row: dict) -> str:
    return join_description_and_desc2(row.get("Description") or "", row.get("Desc 2") or "")


def _normalize_ws(text: str) -> str:
    """Collapses any run of whitespace to a single space for the EQUALITY check
    only - the AC-RV-3 row mapping already strips a Desc 2 remainder down to
    its own text (rv_3b), so re-joining it loses whatever spacing the source
    AutoCount `description` field originally carried between the two halves.
    That loss is not a real difference for the checker to see."""
    return " ".join((text or "").split())


def _excel_price(row: dict) -> Decimal:
    try:
        return parse_manual_list_price(row.get("Price"))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _pull_price(row: dict) -> Decimal:
    try:
        return Decimal(str(row.get("list_price")))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def compare_products(excel_rows: list[dict], pull_rows: list[dict]) -> dict:
    """AC-CM-2: keyed by Item Code, trimmed and case-insensitive.

    Returns a `summary` (`total`/`matched`/`different`, over the INTERSECTION
    of the two sides), `differences` (one entry per differing field, each
    carrying both values), and `only_in_excel` / `only_in_pull` (item codes).
    """
    excel_by_key: dict[str, dict] = {}
    for row in excel_rows:
        key = _key(_excel_code(row))
        if key:
            excel_by_key[key] = row

    pull_by_key: dict[str, dict] = {}
    for row in pull_rows:
        key = _key(_pull_code(row))
        if key:
            pull_by_key[key] = row

    only_in_excel = sorted(_excel_code(excel_by_key[k]) for k in excel_by_key if k not in pull_by_key)
    only_in_pull = sorted(_pull_code(pull_by_key[k]) for k in pull_by_key if k not in excel_by_key)

    common_keys = [k for k in excel_by_key if k in pull_by_key]
    differences: list[dict] = []
    matched = 0

    for key in common_keys:
        excel_row = excel_by_key[key]
        pull_row = pull_by_key[key]
        item_code = _pull_code(pull_row) or _excel_code(excel_row)
        row_diffs: list[tuple[str, Any, Any]] = []

        excel_desc = _excel_description(excel_row)
        pull_desc = pull_row.get("description") or ""
        if _normalize_ws(excel_desc) != _normalize_ws(pull_desc):
            row_diffs.append(("description", excel_desc, pull_desc))

        excel_group = (excel_row.get("Item Group") or "").strip()
        pull_group = (pull_row.get("category_code") or "").strip()
        if excel_group != pull_group:
            row_diffs.append(("item_group", excel_group, pull_group))

        excel_brand = (excel_row.get("Item Brand") or "").strip()
        pull_brand = (pull_row.get("brand_code") or "").strip()
        if excel_brand != pull_brand:
            row_diffs.append(("item_brand", excel_brand, pull_brand))

        excel_price = _excel_price(excel_row)
        pull_price = _pull_price(pull_row)
        if excel_price != pull_price:
            row_diffs.append(("price", str(excel_price), str(pull_price)))

        excel_active = is_active_from_manual_value(excel_row.get("Is Active"))
        pull_active = bool(pull_row.get("is_active"))
        if excel_active != pull_active:
            row_diffs.append(("is_active", excel_active, pull_active))

        if row_diffs:
            for field, excel_value, pull_value in row_diffs:
                differences.append(
                    {"item_code": item_code, "field": field, "excel": excel_value, "pull": pull_value}
                )
        else:
            matched += 1

    total = len(common_keys)
    return {
        "summary": {"total": total, "matched": matched, "different": total - matched},
        "differences": differences,
        "only_in_excel": only_in_excel,
        "only_in_pull": only_in_pull,
    }
