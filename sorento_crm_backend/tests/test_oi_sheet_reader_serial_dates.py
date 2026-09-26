"""Excel date serials, left in General format: the DELIVERY DATE and SO DATE columns of the
customer's current `JAN - DEC 2026 ORDERabc.xlsx` (measured defect, 19 Sep 2026).

`project_order_inquiry_reader._as_date` accepts a `datetime`, a `date`, and day-first TEXT
(AC-17, round 4, `test_project_order_inquiry_import_reader.py`) - but not a plain Excel date
SERIAL, an integer (or a whole-number float openpyxl can hand back) counting days from
1899-12-30. A cell left in "General" number format reads back as exactly that: measured on
the customer's own book, 15,942 of 16,057 rows carry an int where a date belongs, `_as_date`
answers `None` for every one of them, and a delivery on the same item that shares a quantity
collapses into a single "restatement" (`_restates`' key includes the date; `None` ties every
one of them together). `46024` = 2026-01-02, `46113` = 2026-04-01, `45588` = 2024-10-23 -
`date(1899, 12, 30) + timedelta(days=serial)`, the usual (1900-leap-year-bug-compatible)
Excel epoch.

No database needed - `_as_date` and `read_order_inquiry` are pure functions over workbook
bytes, so this lives beside `test_project_order_inquiry_import_reader.py` rather than
through the Postgres-backed importer harness. The importer-level regression this same defect
causes (two real deliveries collapsing into one raised row) is
`test_serial_dated_rows_are_not_restatements` in `test_oi_sheet_line_pick_month_po.py`.
"""
from __future__ import annotations

from datetime import date
from io import BytesIO

import openpyxl
import pytest

from app.services.project_order_inquiry_reader import _as_date, read_order_inquiry

#: The monthly-book shape's own header spellings (`SUPPLIER` / `PO NO`, no `STOCK
#: LOCATION`) is not what is under test here - this uses the single-sheet form's headers,
#: with `SO DATE` added, because `so_date` is the other column this defect hits.
_HEADERS = (
    "SO NO", "ITEM CODE", "QTY", "SO DATE", "DELIVERY DATE", "STOCK LOCATION", "REMARK",
)


def _book(rows) -> bytes:
    workbook = openpyxl.Workbook()
    tab = workbook.active
    tab.title = "Sheet1"
    tab.append(list(_HEADERS))
    for row in rows:
        tab.append(list(row))
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_reader_reads_excel_serial_delivery_date():
    """A DELIVERY DATE cell holding the plain int `46113` and an SO DATE cell holding the
    plain int `45588` - General format, exactly how the customer's book carries them - read
    as real dates, not as `None`. A whole-number FLOAT serial (`46113.0`) reads the same,
    since a formula-derived cell can come back as one."""
    data = _book([
        ("SO1", "ITEM1", 200, 45588, 46113, "WH1", ""),
        ("SO2", "ITEM1", 200, 45588.0, 46113.0, "WH1", ""),
    ])

    result = read_order_inquiry(data)

    assert result.ok, result.problems
    assert [r.delivery_date for r in result.rows] == [
        date(2026, 4, 1), date(2026, 4, 1),
    ], "an integer (or whole-number float) serial in the delivery date cell answered None"
    assert [r.so_date for r in result.rows] == [
        date(2024, 10, 23), date(2024, 10, 23),
    ]

    # Direct on `_as_date` too, in case a workbook round trip ever normalises the float
    # back to an int before this reaches it (measured: this openpyxl build already does).
    assert _as_date(46113.0) == date(2026, 4, 1)
    assert _as_date(45588.0) == date(2024, 10, 23)


@pytest.mark.parametrize(
    "serial, expected",
    [
        (36526, date(2000, 1, 1)),
        (73050, date(2099, 12, 31)),
        (36525, None),
        (73051, None),
        (0, None),
        (200, None),
        (99999, None),
        (True, None),
        (False, None),
    ],
)
def test_reader_serial_date_bounds(serial, expected):
    """The sane window is 2000-01-01 to 2099-12-31 inclusive (Excel serials 36526 to
    73050). Anything outside it is a NUMBER sitting in the date column, not a date - a
    quantity typed into DELIVERY DATE by mistake must not become 18 Jul 1900 (serial 200)
    or some date in 2170 (serial 99999). `bool` is an `int` in Python
    (`isinstance(True, int)` is `True`), so `True` / `False` must not slip through an
    int-shaped branch and answer `1899-12-31` / `1899-12-30`."""
    assert _as_date(serial) == expected
