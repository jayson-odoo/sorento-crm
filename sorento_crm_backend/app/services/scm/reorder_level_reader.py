"""Read an AutoCount reorder level + reorder quantity listing.

> "the reorder level and reorder quantity ... are set at autocount, and they need to upload
>  to our system"

No sample export exists yet, so the headers are ASSUMED (user, 2026-08-10) and resolved
through `import_field_alias` under doc type ``reorder_level`` - when the real file arrives
spelled differently, the fix is alias rows, not a release. Same reader shape as the
supplier stock list: the header is the first row that resolves an item code, because these
exports carry title lines above the table.

`location` and `reorder_qty` are optional. AutoCount can keep one level per item with no
per-location split, and a file that says less still says something; a row with no location
lands as the product-wide level (`warehouse_id` NULL), which is already how
`scm.reorder_level` scopes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.services.import_alias_service import AliasResolver, normalize_header
from app.services.scm.outstanding_reader import RowProblem, sheet_rows

DOC_TYPE = "reorder_level"

#: Without an item code and a level the row cannot set anything.
_REQUIRED_COLUMNS = ("item_code", "reorder_level")


@dataclass
class LevelRow:
    row_number: int
    item_code: str
    reorder_level: float
    location: Optional[str] = None
    reorder_qty: Optional[float] = None


@dataclass
class LevelReadResult:
    rows: list[LevelRow] = field(default_factory=list)
    problems: list[RowProblem] = field(default_factory=list)
    unmapped_headers: list[str] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)
    total_rows: int = 0

    @property
    def ok(self) -> bool:
        return not self.missing_columns


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    s = str(value).strip()
    return s or None


def _number(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value).strip().replace(",", "").replace(" ", "")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def read_workbook(
    file_data: bytes, resolver: Optional[AliasResolver] = None, *, db: Optional[Session] = None
) -> LevelReadResult:
    """Parse the first sheet of an AutoCount reorder-level listing."""
    if resolver is None:
        if db is None:
            raise ValueError("read_workbook needs either a resolver or a session")
        resolver = AliasResolver.for_doc_type(db, DOC_TYPE)

    result = LevelReadResult()
    try:
        rows = sheet_rows(file_data)
    except Exception as exc:  # noqa: BLE001 - the message is for the person who uploaded it
        result.problems.append(RowProblem(0, f"could not read the workbook: {exc}"))
        result.missing_columns = list(_REQUIRED_COLUMNS)
        return result

    header_idx: Optional[int] = None
    col_field: dict[int, str] = {}
    all_rows = list(rows)
    for idx, raw in enumerate(all_rows):
        mapped: dict[int, str] = {}
        for pos, cell in enumerate(raw):
            f = resolver.field_for_header(cell)
            if f:
                mapped[pos] = f
        if "item_code" in mapped.values():
            header_idx = idx
            col_field = mapped
            result.unmapped_headers = [
                str(c).strip()
                for p, c in enumerate(raw)
                if p not in mapped and normalize_header(c)
            ]
            break

    if header_idx is None:
        result.missing_columns = list(_REQUIRED_COLUMNS)
        return result

    present = set(col_field.values())
    result.missing_columns = [c for c in _REQUIRED_COLUMNS if c not in present]
    if result.missing_columns:
        return result

    for offset, raw in enumerate(all_rows[header_idx + 1 :], start=header_idx + 2):
        values: dict[str, Any] = {}
        for pos, f in col_field.items():
            if pos < len(raw):
                values[f] = raw[pos]
        code = _text(values.get("item_code"))
        if code is None:
            # Spacing, a total line, or a note - only worth complaining about when the row
            # carries a level somebody meant to declare.
            if _number(values.get("reorder_level")) is not None:
                result.problems.append(RowProblem(offset, "no item code on a row with a level"))
            continue

        level = _number(values.get("reorder_level"))
        if level is None:
            # An item named with no level states nothing. NULL must not be written as 0:
            # a NULL level means "nobody set one" and the engine emits needs_level.
            result.problems.append(RowProblem(offset, f"{code}: no reorder level on the row"))
            continue

        result.total_rows += 1
        result.rows.append(
            LevelRow(
                row_number=offset,
                item_code=code,
                reorder_level=level,
                location=_text(values.get("location")),
                reorder_qty=_number(values.get("reorder_qty")),
            )
        )
    return result
