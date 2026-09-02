"""Read a supplier's stock list into rows the Loading Plan can measure.

The file is the supplier's own, in their own Chinese: 型号 for the model, 包装好库存 for what
is packed, 空瓷 for the unfinished bodies, 体积(cbm) per unit and 总体积(cbm) for the line.
Every one of those spellings is already an `import_field_alias` row (migration 311), so the
headers are resolved through the alias table and a supplier who renames a column is a row
somebody inserts, not a release.

Two quantities, never summed. Packed stock can go on a container this week; unfinished stock
is a request to the supplier's production line. Adding them would put a container's worth of
things that do not exist yet onto a loading plan.

Volume falls back once: when the file gives a line TOTAL but no per-unit figure, per-unit is
the total over the quantity - the supplier writes both and only sometimes fills the first.
When neither is present the volume stays None, which the allocator treats as unmeasured. It
is never zero: an item nobody measured must not look like an item that takes no space.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.services.import_alias_service import AliasResolver, normalize_header
from app.services.scm.outstanding_reader import RowProblem, sheet_rows

DOC_TYPE = "supplier_inventory"

#: Without an item code and a packed figure the row cannot be placed on a container at all.
_REQUIRED_COLUMNS = ("item_code", "qty_packed")


@dataclass
class InventoryRow:
    row_number: int
    item_code: str
    qty_packed: float = 0.0
    qty_unfinished: float = 0.0
    cbm_per_unit: Optional[float] = None
    product_name: Optional[str] = None
    brand: Optional[str] = None
    spec: Optional[str] = None
    remark: Optional[str] = None


@dataclass
class InventoryReadResult:
    rows: list[InventoryRow] = field(default_factory=list)
    problems: list[RowProblem] = field(default_factory=list)
    unmapped_headers: list[str] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)
    total_rows: int = 0
    #: The first non-empty text cell above the header row (AC-G3), so a preview can warn
    #: when the sheet's own title names a different supplier than the one picked in the
    #: dialog. `None` when the header sits on row 1 - the file said nothing above its table.
    letterhead: Optional[str] = None

    @property
    def ok(self) -> bool:
        """Readable when the header carries what a container decision needs.

        Individual unusable rows do not condemn the file, for the same reason as every other
        importer here: a 300-line stock list with 2 blank model numbers should load 298.
        """
        return not self.missing_columns


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    s = str(value).strip()
    return s or None


def _number(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
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
) -> InventoryReadResult:
    """Parse the first sheet of a supplier stock list.

    `resolver` is injectable so the parsing can be tested against a file alone, with no
    database in the picture; `db` builds one from the alias table for the normal path.
    """
    if resolver is None:
        if db is None:
            raise ValueError("read_workbook needs either a resolver or a session")
        resolver = AliasResolver.for_doc_type(db, DOC_TYPE)

    result = InventoryReadResult()
    try:
        rows = sheet_rows(file_data)
    except Exception as exc:  # noqa: BLE001 - the message is for the person who uploaded it
        result.problems.append(RowProblem(0, f"could not read the workbook: {exc}"))
        result.missing_columns = list(_REQUIRED_COLUMNS)
        return result

    # The header is not always the first row: these files carry a title line and sometimes a
    # blank one above it. So the header is the first row that resolves at least the item code,
    # rather than row 1 by decree.
    header_idx: Optional[int] = None
    col_field: dict[int, str] = {}
    all_rows = list(rows)
    for idx, raw in enumerate(all_rows):
        mapped = {}
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

        if result.letterhead is None:
            for cell in raw:
                cell_text = _text(cell)
                if cell_text:
                    result.letterhead = cell_text
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
            # A blank model number is the sheet's own spacing, a total line, or a note. Only
            # worth complaining about when the row carries a quantity, which makes it stock
            # somebody meant to declare.
            if _number(values.get("qty_packed")) or _number(values.get("qty_unfinished")):
                result.problems.append(RowProblem(offset, "no model number on a row with stock"))
            continue

        result.total_rows += 1
        packed = _number(values.get("qty_packed")) or 0.0
        unfinished = _number(values.get("qty_unfinished")) or 0.0
        per_unit = _number(values.get("cbm_per_unit"))
        if per_unit is None:
            total = _number(values.get("cbm_total"))
            basis = packed + unfinished
            if total is not None and basis > 0:
                per_unit = round(total / basis, 6)

        result.rows.append(
            InventoryRow(
                row_number=offset,
                item_code=code,
                qty_packed=packed,
                qty_unfinished=unfinished,
                cbm_per_unit=per_unit,
                product_name=_text(values.get("product_name")),
                brand=_text(values.get("brand")),
                spec=_text(values.get("spec")),
                remark=_text(values.get("remark")),
            )
        )

    return result
