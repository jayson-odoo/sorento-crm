"""L1 - reading AutoCount's sales-order detail listing as HISTORY.

The sibling of `po_listing_reader` on the demand side, and the counterpart of
`outstanding_reader` on the same file. One file, two readers, because they answer two
different questions and mixing them is how a delivered order becomes a commitment:

* `outstanding_reader` answers **"what is still owed to customers?"**. It nets the
  quantity down to what is outstanding and drops anything that nets to zero, because a
  fully delivered line is not a commitment and putting it on the plan would invent demand.
* this reader answers **"what did we sell, and when?"**. It keeps EVERY line, delivered or
  not, and carries the ordered and delivered quantities separately, because the value of
  history is the date and the quantity that actually moved.

Feeding the client's own export through the first one yields nothing at all - every one of
its 81,361 lines is fully delivered - which is correct and is exactly why this reader exists.

The file is a flat table, not the banded report `po_listing_reader` has to unpick: one header
row, then one row per line, with the document's own fields repeated on every one of its lines.
So the parsing risk here is not layout, it is meaning:

**Rows that are not lines.** The export prints an `ITEM PACKAGE :` caption above each package
(9,141 of them in the client's file, no item code and no quantity) and a grand-totals row at
the very bottom carrying a quantity and no document. Neither is a line. Treating the captions
as failures buries the handful of rows that really did fail; treating the totals row as a line
adds 3.2 million units of phantom demand.

**Lines that are not stock.** `MISC` and `TRANSPORT CHARGE` are real money on the order with
no product behind them, the same way `HANDLING CHARGES` is on the purchase side. They are
carried and flagged rather than dropped, so the document still adds up.

**No line number.** One order routinely repeats the same item at the same location and price
(SO174948 carries `SRTWT5801` three times, one unit each). There is nothing in the file to
tell those three apart, so the line's identity is its ORDINAL within its document. That is
stable for a given export and it preserves the repeats, where any content-based key would
collapse three real lines into one.

Pure: bytes and a resolver in, dataclasses out. No session, no catalogue lookup, so the shape
of the file is testable without a database.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from app.services.import_alias_service import AliasResolver, normalize_header
from app.services.scm.outstanding_reader import (
    RowProblem,
    _clean,
    _to_date,
    _to_float,
    sheet_rows,
)

DOC_TYPE = "outstanding_so"

#: Without a document number and a quantity the row states nothing that can be written.
_REQUIRED_COLUMNS = ("so_number", "item_code")

#: Item codes that are real money on the order with no product behind them. Matched on the
#: code, not the description, because the description is free text. Kept as a set rather than
#: a rule so a new one is a one-line change with a test beside it.
NON_STOCK_CODES = {"MISC", "IP", "TRANSPORT", "TRANSPORT CHARGE", "CHARGES", "FREIGHT"}


@dataclass
class SoHistoryLine:
    ordinal: int                    # 1-based position within its own document
    row_number: int                 # position in the sheet, for problem reporting
    item_code: str
    location: str = ""
    qty_ordered: float = 0.0
    qty_delivered: float = 0.0
    unit_price: Optional[float] = None
    required_date: Optional[date] = None
    is_stock_item: bool = True

    @property
    def qty_outstanding(self) -> float:
        return self.qty_ordered - self.qty_delivered


@dataclass
class SoHistoryOrder:
    so_number: str
    order_date: Optional[date] = None
    requested_delivery_date: Optional[date] = None
    debtor_code: str = ""
    customer_name: str = ""
    note: str = ""
    lines: list[SoHistoryLine] = field(default_factory=list)


@dataclass
class SoListingResult:
    orders: list[SoHistoryOrder] = field(default_factory=list)
    problems: list[RowProblem] = field(default_factory=list)
    unmapped_headers: list[str] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)
    total_rows: int = 0
    #: Captions and spacers: neither an item code nor a quantity. Counted, never reported as
    #: failures, because nine thousand "problems" reads as a broken file.
    layout_rows: int = 0
    #: WHICH rows those were. Row numbers, not just a count, because a queued import records
    #: an outcome per source row: with the count alone the 9,144 package captions in the
    #: client's own export are 9,144 rows the job can never account for.
    layout_row_numbers: list[int] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing_columns and bool(self.orders)

    @property
    def line_count(self) -> int:
        return sum(len(o.lines) for o in self.orders)

    @property
    def outstanding_line_count(self) -> int:
        """Lines the file says are NOT fully delivered.

        History is written closed regardless (see `so_history_service`), so this is what the
        uploader has to be told: those lines belong to the outstanding channel, and importing
        them here records them as finished business.
        """
        return sum(
            1 for o in self.orders for ln in o.lines if ln.qty_outstanding > 0
        )


def read_so_listing(file_data: bytes, resolver: AliasResolver) -> SoListingResult:
    """Parse the listing into documents and their lines. Never raises on content."""
    result = SoListingResult()
    try:
        rows = sheet_rows(file_data)
    except Exception as exc:  # noqa: BLE001 - reported, never raised at the uploader
        result.problems.append(RowProblem(0, f"could not read the workbook: {exc}"))
        result.missing_columns = list(_REQUIRED_COLUMNS)
        return result

    # `sheet_rows` yields rather than returns a list - the client's export is 81,362 rows and
    # materialising it twice is the difference between a read and a memory problem.
    try:
        header = next(rows)
    except StopIteration:
        result.missing_columns = list(_REQUIRED_COLUMNS)
        return result

    body = rows
    col_field: dict[int, str] = {}
    for idx, cell in enumerate(header):
        f = resolver.field_for_header(cell)
        if f:
            col_field[idx] = f
        elif normalize_header(cell):
            result.unmapped_headers.append(_clean(cell))

    result.missing_columns = [
        c for c in _REQUIRED_COLUMNS if c not in set(col_field.values())
    ]
    if result.missing_columns:
        return result

    by_number: dict[str, SoHistoryOrder] = {}

    for row_number, row in enumerate(body, start=2):
        if not any(c is not None and str(c).strip() for c in row):
            continue
        result.total_rows += 1
        rec = {col_field[i]: v for i, v in enumerate(row) if i in col_field}

        doc = _clean(rec.get("so_number"))
        item = _clean(rec.get("item_code"))
        ordered = _to_float(rec.get("qty_outstanding"))
        delivered = _to_float(rec.get("qty_delivered"))
        remaining = _to_float(rec.get("qty_remaining"))

        # A row with no item AND no quantity is a caption or a spacer, not a failure.
        if not item and not ordered:
            result.layout_rows += 1
            result.layout_row_numbers.append(row_number)
            continue

        missing = [f for f, v in (("so_number", doc), ("item_code", item)) if not v]
        if ordered is None:
            missing.append("qty")
        if missing:
            result.problems.append(RowProblem(
                row_number, f"missing {', '.join(missing)}", value=doc or item))
            continue

        # The delivered figure, from whichever column the export states it in. The quantity
        # column is what was ORDERED here - unlike the outstanding reader, this one never
        # nets, because history needs both halves. When only a remaining figure is stated,
        # delivered is the difference.
        if delivered is None:
            delivered = (ordered - remaining) if remaining is not None else ordered

        order = by_number.get(doc)
        if order is None:
            order = SoHistoryOrder(
                so_number=doc,
                order_date=_to_date(rec.get("so_date")),
                requested_delivery_date=_to_date(rec.get("required_date")),
                debtor_code=_clean(rec.get("debtor_code")),
                customer_name=_clean(rec.get("customer_name")),
                note=_clean(rec.get("remark")),
            )
            by_number[doc] = order
            result.orders.append(order)

        order.lines.append(SoHistoryLine(
            ordinal=len(order.lines) + 1,
            row_number=row_number,
            item_code=item,
            location=_clean(rec.get("stock_location")),
            qty_ordered=ordered,
            qty_delivered=delivered,
            unit_price=_to_float(rec.get("unit_price")),
            # Per line, not per header: one order routinely carries several delivery dates,
            # and the header's own date cannot stand in for them.
            required_date=_to_date(rec.get("required_date")),
            is_stock_item=item.upper() not in NON_STOCK_CODES,
        ))

    return result
