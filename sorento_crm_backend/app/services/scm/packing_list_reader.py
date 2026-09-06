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

import re
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
#: `seal_no` and `consignee` are R13 additions (purchasing consolidation batch, lane C).
_BLOCK_FIELDS = ("container_no", "bl_no", "seal_no", "consignee")

#: A cell may state TWO block fields side by side (`箱号:WHSU6243088 / 封签号:WHA4528193`,
#: the Jiexia sample). Split on the supplier's own separator BEFORE the label test, so both
#: are read rather than only the first (AC-F9). The ASCII slash needs whitespace on BOTH
#: sides to count - `SZX/2026/001` (a bill of lading) and `31/07/2026` (a date) are one
#: value each, and matching a bare `/` inside them split a B/L number into three pieces and
#: a date into a day, a month and a year, none of which resolve to anything (review round 1,
#: purchasing consolidation batch lane C). The fullwidth `／` still splits regardless of
#: spacing - nothing in these documents ever uses it AS a value, only as a separator.
_MULTI_SEP = re.compile(r"\s+/\s+|／")

#: The label that means "everything from here to the end of the sheet is a footer note",
#: not a block field or a line - `备注：` on the Jiexia packing list, captured verbatim.
_FOOTER_FIELD = "remark"

#: Title-cell markers (R12): what marks a cell as the DOCUMENT'S OWN TITLE rather than a
#: real answer to anything it might otherwise resolve as. Defined here, not in
#: `supplier_document_service.classify()` (which imports these), because that module
#: already imports FROM this one and the reverse would cycle - and `_shipper_of` below
#: needs the exact same list `classify()` decides PI-vs-PL with, so a title row is never
#: read as the letterhead either (S1, review round 1). Bare "INVOICE" is deliberately NOT
#: a marker: the packing list's own labelled cell states "INVOICE NO.: ..." (the PI number
#: both documents share), which would otherwise misclassify every packing list.
_PI_TITLE_MARKERS = ("发票", "PROFORMA INVOICE")
_PL_TITLE_MARKERS = ("装箱单", "PACKING LIST")

#: A totals row states a description but no item code - the same shape `_note_from` keeps
#: as an accessory note, but it is arithmetic about the block, not something inside it
#: (`SUB TOTAL 1*40HQ` in the Jiexia packing list's own description column). Matched loosely
#: rather than by a header label, because this text sits where a description would, not in
#: a labelled cell.
_TOTALS_ROW_RE = re.compile(r"^(SUB[\s-]*)?TOTAL\b", re.IGNORECASE)


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
    #: The factory's OWN model number (`洁厦型号` / `JIEXIA MODEL`), distinct from `item_code`
    #: (`客户型号` - OUR catalogue code, a separate column on the Jiexia documents). Resolved
    #: but not consumed by anything yet - kept so a future preview can show it beside ours.
    supplier_code: Optional[str] = None
    #: Set only when the table carries a container COLUMN. It is what the row said, and it is
    #: used to split one table into blocks; the block is what owns the container from then on.
    container_no: Optional[str] = None


@dataclass
class PackingBlock:
    """One container's worth of the file: what it is called, and what is in it."""

    index: int
    container_no: Optional[str] = None
    bl_no: Optional[str] = None
    #: The container's seal number (`封签号`, R13). Per block, never carried over: two
    #: containers in one file never share a seal.
    seal_no: Optional[str] = None
    #: Who is billed (`客户：`, R13). Stated once, above the first block, and carried onto
    #: every later block in the same file - a packing list never bills two customers.
    consignee: Optional[str] = None
    #: The row the block's table starts on. Part of its identity when it has no container
    #: number, and the only thing that distinguishes two otherwise identical pre-load blocks.
    header_row: int = 0
    lines: list[PackingLine] = field(default_factory=list)
    #: A data row that named something but stated no usable quantity - the accessory lines a
    #: packing list writes around its coded rows (`840 水箱空瓷：1个`). Kept against the block
    #: as a note rather than dropped or miscounted as a line (AC-F3).
    notes: list[str] = field(default_factory=list)

    @property
    def total_qty(self) -> float:
        return sum(ln.qty for ln in self.lines)

    @property
    def total_cartons(self) -> Optional[float]:
        vals = [ln.cartons for ln in self.lines if ln.cartons is not None]
        return sum(vals) if vals else None

    @property
    def total_amount(self) -> Optional[float]:
        vals = [ln.amount for ln in self.lines if ln.amount is not None]
        return sum(vals) if vals else None

    @property
    def total_cbm(self) -> Optional[float]:
        vals = [ln.cbm_total for ln in self.lines if ln.cbm_total is not None]
        return round(sum(vals), 4) if vals else None


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
    #: The letterhead company (R13/R14) - the first non-empty cell of ROW 0, when it resolves
    #: to no known field and is not itself a label. Applies to the WHOLE file: one packing
    #: list is written by one factory, however many containers it lists.
    shipper: Optional[str] = None
    #: Everything from the `备注：` label row to the end of the sheet, verbatim (R13). File
    #: level for the same reason `shipper` is: the footer describes the shipment, not one
    #: container in it.
    footer_notes: Optional[str] = None

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

    A cell may ALSO state two of these fields side by side (`箱号:WHSU6243088 /
    封签号:WHA4528193`, the Jiexia sample) - split on the supplier's own separator before the
    inline colon test, so both land rather than only the first half of the cell (AC-F9).

    The split is refused unless what follows the separator carries a label of its own
    (a colon): `_MULTI_SEP` only fires on a slash with whitespace either side now, but a
    cell like `货柜号：ABCU1 / loaded first` would still match that shape without ALSO
    checking for a second label, and "loaded first" is a note, not a second answer
    (review round 1, purchasing consolidation batch lane C).
    """
    out: dict[str, str] = {}
    for pos, cell in enumerate(raw):
        label = _text(cell)
        if not label:
            continue
        split = [p for p in _MULTI_SEP.split(label) if p.strip()]
        if len(split) > 1 and any((":" in p or "：" in p) for p in split[1:]):
            parts = split
        else:
            parts = [label]
        matched_inline = False
        for part in parts:
            # `货柜号：XXXU123` in ONE cell is as common as two cells, so split on either colon.
            inline = None
            for sep in ("：", ":"):
                if sep in part:
                    head, _, tail = part.partition(sep)
                    f = resolver.field_for_header(head)
                    if f in fields and _text(tail):
                        inline = (f, _text(tail))
                    break
            if inline:
                out.setdefault(inline[0], inline[1])
                matched_inline = True
        if matched_inline:
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
        supplier_code=_text(vals.get("supplier_code")),
        container_no=_text(vals.get("container_no")),
    )


def _note_from(raw: list, col_field: dict[int, str]) -> Optional[str]:
    """A data row that named something but stated no usable quantity.

    The four accessory lines the Jiexia packing list writes around its coded rows
    (`840 水箱空瓷：1个`, `纸箱：2个`) fail `_line_from` - some for lacking an item code, one
    for lacking a quantity even though it names one (AC-F3) - and both are the same answer
    here: whatever the row's description column says, kept as a note against the block
    rather than dropped on the floor or miscounted as a line.
    """
    vals: dict[str, Any] = {}
    for pos, f in col_field.items():
        if pos < len(raw):
            vals[f] = raw[pos]
    note = _text(vals.get("product_name")) or _text(vals.get("description"))
    if note and _TOTALS_ROW_RE.match(note.strip()):
        return None
    return note


def _shipper_of(raw: list, resolver: AliasResolver) -> Optional[str]:
    """The letterhead company, from the FIRST non-empty cell of row 0.

    Only when that cell resolves to no known field and is not itself a label - a file whose
    row 0 is already the address block's first line, or the header row itself, states no
    shipper this way and gets none, rather than a guess (R13/R14).

    Nor when it IS the document's own title (`马来西亚 PACKING LIST`, the Kailu fixture): a
    title carries no company name at all, and the same title-cell markers
    `supplier_document_service.classify()` decides PI-vs-PL with are the ones that say so
    here too (S1, review round 1).
    """
    first = next((c for c in raw if _text(c)), None)
    text = _text(first)
    if not text:
        return None
    if resolver.field_for_header(text) is not None or _is_label(text, resolver):
        return None
    upper = text.upper()
    if any(marker in upper for marker in (*_PI_TITLE_MARKERS, *_PL_TITLE_MARKERS)):
        return None
    return text


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
    #: A label seen while `current` ALREADY has lines describes the NEXT container, not the
    #: one just filled - but it must not become a new block until the row after it turns
    #: out NOT to be a repeated header row (the Jinbaichuan/Kailu shape this reader already
    #: handled): a header immediately following the label is what actually starts the next
    #: block, via `pending`, exactly as before. Set False whenever `pending` is consumed.
    pending_is_new_block = False
    current: Optional[PackingBlock] = None
    col_field: dict[int, str] = {}
    saw_header = False
    # Carried across blocks WITHIN one file - a packing list bills one customer however many
    # containers it lists, even though the label stating so appears only once (R13).
    sticky_consignee: Optional[str] = None
    in_footer = False
    footer_lines: list[str] = []

    def _apply_pending() -> None:
        """Resolve whatever `_labelled` has accumulated since the last block, right before
        the first real content (a line or a note) that needs to know which block it is on.

        A NEW block only when the CURRENT one already has lines AND the label(s) arrived
        with no repeated header row in between (`pending_is_new_block`) - the third shape
        this reader handles, a labelled row splitting one table with no header of its own.
        Otherwise the pending fields are the CURRENT block's own identity, still being
        filled in between its header row and its first line.
        """
        nonlocal current, pending, pending_is_new_block, sticky_consignee
        if not pending:
            return
        if pending_is_new_block and current is not None and current.lines:
            current = PackingBlock(
                index=len(result.blocks) + 1,
                container_no=pending.get("container_no"),
                bl_no=pending.get("bl_no"),
                seal_no=pending.get("seal_no"),
                consignee=pending.get("consignee") or sticky_consignee,
                header_row=row_number,
            )
            result.blocks.append(current)
        elif current is not None:
            if pending.get("container_no"):
                current.container_no = pending["container_no"]
            if pending.get("bl_no"):
                current.bl_no = pending["bl_no"]
            if pending.get("seal_no"):
                current.seal_no = pending["seal_no"]
            if pending.get("consignee"):
                current.consignee = pending["consignee"]
        if current is not None and current.consignee:
            sticky_consignee = current.consignee
        pending = {}
        pending_is_new_block = False

    for idx, raw in enumerate(all_rows):
        row_number = idx + 1

        if idx == 0 and result.shipper is None:
            result.shipper = _shipper_of(raw, resolver)

        if in_footer:
            text = "; ".join(t for c in raw if (t := _text(c)))
            if text:
                footer_lines.append(text)
            continue

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
                seal_no=pending.get("seal_no"),
                consignee=pending.get("consignee") or sticky_consignee,
                header_row=row_number,
            )
            result.blocks.append(current)
            if current.consignee:
                sticky_consignee = current.consignee
            pending = {}
            pending_is_new_block = False
            continue

        if not saw_header:
            pending.update(_labelled(raw, resolver))
            continue

        # A `备注：` label row: everything from here to the end of the sheet is a footer
        # note, never a line or the next block's identity (R13).
        first_text = next((_text(c) for c in raw if _text(c)), None)
        if first_text and resolver.field_for_header(first_text) == _FOOTER_FIELD:
            in_footer = True
            footer_lines.append(first_text)
            continue

        line = _line_from(raw, col_field, row_number)
        if line is None:
            # Not a line. It may be the label(s) introducing the NEXT container - the third
            # shape this reader handles (module docstring): one header table, and a new
            # block starts at each LABELLED row rather than at a repeated header. Held in
            # `pending` rather than acted on immediately: a REPEATED header row right after
            # this one is what actually starts the block (existing shape, above), and
            # deciding here too would create it twice.
            found = _labelled(raw, resolver)
            if found:
                pending.update(found)
                if current is not None and current.lines:
                    pending_is_new_block = True
                continue
            note = _note_from(raw, col_field)
            if note is not None:
                # A note row does NOT decide whether `pending` starts a new block - only a
                # real header or line does (the checks above/below). Draining it here, while
                # `pending_is_new_block` is still open, minted a block with the note and no
                # lines that the final `b.lines` filter then throws away, taking the
                # container number that belonged to the NEXT header with it (B2, review
                # round 1). Held instead: the note lands on the CURRENT block, same as any
                # other accessory line found before its container is confirmed.
                if not pending_is_new_block:
                    _apply_pending()
                if current is not None:
                    current.notes.append(note)
            continue

        _apply_pending()
        if current is not None:
            current.lines.append(line)

    result.footer_notes = "\n".join(footer_lines) if footer_lines else None

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
                    # The table carries ONE seal/consignee/note set, stated once above the
                    # whole table rather than per container column value - carried onto
                    # EVERY split-off block rather than only the first (S2, review round 1).
                    seal_no=block.seal_no,
                    consignee=block.consignee,
                    notes=list(block.notes),
                    header_row=block.header_row,
                )
                order.append(key)
            by_container[key].lines.append(ln)
        out.extend(by_container[k] for k in order)
    return out
