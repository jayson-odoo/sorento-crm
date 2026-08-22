"""Read a pre-load or packing list into one shipment per container block.

The file the supplier sends is not one table. It is several, one per container, stacked down a
single sheet, and each carries its own container number and bill of lading. The existing
packing-list path takes one shipment per POST from an n8n PDF extraction; nothing here read a
workbook carrying five of them, and that is the whole of AC-G1.

Two shapes are handled, because both exist in the wild and deciding which one this file is is
cheaper than asking:

  * **A container COLUMN.** One table, a `货柜号` column, and a block is a distinct value in it.
  * **Repeated header rows.** Several tables stacked, each preceded by labelled cells
    (`货柜号: XXXU1234567`, `提单号: ...`). A block starts at each header row, and the labels
    above it belong to it.

Neither container number nor bill of lading is required (AC-G2). At pre-load stage the
container has not been assigned yet, and a reader that insisted on one would reject the exact
file this feature exists to read. A block with no container number is still a block: it is
identified by its position and its contents, never by a field that is legitimately blank.

Every header spelling is already an `import_field_alias` row for doc type `packing_list`
(migration 311), so a supplier who renames a column is a row somebody inserts, not a release.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.services.import_alias_service import AliasResolver, normalize_header
from app.services.scm.currency_resolution import price_column_currency
from app.services.scm.outstanding_reader import RowProblem, sheet_rows

DOC_TYPE = "packing_list"

#: Without an item code and a quantity there is nothing to receive against.
_REQUIRED_COLUMNS = ("item_code", "qty")

#: Fields that describe the CONTAINER rather than a line. They may appear as columns in the
#: table or as labelled cells above it; either way they belong to the block, not the row.
_BLOCK_FIELDS = ("container_no", "bl_no")


@dataclass
class PackingLine:
    row_number: int
    item_code: str
    qty: float
    product_name: Optional[str] = None
    spec: Optional[str] = None
    cartons: Optional[float] = None
    net_weight: Optional[float] = None
    gross_weight: Optional[float] = None
    cbm_per_unit: Optional[float] = None
    cbm_total: Optional[float] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None
    brand: Optional[str] = None
    remark: Optional[str] = None
    #: Set only when the table carries a container COLUMN. It is what the row said, and it is
    #: used to split one table into blocks; the block is what owns the container from then on.
    container_no: Optional[str] = None


@dataclass
class PackingBlock:
    """One container's worth of the file: what it is called, and what is in it."""

    index: int
    container_no: Optional[str] = None
    bl_no: Optional[str] = None
    #: The row the block's table starts on. Part of its identity when it has no container
    #: number, and the only thing that distinguishes two otherwise identical pre-load blocks.
    header_row: int = 0
    lines: list[PackingLine] = field(default_factory=list)

    @property
    def total_qty(self) -> float:
        return sum(ln.qty for ln in self.lines)

    @property
    def total_cartons(self) -> Optional[float]:
        vals = [ln.cartons for ln in self.lines if ln.cartons is not None]
        return sum(vals) if vals else None


@dataclass
class PackingReadResult:
    blocks: list[PackingBlock] = field(default_factory=list)
    problems: list[RowProblem] = field(default_factory=list)
    unmapped_headers: list[str] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)
    total_rows: int = 0
    #: What the price columns say the money is (`RMB`, `单价(元)`). A HINT: the file states
    #: it, the service decides whether it wins (`currency_resolution.resolve_currency`).
    #: Without it a parsed unit price could only be stored with no currency, which is the
    #: same as not storing it (AC-P5.1).
    currency_hint: Optional[str] = None

    @property
    def ok(self) -> bool:
        """Readable when a header carrying what a receipt needs was found at all.

        Individual unusable rows do not condemn the file: a 34-line packing list with one blank
        model number should load 33, same as every other importer here.
        """
        return not self.missing_columns and bool(self.blocks)

    @property
    def line_count(self) -> int:
        return sum(len(b.lines) for b in self.blocks)


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


def _header_map(raw: list, resolver: AliasResolver) -> dict[int, str]:
    out: dict[int, str] = {}
    for pos, cell in enumerate(raw):
        f = resolver.field_for_header(cell)
        if f:
            out[pos] = f
    return out


def _is_header(mapped: dict[int, str], required: tuple[str, ...] = _REQUIRED_COLUMNS) -> bool:
    """A header is a row that names every column the document cannot be read without.

    Item code alone is not enough: a labelled cell reading `产品型号: SRTWC8613` resolves the
    same alias and would otherwise start a block of one row whose header is its own data.

    `required` is a parameter because the proforma reader shares this machinery and needs a
    price column on the header row before it will call a row a header (AC-P2.6).
    """
    values = set(mapped.values())
    return all(f in values for f in required)


def _labelled(
    raw: list, resolver: AliasResolver, fields: tuple[str, ...] = _BLOCK_FIELDS
) -> dict[str, str]:
    """Block-level values written as `label: value` or `label | value` in adjacent cells.

    Only the block fields are collected (`fields` is a parameter so the proforma reader can
    ask for its own five). A row that maps a label to nothing usable is ignored rather than
    recorded as blank, because a blank container number and an absent one have to stay the
    same thing here (AC-G2).

    A candidate value that is itself a LABEL - it resolves to a known header, or it simply
    ends in a colon - is not a value, and ends the search for this field. The row
    `提单号：` ... `Date 日期：` ... `31/07/2026` is a blank bill of lading followed by a
    date; without this the scan walked past the second label and read the date as the B/L
    number (AC-P2.4). The colon test is what corrects the PACKING-LIST channel, where
    `Date 日期：` resolves to nothing at all and so would not be recognised as a label.
    """
    out: dict[str, str] = {}
    for pos, cell in enumerate(raw):
        label = _text(cell)
        if not label:
            continue
        # `货柜号：XXXU123` in ONE cell is as common as two cells, so split on either colon.
        inline = None
        for sep in ("：", ":"):
            if sep in label:
                head, _, tail = label.partition(sep)
                f = resolver.field_for_header(head)
                if f in fields and _text(tail):
                    inline = (f, _text(tail))
                break
        if inline:
            out.setdefault(inline[0], inline[1])
            continue

        f = resolver.field_for_header(label)
        if f in fields:
            for nxt in raw[pos + 1:]:
                val = _text(nxt)
                if not val:
                    continue
                if not _is_label(val, resolver):
                    out.setdefault(f, val)
                break
    return out


def _is_label(value: str, resolver: AliasResolver) -> bool:
    """Is this cell a heading rather than somebody's answer to one?

    Three ways to be one, and all three occur in the files: it ends in a colon
    (`Date 日期：`), it resolves to a known header on its own (`货柜号`), or it is the
    one-cell `label：value` form (`货柜号：XXXU1234567`) whose head resolves. The last is why
    the test is not simply "does it resolve" - the whole cell resolves to nothing.
    """
    if value.rstrip().endswith((":", "：")):
        return True
    if resolver.field_for_header(value) is not None:
        return True
    for sep in ("：", ":"):
        if sep in value:
            return resolver.field_for_header(value.partition(sep)[0]) is not None
    return False


def _line_from(raw: list, col_field: dict[int, str], row_number: int) -> Optional[PackingLine]:
    vals: dict[str, Any] = {}
    for pos, f in col_field.items():
        if pos < len(raw):
            vals[f] = raw[pos]

    code = _text(vals.get("item_code"))
    qty = _number(vals.get("qty"))
    if not code or qty is None:
        return None

    cbm_total = _number(vals.get("cbm_total"))
    per_unit = _number(vals.get("cbm_per_unit"))
    # The supplier writes both columns and fills only one of them about half the time. Deriving
    # per-unit from the line total is the same fallback the stock list uses; it is never zeroed,
    # because an item nobody measured must not look like an item that takes no space.
    if per_unit is None and cbm_total is not None and qty:
        per_unit = round(cbm_total / qty, 6)

    return PackingLine(
        row_number=row_number,
        item_code=code,
        qty=qty,
        product_name=_text(vals.get("product_name")),
        spec=_text(vals.get("spec")),
        cartons=_number(vals.get("cartons")),
        net_weight=_number(vals.get("net_weight")),
        gross_weight=_number(vals.get("gross_weight")),
        cbm_per_unit=per_unit,
        cbm_total=cbm_total,
        unit_price=_number(vals.get("unit_price")),
        amount=_number(vals.get("amount")),
        brand=_text(vals.get("brand")),
        remark=_text(vals.get("remark")),
        container_no=_text(vals.get("container_no")),
    )


def read_workbook(
    file_data: bytes, resolver: Optional[AliasResolver] = None, *, db: Optional[Session] = None
) -> PackingReadResult:
    """Parse a packing list into blocks.

    `resolver` is injectable so parsing can be tested against a file alone, with no database in
    the picture; `db` builds one from the alias table for the normal path.
    """
    if resolver is None:
        if db is None:
            raise ValueError("read_workbook needs either a resolver or a session")
        resolver = AliasResolver.for_doc_type(db, DOC_TYPE)

    result = PackingReadResult()
    try:
        all_rows = list(sheet_rows(file_data))
    except Exception as exc:  # noqa: BLE001 - the message is for the person who uploaded it
        result.problems.append(RowProblem(0, f"could not read the workbook: {exc}"))
        result.missing_columns = list(_REQUIRED_COLUMNS)
        return result

    result.total_rows = len(all_rows)
    pending: dict[str, str] = {}
    current: Optional[PackingBlock] = None
    col_field: dict[int, str] = {}
    saw_header = False

    for idx, raw in enumerate(all_rows):
        row_number = idx + 1
        mapped = _header_map(raw, resolver)

        if _is_header(mapped):
            if not saw_header:
                result.unmapped_headers = [
                    str(c).strip()
                    for p, c in enumerate(raw)
                    if p not in mapped and normalize_header(c)
                ]
                result.currency_hint = price_column_currency(raw, mapped)
            saw_header = True
            col_field = mapped
            current = PackingBlock(
                index=len(result.blocks) + 1,
                container_no=pending.get("container_no"),
                bl_no=pending.get("bl_no"),
                header_row=row_number,
            )
            result.blocks.append(current)
            pending = {}
            continue

        if not saw_header:
            pending.update(_labelled(raw, resolver))
            continue

        line = _line_from(raw, col_field, row_number)
        if line is None:
            # Not a line. It may be the labels introducing the NEXT block, which is how a
            # stacked file separates one container from the next.
            found = _labelled(raw, resolver)
            if found:
                pending.update(found)
            continue

        if current is not None:
            current.lines.append(line)

    if not saw_header:
        result.missing_columns = list(_REQUIRED_COLUMNS)
        return result

    present = set(col_field.values())
    result.missing_columns = [c for c in _REQUIRED_COLUMNS if c not in present]
    if result.missing_columns:
        return result

    result.blocks = _split_by_container_column(result.blocks, col_field)
    # A header with no lines under it is not a container; it is the shape of an empty template.
    result.blocks = [b for b in result.blocks if b.lines]
    for i, b in enumerate(result.blocks, start=1):
        b.index = i
    return result


def _split_by_container_column(
    blocks: list[PackingBlock], col_field: dict[int, str]
) -> list[PackingBlock]:
    """The other shape: one table with a container column, so a block is a distinct value.

    Only applies when the table actually HAS that column and more than one value appears in it.
    A single-container file stays one block whichever shape it is written in, which is what
    keeps the two readings from disagreeing about the simple case.
    """
    if "container_no" not in set(col_field.values()):
        return blocks

    out: list[PackingBlock] = []
    for block in blocks:
        by_container: dict[str, PackingBlock] = {}
        order: list[str] = []
        for ln in block.lines:
            key = (ln.container_no or block.container_no or "") or ""
            if key not in by_container:
                by_container[key] = PackingBlock(
                    index=0,
                    container_no=key or block.container_no,
                    bl_no=block.bl_no,
                    header_row=block.header_row,
                )
                order.append(key)
            by_container[key].lines.append(ln)
        out.extend(by_container[k] for k in order)
    return out
