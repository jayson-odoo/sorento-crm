"""Saved column mappings for the AutoCount pull compare (PLAN-do-compare-mapping.md).

A mapping names the sheet to read and, per Excel column, a transform and the Sorento field it
feeds. The fixed lists below are the whole vocabulary: no formulas. A kind with no saved row
falls back to `DEFAULT_MAPPINGS` (databases built by `create_all` carry no migration seed).
"""
from __future__ import annotations

import copy
from typing import Optional

from sqlalchemy.orm import Session

from app.models.autocount_compare_mapping import AutocountCompareMapping
from app.services.error_handler import AppException

KINDS = ("order_listing", "order_tracking")
TRANSFORMS = ("text", "number", "money", "date", "percent_text", "percent_fraction", "cancel_flag")
FIELDS_BY_KIND: dict[str, tuple[str, ...]] = {
    "order_listing": ("doc_no", "doc_date", "item_code", "location", "qty", "unit_price",
                      "discount", "total_ex"),
    "order_tracking": ("doc_no", "doc_date", "debtor_code", "cancel"),
}
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "order_listing": ("doc_no", "item_code"),
    "order_tracking": ("doc_no",),
}
#: The `kind` a compare `source` reads.
KIND_BY_SOURCE = {"lines": "order_listing", "headers": "order_tracking"}
_MAX_COLUMNS = 100


def _cols(triples: tuple[tuple[str, str, str], ...]) -> list[dict]:
    return [{"excel_header": h, "transform": t, "field": f} for h, t, f in triples]


DEFAULT_MAPPINGS: dict[str, dict] = {
    "order_listing": {"sheet_name": "Master", "columns": _cols((
        ("Doc No", "text", "doc_no"), ("Doc Date", "date", "doc_date"),
        ("Item Code", "text", "item_code"), ("Location", "text", "location"),
        ("Qty", "number", "qty"), ("Unit Price", "money", "unit_price"),
        ("Discount", "percent_text", "discount"), ("Total (Ex)", "money", "total_ex"),
    ))},
    "order_tracking": {"sheet_name": "Master", "columns": _cols((
        ("Doc. No.", "text", "doc_no"), ("Date", "date", "doc_date"),
        ("Debtor Code", "text", "debtor_code"), ("Cancel", "cancel_flag", "cancel"),
    ))},
}


def _unknown_kind(kind: str) -> AppException:
    return AppException(status_code=404, message=f"Unknown mapping kind '{kind}'.", code="UNKNOWN_KIND")


def _invalid(message: str) -> AppException:
    return AppException(status_code=422, message=message, code="INVALID_MAPPING")


def get_mapping(db: Session, kind: str) -> dict:
    """`{sheet_name, columns}` for a kind: the saved row, else the in-code default."""
    if kind not in KINDS:
        raise _unknown_kind(kind)
    row = db.query(AutocountCompareMapping).filter(AutocountCompareMapping.kind == kind).first()
    if row is None:
        return copy.deepcopy(DEFAULT_MAPPINGS[kind])
    return {"sheet_name": row.sheet_name, "columns": copy.deepcopy(row.columns)}


def list_mappings(db: Session) -> list[dict]:
    return [{"kind": kind, **get_mapping(db, kind)} for kind in KINDS]


def validate_columns(kind: str, columns: list[dict]) -> list[dict]:
    """The cleaned column rows, or a 422 `INVALID_MAPPING` naming the first fault."""
    allowed = FIELDS_BY_KIND[kind]
    if len(columns) > _MAX_COLUMNS:
        raise _invalid(f"At most {_MAX_COLUMNS} columns.")
    cleaned: list[dict] = []
    seen: set[str] = set()
    for col in columns:
        header = str((col or {}).get("excel_header") or "").strip()
        transform = (col or {}).get("transform")
        field = (col or {}).get("field")
        if not header:
            raise _invalid("Every row needs an Excel column name.")
        if transform not in TRANSFORMS:
            raise _invalid(f"Unknown transform '{transform}'.")
        if field not in allowed:
            raise _invalid(f"'{field}' is not a field of this workbook.")
        if field in seen:
            raise _invalid(f"'{field}' is mapped more than once.")
        seen.add(field)
        cleaned.append({"excel_header": header, "transform": transform, "field": field})
    for required in REQUIRED_FIELDS[kind]:
        if required not in seen:
            raise _invalid(f"'{required}' must be mapped.")
    return cleaned


def save_mapping(
    db: Session, kind: str, sheet_name: str, columns: list[dict], user_id: Optional[str]
) -> dict:
    """Validate, then upsert the kind's row. Nothing is written when validation fails."""
    if kind not in KINDS:
        raise _unknown_kind(kind)
    sheet = str(sheet_name or "").strip()
    if not sheet or len(sheet) > 100:
        raise _invalid("A sheet name is required.")
    cleaned = validate_columns(kind, columns)
    row = db.query(AutocountCompareMapping).filter(AutocountCompareMapping.kind == kind).first()
    if row is None:
        row = AutocountCompareMapping(kind=kind, sheet_name=sheet, columns=cleaned, updated_by=user_id)
        db.add(row)
    else:
        row.sheet_name = sheet
        row.columns = cleaned
        row.updated_by = user_id
    db.commit()
    return {"sheet_name": sheet, "columns": cleaned}
