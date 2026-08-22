"""Pulling a list of product codes out of a file an admin already has (S18).

The client's definition of "standard" arrived as a workbook: three sheets, a title row,
headings on row 2 and the codes in column F. Nothing here depends on any of that being
true. Codes are found by HEADING, with the usual synonyms, across EVERY sheet - a column
that moved must not silently turn a description into a product code, which is exactly the
failure a positional reader produces and the one nobody notices until a hundred wrong
products have been called standard.

It reads THREE columns, and until 2026-08-10 it read one. The note that used to sit here
said importing the sheet's pricing would create "a second, quieter source of truth"; that
was right about images, which still belong to `product_attachments.is_primary`, and wrong
about price. The client's answer to "what does this scope sell and for how much" IS that
sheet, and leaving two of its columns in Excel left them quoting from Excel.

So:

* **PRODUCT CODE** -> the code, as before.
* **DEVELOPERS / DEVELOPER** -> the price this series sells at (`selling_price`).
* **DISTRIBUTORS / DISTRIBUTOR** -> how much further a distributor may discount, as a
  percent (`max_discount_pct`).

CENTRAL, NORTHEN and SOUTHERN are still ignored. They exist in the file and are entirely
empty, and importing an empty column as a real per-region price dimension is how a pricing
model becomes something nobody can explain.

A missing price or percentage is **silence, not zero** - see `normalise_percent`.
"""
from __future__ import annotations

import csv
import io
import logging
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, List, Sequence

from app.services.error_handler import AppException

logger = logging.getLogger(__name__)

# Headings that mean "this column holds the product code", normalised to lower case with
# punctuation dropped so `Product Code`, `PRODUCT CODE ` and `Product/Code` are one thing.
#
# `ITEM` is NOT on this list even though the AutoCount reader accepts it, and the client's
# own sheet is why: there `ITEM` is the row number, so accepting it would have called `1`,
# `2`, `3` product codes on a sheet that also carries a perfectly good `PRODUCT CODE`.
_CODE_HEADINGS = (
    "product code",
    "item code",
    "stock code",
    "sku",
    "code",
)

# The price this series sells at. `DEVELOPERS` is the client's word for it and their tabs
# disagree on the plural, so both spellings are here alongside the words somebody would use
# if they built the sheet themselves.
_PRICE_HEADINGS = (
    "developers",
    "developer",
    "selling price",
    "sell price",
    "price",
)

# How much further a distributor may come down. Same story on the plural.
#
# `CENTRAL`, `NORTHEN` and `SOUTHERN` are deliberately absent: they are in the file, they are
# entirely empty, and a per-region price is a different model from a single price plus a
# margin. Adding them here would silently make every one of those blanks mean something.
_DISCOUNT_HEADINGS = (
    "distributors",
    "distributor",
    "max discount",
    "maximum discount",
    "discount",
)

# How far down a sheet to look for the heading row. The client's own file puts a title on
# row 1, so "row 1 or bust" would find nothing; ten is generous and still bounded.
_MAX_HEADER_SCAN = 10

_XLSX_SUFFIXES = (".xlsx", ".xlsm")
_CSV_SUFFIXES = (".csv", ".txt", ".tsv")


def _norm_heading(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        # openpyxl reads a numeric-looking code as a float; `8038.0` is not a product code
        # anybody typed.
        return str(int(value))
    return str(value).strip()


def _code_column(rows: Sequence[Sequence[Any]]) -> tuple[int, int] | None:
    """``(header_row_index, column_index)`` of the code column, or None.

    Scores by heading rather than taking the first hit: on the client's sheet both `ITEM `
    and `PRODUCT CODE` are present, and `ITEM` there is a row number. The most specific
    heading wins, which is what the ordering of ``_CODE_HEADINGS`` encodes.
    """
    best: tuple[int, int, int] | None = None  # (rank, row, column)
    for row_index, row in enumerate(rows[:_MAX_HEADER_SCAN]):
        for column_index, cell in enumerate(row):
            heading = _norm_heading(cell)
            if heading in _CODE_HEADINGS:
                rank = _CODE_HEADINGS.index(heading)
                if best is None or rank < best[0]:
                    best = (rank, row_index, column_index)
    return (best[1], best[2]) if best else None


def _split_cell(value: Any) -> List[str]:
    """One cell as the codes it holds.

    Split on line breaks, because the client's own sheet has cells carrying TWO codes on
    two lines (`MAB7050-WH` above `SRTWHBWP`). Read whole, such a cell matches nothing and
    is reported as one unreadable string; split, both halves get looked up and the miss
    report names the code that is actually missing. No product code contains a newline, so
    there is nothing this can wrongly break apart.
    """
    text = _cell(value)
    if not text:
        return []
    return [part.strip() for part in re.split(r"[\r\n]+", text) if part.strip()]


def _value_column(header: Sequence[Any], headings: Sequence[str]) -> int | None:
    """The first column in this header row whose heading is one of ``headings``."""
    for index, cell in enumerate(header):
        if _norm_heading(cell) in headings:
            return index
    return None


def normalise_price(value: Any) -> Decimal | None:
    """A money cell as a number, or nothing.

    Lenient about how it is written (``RM 1,250.50``) and strict about what it means: a cell
    that is not a number at all (``TBC``) and a negative one both come back as nothing rather
    than as a price somebody would then quote from.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", text)
    if not cleaned or cleaned in {"-", ".", "-."}:
        return None
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        return None
    return None if amount < 0 else amount


def normalise_percent(value: Any) -> Decimal | None:
    """A discount cell as a PERCENT, however the sheet spelled it.

    The client's book writes the same six percent two ways: ``6 % MAX`` in `wares` and
    ``0.06`` in `fittings`. Both land on ``6``.

    The rule, stated because it is a judgement either way round:

    * a cell carrying a literal ``%`` is a percentage at face value, whatever its size, so
      ``6 % MAX`` can never be read as six hundred percent;
    * otherwise a value **below one** is a fraction and is multiplied out (``0.06`` -> 6,
      ``0.1`` -> 10), and a value of **one or more** is already a percentage (``6`` -> 6).

    Exactly ``1`` therefore reads as one percent rather than one hundred. Both readings are
    defensible; a hundred percent discount is not a thing anybody types into a price sheet,
    and one percent is.

    **Nothing is nothing.** A blank, or a cell saying ``n/a``, returns ``None`` and NOT zero.
    Zero would mean "no discount permitted", which is a hard floor at the selling price - and
    56 of the client's 151 codes carry a price with no percentage beside it, so that reading
    would put every one of them in breach the moment anybody discounted a cent.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    literal_percent = "%" in text
    cleaned = re.sub(r"[^0-9.\-]", "", text)
    if not cleaned or cleaned in {"-", ".", "-."}:
        return None
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        return None
    if amount < 0:
        return None
    if not literal_percent and amount < 1:
        amount = amount * 100
    return amount.normalize() + Decimal(0)


@dataclass(frozen=True)
class SeriesSheetRow:
    """One product as the sheet states it. Price and percentage are optional, and absent
    means the sheet did not say - never zero."""

    code: str
    selling_price: Decimal | None = None
    max_discount_pct: Decimal | None = None


def _series_rows_from_rows(rows: Sequence[Sequence[Any]]) -> List[SeriesSheetRow] | None:
    """Every row below the heading, in sheet order. None when there is no code column.

    Price and percentage are located in the SAME header row the code was found in, so a
    workbook whose tabs disagree about where the headings sit (the client's does) still reads
    each tab on its own terms.
    """
    found = _code_column(rows)
    if found is None:
        return None
    header_row, code_column = found
    header = rows[header_row]
    price_column = _value_column(header, _PRICE_HEADINGS)
    discount_column = _value_column(header, _DISCOUNT_HEADINGS)

    def _at(row: Sequence[Any], column: int | None) -> Any:
        return row[column] if column is not None and column < len(row) else None

    out: List[SeriesSheetRow] = []
    for row in rows[header_row + 1 :]:
        if code_column >= len(row):
            continue
        price = normalise_price(_at(row, price_column))
        discount = normalise_percent(_at(row, discount_column))
        # A cell holding two codes on two lines gives both the row's price: the sheet states
        # one figure for that line and splitting it between them would invent a number.
        for code in _split_cell(row[code_column]):
            out.append(
                SeriesSheetRow(code=code, selling_price=price, max_discount_pct=discount)
            )
    return out


def _rows_from_xlsx(payload: bytes) -> List[List[List[Any]]]:
    import openpyxl

    try:
        book = openpyxl.load_workbook(io.BytesIO(payload), data_only=True, read_only=True)
    except Exception as exc:  # noqa: BLE001 -- a corrupt upload is the user's problem to see
        raise AppException(
            status_code=422,
            message="That file could not be opened as a spreadsheet.",
            code="series_import_unreadable",
        ) from exc
    try:
        return [
            [list(row) for row in sheet.iter_rows(values_only=True)]
            for sheet in book.worksheets
        ]
    finally:
        book.close()


def _rows_from_csv(payload: bytes) -> List[List[List[Any]]]:
    text_body = payload.decode("utf-8-sig", errors="replace")
    first_line = next((line for line in text_body.splitlines() if line.strip()), "")
    delimiter = "\t" if "\t" in first_line else ","
    reader = csv.reader(io.StringIO(text_body), delimiter=delimiter)
    return [[list(row) for row in reader]]


def extract_product_codes(payload: bytes, *, filename: str = "") -> List[str]:
    """Every product code in the file, in the order it appears, duplicates kept.

    The S18 entry point, kept because several callers want nothing else. It delegates to
    ``extract_series_rows`` rather than walking the sheet a second way, so the two readers
    cannot drift into disagreeing about which column holds the code.
    """
    return [row.code for row in extract_series_rows(payload, filename=filename)]


def extract_series_rows(payload: bytes, *, filename: str = "") -> List[SeriesSheetRow]:
    """Every product row in the file - code, price, percentage - in the order it appears.

    Duplicates are kept on purpose: the caller reports how many cells were submitted against
    how many unique codes they came to, and collapsing them here would hide that the client's
    151 cells are really 140 codes.

    A single-column list with no heading at all is accepted too - not every list arrives as
    the client's template, and refusing a plain paste-to-CSV would send an admin back to
    Excel to add a header row for our benefit. Such a file states no prices, so those rows
    carry a code and nothing else.
    """
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix in _CSV_SUFFIXES:
        sheets = _rows_from_csv(payload)
    elif suffix in _XLSX_SUFFIXES or not suffix:
        sheets = _rows_from_xlsx(payload)
    else:
        raise AppException(
            status_code=422,
            message=(
                f"'{suffix or filename}' is not a spreadsheet. Upload an .xlsx or a .csv, "
                "or paste the codes instead."
            ),
            code="series_import_unsupported_file",
        )

    out: List[SeriesSheetRow] = []
    matched_any = False
    for rows in sheets:
        found = _series_rows_from_rows(rows)
        if found is not None:
            matched_any = True
            out.extend(found)

    if not matched_any:
        # The one-column, no-heading case: every non-empty row IS a code. Only offered when
        # the file really is one column wide, so a headless multi-column sheet still gets
        # the honest refusal below rather than a column picked at random.
        single = [
            _cell(row[0])
            for rows in sheets
            for row in rows
            if len([cell for cell in row if _cell(cell)]) == 1 and _cell(row[0])
        ]
        total_cells = sum(
            1 for rows in sheets for row in rows for cell in row if _cell(cell)
        )
        if single and len(single) == total_cells:
            return [SeriesSheetRow(code=code) for code in single]
        raise AppException(
            status_code=422,
            message=(
                "No PRODUCT CODE column was found in that file. Name the column "
                "'Product code' (or 'Item code'), or paste the codes instead."
            ),
            code="series_import_no_code_column",
        )

    return out


def parse_pasted_codes(text_body: str) -> List[str]:
    """Codes as somebody pasted them: one per line, or comma / tab / semicolon separated.

    Split on every plausible separator at once rather than asking the user which one they
    used. A paste out of Excel arrives newline-separated; a paste out of an email arrives
    comma-separated; both are the same intent.
    """
    parts = re.split(r"[\r\n,;\t]+", text_body or "")
    return [part.strip() for part in parts if part.strip()]
