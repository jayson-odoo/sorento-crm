"""L1 - reading AutoCount's "Purchase Order Listing With Detail".

A **banded report**, not a table: two label rows, then repeating blocks of one order header
followed by its lines. Pure - bytes in, dataclasses out, no session and no catalogue lookup,
so the shape of the file can be tested without a database.

Three properties of the real export drive the whole design.

**Merged cells shift the columns, in BOTH directions.** The label `Curr.` sits at column 47
with its value at 48, `Total` at 54 with its value at 50, and on the line band the item code
is written one column BEFORE its own label. So neither absolute columns nor nearest-label
binding works: the first mis-binds the very first block, and the second binds the header
total to the currency (50 is 3 from `Curr.` and 4 from `Total`). What is reliable is the
ORDER - the export writes one value per label, left to right, in the order the labels are
printed - so values are aligned to labels by sequence. See `_align`.

**There is a summary section after the orders.** `Final Summary By Items` repeats every item
with `Item Code | UOM | Qty | Amount`, which is indistinguishable from a line row by shape.
Parsing stops at the `Doc Count:` marker; without it every quantity in the file is doubled,
and the result still looks perfectly well formed.

**Some lines are not stock.** `MISC`, `HANDLING CHARGES` and their like are real money on the
order with no product behind them. Dropping them makes the order total stop adding up;
resolving them against the catalogue produces codes that can never match and a failure
reported on every upload. They are carried, and flagged.

What this reader deliberately does NOT produce is an outstanding position. The report's only
quantity is what was ordered - no received column, no line status - so a caller that treated
it as an outstanding book would import 1,586 closed 2020 orders as incoming supply and
inflate every position in the system. `is_order_book` says so out loud.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable, Optional

from app.services.scm.outstanding_reader import sheet_rows

# The header band labels, in the order the export writes them.
_HEADER_LABELS = ("Doc No", "Date", "Code", "Creditor Name", "Curr.", "Total", "Local Total")
# The line band labels. `Disc.` is the last label, and the amount columns fall after it.
_LINE_LABELS = ("No.", "Item Code", "Description", "UOM", "Qty", "Unit Price", "Disc.")

# Everything after this marker is the per-item summary, which repeats the whole file.
_STOP_MARKER = "doc count:"

# A document number in any of the three families the export uses:
#   202001-S0001   SPO-2020/01-0001   PO-2020/01-0001
_DOC_NUMBER = re.compile(r"^(?:[A-Z]{2,4}-)?\d{4}[-/]?\d{0,2}[-/]?[A-Z]?\d{3,4}$", re.I)

# An SO reference written into a PO as a NOTE line. Seen in the real export as
# `**SO:174830**`, and with a customer or project attached: `-HOMEPRO @ SO:174830`,
# `**ECO WORLD TRADING @ SO:174863**`. The digits are what matters; the decoration is not
# consistent enough to parse for meaning.
_SO_NOTE = re.compile(r"S\s*/?\s*O\s*[:#]?\s*(\d{4,})", re.I)

# Item codes that are charges rather than products. Matched on the WHOLE code, never as a
# substring: a real product whose code happens to contain "MISC" is a product.
_NON_STOCK_CODES = {
    "MISC",
    "MISCELLANEOUS",
    "HANDLING CHARGES",
    "HANDLING CHARGE",
    "FREIGHT",
    "FREIGHT CHARGES",
    "TRANSPORT",
    "TRANSPORT CHARGES",
    "DELIVERY CHARGES",
    "SERVICE CHARGES",
    "BANK CHARGES",
    "INSURANCE",
    "DISCOUNT",
    "ROUNDING",
}


@dataclass
class PoListingLine:
    line_no: Optional[int]
    item_code: str
    description: str
    uom: str
    qty_ordered: float
    unit_price: Optional[float]
    amount: Optional[float]
    local_amount: Optional[float]
    #: False for a charge line - real money on the order, no product behind it.
    is_stock_item: bool
    source_row: int


@dataclass
class PoListingNote:
    """A description-only line inside an order: a note, not a purchase.

    The export uses these to mark which sales order a group of lines is for. It carries no
    item and no quantity, so it is not a line - but it is the only place in this file where
    the SO appears at all, and dropping it would throw away the linkage.
    """

    line_no: Optional[int]
    text: str
    #: Sales-order numbers found in the text. Usually one; a note may name none.
    so_numbers: tuple[str, ...]
    source_row: int


@dataclass
class PoListingOrder:
    po_number: str
    order_date: Optional[date]
    supplier_code: str
    supplier_name: str
    currency: str
    total: Optional[float]
    local_total: Optional[float]
    source_row: int
    lines: list[PoListingLine] = field(default_factory=list)
    notes: list[PoListingNote] = field(default_factory=list)

    @property
    def so_numbers(self) -> tuple[str, ...]:
        """Every sales order this order's notes name, in the order they appear.

        Deliberately ORDER-level, not line-level. A note sits between lines and there is
        nothing in the file that says whether it describes the lines above it or the ones
        below - and guessing assigns somebody else's stock to a customer order. The pairing
        this supports is "this PO relates to that SO", which is true either way; the
        per-line pairing comes from the Order Inquiry sheet, which states it outright.
        """
        seen: list[str] = []
        for note in self.notes:
            for so in note.so_numbers:
                if so not in seen:
                    seen.append(so)
        return tuple(seen)


@dataclass
class PoListingResult:
    orders: list[PoListingOrder] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    #: True once the `Doc Count:` marker was seen, i.e. the summary section was excluded.
    stopped_at_marker: bool = False
    #: Always True. Stated rather than implied: this file says what was ORDERED and cannot
    #: say what is still outstanding, and a caller must not read it as an on-order position.
    is_order_book: bool = True

    @property
    def ok(self) -> bool:
        return bool(self.orders) and not any(p.startswith("this file") for p in self.problems)

    @property
    def line_count(self) -> int:
        return sum(len(o.lines) for o in self.orders)


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
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _bands(row: tuple, labels: Iterable[str]) -> Optional[dict[str, int]]:
    """Where each label of a band sits, if this row IS that band's label row."""
    found: dict[str, int] = {}
    for idx, cell in enumerate(row):
        text = _text(cell)
        for label in labels:
            if text.lower() == label.lower() and label not in found:
                found[label] = idx
    return found if len(found) == len(tuple(labels)) else None


def _values(row: tuple) -> list[Any]:
    """The row's non-empty cells, left to right."""
    return [c for c in row if c is not None and _text(c) != ""]


def _align(row: tuple, labels: tuple[str, ...]) -> tuple[dict[str, Any], list[Any]]:
    """Bind a data row's values to the labels by SEQUENCE, and return the tail.

    Not by column, and not by nearest label - both are wrong on this export, and each is
    wrong in a way that looks right on some rows:

      * absolute columns: the label `Curr.` sits at 47 and its value at 48, `Total` at 54
        with its value at 50, so the first block already mis-binds;
      * nearest label: the header total at column 50 is 3 away from `Curr.` and 4 from
        `Total`, so it binds to the currency.

    What IS reliable is the order. The export writes one value per label, left to right, in
    the order the labels are printed - so the k-th value is the k-th field. Values past the
    last label are the money columns the band has no label for (amount, local amount), and
    they come back as the tail rather than being forced into `Disc.`.
    """
    values = _values(row)
    bound = {label: values[i] for i, label in enumerate(labels) if i < len(values)}
    return bound, values[len(labels):]


def _looks_like_doc_number(value: Any) -> bool:
    text = _text(value)
    return bool(text) and bool(_DOC_NUMBER.match(text))


def read_po_listing(file_data: bytes) -> PoListingResult:
    """Parse the export into orders and their lines."""
    result = PoListingResult()
    try:
        rows = list(sheet_rows(file_data))
    except Exception as exc:  # noqa: BLE001 - surfaced, never swallowed
        result.problems.append(f"this file could not be read: {exc}")
        return result

    header_bands: Optional[dict[str, int]] = None
    line_bands: Optional[dict[str, int]] = None
    current: Optional[PoListingOrder] = None

    for row_number, row in enumerate(rows, start=1):
        first = _text(row[0]) if row else ""
        if first.lower().startswith(_STOP_MARKER):
            # Everything below repeats the file as a per-item summary.
            result.stopped_at_marker = True
            break

        if header_bands is None:
            found = _bands(row, _HEADER_LABELS)
            if found:
                header_bands = found
                continue
        if line_bands is None:
            found = _bands(row, _LINE_LABELS)
            if found:
                line_bands = found
                continue
        if header_bands is None or line_bands is None:
            continue

        # A header row starts with the document number; a line row starts with a line number.
        if _looks_like_doc_number(row[0]):
            values, _extra = _align(row, _HEADER_LABELS)
            current = PoListingOrder(
                po_number=_text(values.get("Doc No")),
                order_date=_as_date(values.get("Date")),
                supplier_code=_text(values.get("Code")),
                supplier_name=_text(values.get("Creditor Name")),
                currency=_text(values.get("Curr.")),
                total=_number(values.get("Total")),
                local_total=_number(values.get("Local Total")),
                source_row=row_number,
            )
            result.orders.append(current)
            continue

        line_no = _number(row[0]) if row else None
        if line_no is None or current is None:
            continue

        # `Disc.` is the last label and is empty on every line in the real export, so the
        # amount lands in its slot. Align only up to `Unit Price` and treat everything after
        # as money, which is what the report actually writes.
        values, money = _align(row, _LINE_LABELS[:-1])
        item_code = _text(values.get("Item Code"))
        qty = _number(values.get("Qty"))

        # A row with a line number but no item and no quantity is not a broken line - it is
        # a NOTE, and the export uses notes to name the sales order. Reporting these as
        # failures produced 812 complaints on the customer's own file, which is how a
        # problem list stops being read.
        if not item_code or qty is None:
            text = _text(values.get("Description")) or _text(values.get("Item Code"))
            if text:
                current.notes.append(
                    PoListingNote(
                        line_no=int(line_no),
                        text=text,
                        so_numbers=tuple(_SO_NOTE.findall(text)),
                        source_row=row_number,
                    )
                )
            # A line number with nothing at all beside it is spacing in the report.
            continue

        amounts = [n for n in (_number(m) for m in money) if n is not None]

        current.lines.append(
            PoListingLine(
                line_no=int(line_no),
                item_code=item_code,
                description=_text(values.get("Description")),
                uom=_text(values.get("UOM")),
                qty_ordered=qty,
                unit_price=_number(values.get("Unit Price")),
                amount=amounts[0] if amounts else None,
                local_amount=amounts[1] if len(amounts) > 1 else None,
                is_stock_item=item_code.strip().upper() not in _NON_STOCK_CODES,
                source_row=row_number,
            )
        )

    if not result.orders:
        result.problems.append(
            "this file does not look like a Purchase Order Listing With Detail: no order "
            "header row was found."
        )
    return result
