"""Read a supplier's proforma invoice - one document per file, or five stacked in one.

Two real shapes, and they are the same shape twice:

  * **Jinbaichuan's pre-loading list** (`2026-7-31 SORENTO 预装清单.xlsx`) is five proforma
    invoices stacked down one sheet. Its own title cell says `Proforma Invoice`; the packing
    list channel reads the same file for what is going in the container, and this channel
    reads it for what is being charged for it.
  * **Kailu's proforma** (`KAILU形式发票(Sorento)260717.xlsx`) is one document with a
    letterhead, labelled cells (`货单号：`, `日期：`), a seven-column table and a `合 计` total.

Structurally both are "labelled cells above a header row above lines", which is the packing
list reader's second shape, so its block machinery is reused rather than copied - `_labelled`,
`_header_map` and `_is_header` come from there, parametrised with this document's own block
fields and required columns. What is NOT shared is the line: a packing line is measured
(weights, volumes) and a proforma line is priced.

Header requirement is item code + quantity + UNIT PRICE (AC-P2.6). A table with no price
column is a packing list, and reading it as an invoice would produce documents of record with
no prices in them - worse than refusing the file and naming what is missing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.services.import_alias_service import AliasResolver, normalize_header
from app.services.scm.currency_resolution import price_column_currency
from app.services.scm.outstanding_reader import RowProblem, sheet_rows

# Reused from the packing-list reader, deliberately: the two channels read the SAME file in
# the wild, and a private copy of the block scanner here is how they would start disagreeing
# about where one document ends and the next begins.
from app.services.scm.packing_list_reader import (
    _header_map,
    _is_header,
    _labelled,
    _number,
    _text,
)

DOC_TYPE = "proforma_invoice"

#: A proforma with no price is not a proforma. Quantity and item code are what a line is.
_REQUIRED_COLUMNS = ("item_code", "qty", "unit_price")

#: Fields describing the DOCUMENT rather than a line. Written as labelled cells above the
#: table (`货单号：`, `日期：`) or, rarely, as columns in it.
_BLOCK_FIELDS = ("pi_number", "invoice_date", "container_no", "bl_no", "currency")

#: How the two suppliers write "total". Normalised, so `合 计` and `合计` are one key.
_TOTAL_LABELS = {
    normalize_header(x)
    for x in ("合计", "总金额", "总计", "金额合计", "TOTAL", "Grand Total", "Total Amount")
}

#: The date spellings seen in these documents. Day-first `31.07.2026` is Kailu's; the
#: pre-loading list writes a real date cell, which arrives already stringified as ISO.
#: Anything else is reported against its row rather than guessed at - a date guessed the
#: other way round moves an invoice by months and nothing on screen says so.
_DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%d.%m.%Y",
    "%Y.%m.%d",
    "%Y/%m/%d",
)


@dataclass
class ProformaLine:
    row_number: int
    item_code: str
    qty: float
    description: Optional[str] = None
    uom: Optional[str] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None
    po_ref: Optional[str] = None
    remark: Optional[str] = None
    brand: Optional[str] = None
    cartons: Optional[float] = None
    spec: Optional[str] = None


@dataclass
class ProformaDocument:
    """One invoice: what it is called, when it was written, and what it charges for."""

    index: int
    pi_number: Optional[str] = None
    invoice_date: Optional[date] = None
    container_no: Optional[str] = None
    bl_no: Optional[str] = None
    #: What the document says its money is (`RMB`, `单价(元)`). A hint, never applied here:
    #: the service decides whether the form, the document or the price list wins (AC-P3.1).
    currency_hint: Optional[str] = None
    #: The row its table starts on. Part of its identity when it states no PI number, and the
    #: only thing telling two otherwise identical blocks apart.
    header_row: int = 0
    #: The total the document states for itself, when it states one. Kept beside the line sum
    #: rather than replacing it: a disagreement between the two is a warning worth reading.
    stated_total: Optional[float] = None
    lines: list[ProformaLine] = field(default_factory=list)

    @property
    def total_qty(self) -> float:
        return sum(ln.qty for ln in self.lines)

    @property
    def line_total(self) -> float:
        """The sum of the lines. An amount when the line states one, else price x quantity."""
        total = 0.0
        for ln in self.lines:
            if ln.amount is not None:
                total += ln.amount
            elif ln.unit_price is not None:
                total += ln.unit_price * ln.qty
        return round(total, 2)

    @property
    def priced_lines(self) -> int:
        return sum(1 for ln in self.lines if ln.unit_price is not None or ln.amount is not None)


@dataclass
class ProformaReadResult:
    documents: list[ProformaDocument] = field(default_factory=list)
    problems: list[RowProblem] = field(default_factory=list)
    unmapped_headers: list[str] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)
    total_rows: int = 0

    @property
    def ok(self) -> bool:
        """Readable when a priced header row was found and something sits under it.

        Individual unusable rows do not condemn the file, same rule as every other importer
        here: a 19-line invoice with one blank model number lands 18 and names the one.
        """
        return not self.missing_columns and bool(self.documents)

    @property
    def line_count(self) -> int:
        return sum(len(d.lines) for d in self.documents)

    @property
    def priced_line_count(self) -> int:
        return sum(d.priced_lines for d in self.documents)

    @property
    def currency_hint(self) -> Optional[str]:
        """What the file as a whole states, i.e. the first document that states anything."""
        for doc in self.documents:
            if doc.currency_hint:
                return doc.currency_hint
        return None


def _parse_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _stated_total(raw: list) -> Optional[float]:
    """The number a totals row states, when the row IS one.

    Positional reading is not available: on the pre-loading list the totals row is merged and
    sits one column left of the header it belongs to, so `总金额` lands under `总体积(cbm)`
    and its value under `RMB`. The label is the anchor, and the number is whichever side of
    it carries one.
    """
    for pos, cell in enumerate(raw):
        if normalize_header(cell) not in _TOTAL_LABELS:
            continue
        for nxt in raw[pos + 1:]:
            found = _number(nxt)
            if found is not None:
                return found
        for prev in reversed(raw[:pos]):
            found = _number(prev)
            if found is not None:
                return found
        return None
    return None


def _pi_line_from(raw: list, col_field: dict[int, str], row_number: int) -> Optional[ProformaLine]:
    """One priced line, or None when this row is not one.

    A totals row (`合 计`, `总金额`) and a blank numbered row (`序号` filled, nothing else)
    both fail the item-code test, which is what keeps them out of the document.
    """
    vals: dict[str, Any] = {}
    for pos, f in col_field.items():
        if pos < len(raw):
            vals[f] = raw[pos]

    code = _text(vals.get("item_code"))
    qty = _number(vals.get("qty"))
    if not code or qty is None:
        return None

    unit_price = _number(vals.get("unit_price"))
    amount = _number(vals.get("amount"))
    # The supplier fills one of the two about as often as both. Neither is derived onto the
    # line here: the document of record says what it says, and the service sums whichever is
    # present. Deriving would make a wrong price look like a stated one.
    return ProformaLine(
        row_number=row_number,
        item_code=code,
        qty=qty,
        description=_text(vals.get("description")),
        uom=_text(vals.get("uom")),
        unit_price=unit_price,
        amount=amount,
        po_ref=_text(vals.get("po_ref")),
        remark=_text(vals.get("remark")),
        brand=_text(vals.get("brand")),
        cartons=_number(vals.get("cartons")),
        spec=_text(vals.get("spec")),
    )


def read_workbook(
    file_data: bytes, resolver: Optional[AliasResolver] = None, *, db: Optional[Session] = None
) -> ProformaReadResult:
    """Parse a workbook into proforma invoices.

    `resolver` is injectable so parsing can be tested against a file alone, with no database
    in the picture; `db` builds one from the alias table for the normal path.

    The document number is NOT derived here. A derived one is positional and needs the file's
    own name (`PI-<stem>-<index>`, AC-P2.5), which this function does not have - the service
    owns it (`proforma_invoice_service.pi_number_for`). What is stated is what is returned.
    """
    if resolver is None:
        if db is None:
            raise ValueError("read_workbook needs either a resolver or a session")
        resolver = AliasResolver.for_doc_type(db, DOC_TYPE)

    result = ProformaReadResult()
    try:
        all_rows = list(sheet_rows(file_data))
    except Exception as exc:  # noqa: BLE001 - the message is for the person who uploaded it
        result.problems.append(RowProblem(0, f"could not read the workbook: {exc}"))
        result.missing_columns = list(_REQUIRED_COLUMNS)
        return result

    result.total_rows = len(all_rows)
    # field -> (value, the row it was written on), so a date that will not parse can be
    # complained about by row rather than by document.
    pending: dict[str, tuple[str, int]] = {}
    current: Optional[ProformaDocument] = None
    col_field: dict[int, str] = {}
    saw_header = False
    #: The most complete header candidate seen, so a file whose table has an item code and a
    #: quantity but NO price says exactly that instead of naming all three columns.
    best_header: set[str] = set()

    for idx, raw in enumerate(all_rows):
        row_number = idx + 1
        mapped = _header_map(raw, resolver)

        if _is_header(mapped, _REQUIRED_COLUMNS):
            if not saw_header:
                result.unmapped_headers = [
                    str(c).strip()
                    for p, c in enumerate(raw)
                    if p not in mapped and normalize_header(c)
                ]
            saw_header = True
            col_field = mapped
            current = _document_from(
                index=len(result.documents) + 1,
                raw_header=raw,
                col_field=mapped,
                pending=pending,
                header_row=row_number,
                problems=result.problems,
            )
            result.documents.append(current)
            pending = {}
            continue

        fields = set(mapped.values())
        if len(fields & set(_REQUIRED_COLUMNS)) > len(best_header & set(_REQUIRED_COLUMNS)):
            best_header = fields

        if not saw_header:
            _absorb(pending, _labelled(raw, resolver, _BLOCK_FIELDS), row_number)
            continue

        line = _pi_line_from(raw, col_field, row_number)
        if line is None:
            total = _stated_total(raw)
            if total is not None:
                if current is not None and current.stated_total is None:
                    current.stated_total = total
                continue
            # Not a line and not a total. It may be the labels introducing the NEXT document,
            # which is how a stacked file separates one invoice from the one before it.
            _absorb(pending, _labelled(raw, resolver, _BLOCK_FIELDS), row_number)
            continue

        if current is not None:
            current.lines.append(line)

    if not saw_header:
        result.missing_columns = [c for c in _REQUIRED_COLUMNS if c not in best_header] or list(
            _REQUIRED_COLUMNS
        )
        return result

    present = set(col_field.values())
    result.missing_columns = [c for c in _REQUIRED_COLUMNS if c not in present]
    if result.missing_columns:
        return result

    # A header with no lines under it is the shape of an empty template, not an invoice.
    result.documents = [d for d in result.documents if d.lines]
    for i, doc in enumerate(result.documents, start=1):
        doc.index = i
    return result


def _absorb(
    pending: dict[str, tuple[str, int]], found: dict[str, str], row_number: int
) -> None:
    """Keep the FIRST spelling of each block field, and remember which row said it."""
    for f, value in found.items():
        pending.setdefault(f, (value, row_number))


def _document_from(
    *,
    index: int,
    raw_header: list,
    col_field: dict[int, str],
    pending: dict[str, tuple[str, int]],
    header_row: int,
    problems: list[RowProblem],
) -> ProformaDocument:
    stated_date, date_row = pending.get("invoice_date", (None, header_row))
    invoice_date = _parse_date(stated_date)
    if stated_date and invoice_date is None:
        problems.append(RowProblem(date_row, f"could not read the invoice date: {stated_date}"))

    labelled_currency = pending.get("currency", (None, 0))[0]
    return ProformaDocument(
        index=index,
        pi_number=pending.get("pi_number", (None, 0))[0],
        invoice_date=invoice_date,
        container_no=pending.get("container_no", (None, 0))[0],
        bl_no=pending.get("bl_no", (None, 0))[0],
        currency_hint=price_column_currency(
            raw_header, col_field, extra=[labelled_currency] if labelled_currency else []
        ),
        header_row=header_row,
    )
