"""L1 - the purchase-history channel's ONE reader, over two file shapes.

AutoCount exports the same business in two layouts and the client sends both.

* **The banded report** (`Purchase Order Listing With Detail`): two label rows, then blocks
  of one order header followed by its lines. `po_listing_reader` reads it, and nothing here
  changes how.
* **The structured extract** (`PO & SPO 2023.xlsx`): one flat sheet, 27 columns, one row per
  line, 27,192 of them, holding BOTH document families at once.

Which one arrived is decided by **header shape**, not by filename and not by an operator
choosing a `kind` on the upload screen. The structured sheet states `Doc No`, `Item Code`
and `Qty` in ONE row; the banded report states them too, but never in the same row - its
`Doc No` is in the header band and its `Item Code` in the line band - so requiring all three
together is what separates them and cannot be satisfied by accident.

Both shapes come back as the same `PoListingResult`, so the write path below has one input
type and the two layouts cannot drift apart in what they are able to express.

What the structured extract states that the banded report cannot:

* the **stock location** per line, so history lands in the warehouse it was bought for;
* the **sales order** per line (`FromSODocList`), where the banded report carries only an
  order-level `**SO:174830**` note that cannot say which line it describes;
* both **document families** in one file, told apart by the Doc No prefix (`doc_family`).

What it does NOT state, and is therefore not invented here: a creditor CODE (only the name),
a currency, a purchase price, and a line number. The last one is why line identity is
positional - see the comment where the ordinal is assigned.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from app.services import import_outcome_codes as oc
from app.services.import_alias_service import AliasResolver, normalize_header
from app.services.scm.outstanding_reader import _to_date, all_sheet_rows
from app.services.scm.po_listing_reader import (
    FAMILY_PO,
    FAMILY_SPO,
    LAYOUT_STRUCTURED,
    PoListingLine,
    PoListingOrder,
    PoListingResult,
    _is_charge_code,
    doc_family,
    read_po_listing,
)

__all__ = [
    "FAMILY_PO",
    "FAMILY_SPO",
    "STRUCTURED_DOC_TYPE",
    "doc_family",
    "read_purchase_history",
    "read_structured_purchase_history",
]

#: The alias table's doc type for the structured extract's 27 headers (migration 358).
STRUCTURED_DOC_TYPE = "po_spo_history"

#: The three fields that must ALL resolve out of one row for that row to be this format's
#: header. Fewer would match the banded report's line band; more would make the detection
#: fail on an export that merely dropped a column we do not read.
_STRUCTURED_SIGNATURE = ("po_number", "item_code", "qty_ordered")

#: How far into the sheet a header row may sit. The captain's export puts it on row 1; the
#: allowance is for an export saved with a title row above it, which AutoCount does elsewhere.
_HEADER_SEARCH_ROWS = 5


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _number(value: Any) -> Optional[float]:
    if value is None or isinstance(value, (date, datetime)):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value).strip().replace(",", "")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _as_date(value: Any) -> Optional[date]:
    """A cell as a date, through the outstanding reader's parser.

    Not a second copy of it: that one reads day-first (`03/08/2026` is 3 August, because
    these are Malaysian exports) and getting it the other way round moves a purchase five
    months. The captain's export writes real datetimes, but an export saved through a text
    format writes strings, and the purchase DATE is the whole reason this channel exists.
    """
    return _to_date(value)


def _header_columns(row: tuple, resolver: AliasResolver) -> Optional[dict[int, str]]:
    """This row's column -> canonical field map, if the row IS the structured header."""
    columns: dict[int, str] = {}
    for index, cell in enumerate(row):
        field = resolver.field_for_header(cell)
        if field is not None:
            columns[index] = field
    if all(f in columns.values() for f in _STRUCTURED_SIGNATURE):
        return columns
    return None


def _find_header(rows: list[tuple], resolver: AliasResolver):
    """The structured header row: (1-based row number, column -> field). None when absent."""
    for row_number, row in enumerate(rows[:_HEADER_SEARCH_ROWS], start=1):
        columns = _header_columns(row, resolver)
        if columns is not None:
            return row_number, columns
    return None


def read_purchase_history(file_data: bytes, resolver: AliasResolver) -> PoListingResult:
    """Read a purchase-history book, whichever of the two shapes it is in.

    The single entry point the channel calls. The workbook is opened ONCE and the detected
    header row is handed to the structured parser rather than re-found by it: 27,192 rows is
    enough that parsing the file twice to answer "which file is this" is a real cost, and two
    separate scans could in principle disagree about which row the header was.

    An unfamiliar file still ends up in the banded reader, which says out loud that it is not
    a Purchase Order Listing rather than half-parsing something it does not understand.
    """
    try:
        rows = all_sheet_rows(file_data)
    except Exception as exc:  # noqa: BLE001 - surfaced, never swallowed
        result = PoListingResult()
        result.problems.append(f"this file could not be read: {exc}")
        return result

    found = _find_header(rows, resolver)
    if found is None:
        return read_po_listing(file_data)
    header_row_number, columns = found
    return _read_structured(rows, header_row_number, columns)


def read_structured_purchase_history(
    file_data: bytes, resolver: AliasResolver
) -> PoListingResult:
    """Parse the flat 27-column extract, for a caller that already knows it has one."""
    result = PoListingResult(layout=LAYOUT_STRUCTURED)
    try:
        rows = all_sheet_rows(file_data)
    except Exception as exc:  # noqa: BLE001 - surfaced, never swallowed
        result.problems.append(f"this file could not be read: {exc}")
        return result

    found = _find_header(rows, resolver)
    if found is None:
        result.problems.append(
            "this file does not look like a PO/SPO history extract: no header row carrying "
            "Doc No, Item Code and Qty was found."
        )
        return result
    return _read_structured(rows, *found)


def _read_structured(rows: list[tuple], header_row_number: int,
                     columns: dict[int, str]) -> PoListingResult:
    """Turn the rows below a known header into orders and their lines.

    Every non-blank row leaves this function exactly once: as a line, on
    `layout_row_numbers`, or on `problem_row_codes`. A row that left as none of the three
    would be a row the queued job cannot account for, and 925 rows of the captain's own book
    state no item code at all: 924 captions inside a document, plus the grand-total row at
    the foot, which states no document either.
    """
    result = PoListingResult(layout=LAYOUT_STRUCTURED)
    header = rows[header_row_number - 1]
    result.unmapped_headers = [
        _text(cell)
        for index, cell in enumerate(header)
        if index not in columns and normalize_header(cell)
    ]

    orders: dict[str, PoListingOrder] = {}
    ordinals: dict[str, int] = {}

    for row_number, row in enumerate(rows[header_row_number:], start=header_row_number + 1):
        if not any(c is not None and _text(c) for c in row):
            # A wholly empty row states nothing, so there is nothing to report about it.
            continue
        result.total_rows += 1
        # First NON-EMPTY wins where two headers resolve to one field, which is the rule
        # `AliasResolver.index_row` already applies: a file carrying both `Description` and
        # `Item Description` must not depend on column order to pick the populated one.
        record: dict[str, Any] = {}
        for index, value in enumerate(row):
            field = columns.get(index)
            if field is None:
                continue
            if field not in record or _text(record[field]) == "":
                record[field] = value

        doc_number = _text(record.get("po_number"))
        item_code = _text(record.get("item_code"))
        qty = _number(record.get("qty_ordered"))

        if not doc_number:
            # The grand-total row at the foot of the export: real figures, no document. Its
            # own code rather than silence, because a row the job cannot explain is a row
            # somebody goes looking for a bug about.
            result.problem_row_codes[row_number] = oc.MISSING_DOC_NO
            continue
        if not item_code:
            # A caption inside a document ("EXTRA LOADING : "), which AutoCount writes with
            # the document's own header values and no item. Never a line, never a failure.
            result.layout_row_numbers.append(row_number)
            continue
        if qty is None:
            result.problem_row_codes[row_number] = oc.MISSING_QUANTITY
            continue

        order = orders.get(doc_number)
        if order is None:
            # The document's own facts are repeated on every one of its rows, so the FIRST
            # row of the document is what writes them. First non-empty wins over last: a
            # trailing blank cell cannot erase a stated date.
            order = PoListingOrder(
                po_number=doc_number,
                order_date=_as_date(record.get("po_date")),
                # This export names the creditor and never its code. Left empty rather than
                # derived from the name: `suppliers.supplier_code` is unique and NOT NULL,
                # so a code invented here would become a supplier nobody can reconcile.
                supplier_code="",
                supplier_name=_text(record.get("supplier_name")),
                # Not stated. `Standard Price` is the item's own standard price, not what
                # this document paid, so no currency and no cost can be read from this file.
                currency="",
                total=None,
                local_total=None,
                source_row=row_number,
            )
            orders[doc_number] = order
            result.orders.append(order)

        # A line in this file has no number of its own, so identity within a document is
        # POSITIONAL - the n-th line of the document, in file order. That is the same rule
        # the outstanding book uses (UAC AC-2.2) and for the same reason: re-reading the same
        # file reproduces the same positions, so a re-upload rewrites rather than doubles. A
        # content key would not do - `202301-S0001` names `CB4924-CR` twice, on two different
        # containers, and those are two real lines rather than one line stated twice.
        ordinals[doc_number] = ordinals.get(doc_number, 0) + 1
        order.lines.append(
            PoListingLine(
                line_no=ordinals[doc_number],
                item_code=item_code,
                description=_text(record.get("item_description")),
                uom="",
                qty_ordered=qty,
                unit_price=None,
                amount=None,
                local_amount=None,
                # Decided by the same code test the banded reader uses, not by the layout:
                # `MISC` and `HANDLING CHARGES` are money on the document with no product
                # behind them wherever they are written, and one definition is what stops
                # the two shapes disagreeing about which of them is stock.
                is_stock_item=not _is_charge_code(item_code),
                source_row=row_number,
                location=_text(record.get("stock_location")),
                so_number=_text(record.get("so_number")) or None,
                expected_date=_as_date(record.get("expected_date")),
            )
        )

    if not result.orders:
        result.problems.append(
            "this file carries no purchase lines: every row states either no document "
            "number or no item code."
        )
    return result
