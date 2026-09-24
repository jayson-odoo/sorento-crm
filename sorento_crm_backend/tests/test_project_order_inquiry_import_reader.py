"""L3 - reading the Order Inquiry sheet, against a real slice of the customer's own file.

This sheet is the reason no curation screen is needed: it carries the stock location a sales
order line ships from, and the purchase order that line is waiting on. Both were believed
missing.

Three shapes in the nine fixture rows, all of them real:

  * `ORDER`                        - nothing placed for this line yet
  * `202605-S0042`                 - waiting on one purchase order
  * `202606-S0024 & 202607-S0043`  - ONE line split across two purchase orders
  * `202605-S0042 & ORDER`         - partly ordered, partly not

The reader moved to Project Sales ownership with its importer (ADR 0010), so this suite lives
in `tests/` rather than `tests/scm/`. The workbook itself stays in `tests/scm/fixtures/`
because two SCM suites - the purchase-history routes and the SO<->PO link test - read the same
file, and one sample file is better than three copies drifting apart.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.services.project_order_inquiry_reader import read_order_inquiry

FIXTURE = Path(__file__).parent / "scm" / "fixtures" / "order_inquiry_sample.xlsx"


@pytest.fixture(scope="module")
def result():
    return read_order_inquiry(FIXTURE.read_bytes())


def test_it_reads_the_lines(result):
    assert result.ok, result.problems
    assert result.problems == []
    assert all(r.so_number and r.item_code for r in result.rows)


def test_the_stock_location_is_read(result):
    """The location was the half of the gap the user could not see a source for."""
    assert result.with_location == len(result.rows)
    assert {r.location for r in result.rows} == {"BRW-IB"}


def test_a_line_can_wait_on_more_than_one_purchase_order(result):
    """`202606-S0024 & 202607-S0043` is one line split across two orders.

    Matching the cell as a whole - or taking the first number - silently loses half the
    supply the line is waiting for, and the loss is invisible: the line still shows a PO.
    """
    split = next(r for r in result.rows if len(r.po_numbers) > 1)
    assert split.po_numbers == ("202606-S0024", "202607-S0043")
    # One claim per (line, order), so a split line claims twice.
    assert result.po_claims > result.with_po


def test_order_means_nothing_is_placed_yet_and_is_not_a_parse_failure(result):
    """"We have not bought it" and "we do not know" are different answers.

    A reader that treated `ORDER` as unparseable would report the first as the second.
    """
    plain = [r for r in result.rows if not r.po_numbers]
    assert plain, "the fixture must exercise the not-yet-ordered path"
    assert all(r.not_ordered for r in plain)


def test_a_line_partly_ordered_records_both_facts(result):
    """`202605-S0042 & ORDER` is a real state: some on order, the rest not."""
    partial = [r for r in result.rows if r.po_numbers and r.not_ordered]
    assert partial, "the fixture must exercise the partly-ordered path"


def test_order_as_a_word_not_as_a_substring():
    """`BACKORDER` and `REORDERED` are not the sheet saying nothing is placed."""
    from app.services.project_order_inquiry_reader import _NOT_ORDERED

    assert _NOT_ORDERED.search("ORDER")
    assert _NOT_ORDERED.search("202605-S0042 & ORDER")
    assert not _NOT_ORDERED.search("BACKORDER")
    assert not _NOT_ORDERED.search("REORDERED")


def test_columns_are_found_by_name_not_by_position():
    """The customer keeps this in two shapes that disagree about the columns.

    The single-sheet form has `STOCK LOCATION` and `REMARK`; the monthly book has `SUPPLIER`
    and `PO NO` and no location at all. A positional reader is right on one and silently
    wrong on the other.
    """
    from app.services.project_order_inquiry_reader import _header_map

    monthly = ("SO DATE", "S/O NO", "ITEM CODE", "QTY", "TOTAL QTY", "DELIVERY DATE",
               "PROJECT/CUSTOMER", "SUPPLIER", "PO NO ")
    form = ("SO DATE", "S/O NO", "ITEM CODE", "QTY", "DELIVERY DATE", "PROJECT/CUSTOMER",
            "STOCK LOCATION", "REMARK")

    m = _header_map(monthly)
    f = _header_map(form)
    assert m and f
    # Same field, different column in each shape - which is the whole point.
    assert m["item_code"] == 2 and f["item_code"] == 2
    assert m["po_number"] == 8 and "po_number" not in f
    assert f["location"] == 6 and "location" not in m


def test_a_sheet_that_is_not_order_inquiry_is_named_rather_than_ignored():
    """A workbook of monthly tabs where one silently fails to parse looks like a quiet month."""
    import io

    import openpyxl

    wb = openpyxl.Workbook()
    wb.active.title = "SUMMARY"
    wb.active.append(["just", "some", "totals"])
    buf = io.BytesIO()
    wb.save(buf)

    out = read_order_inquiry(buf.getvalue())
    assert out.ok is False
    assert "SUMMARY" in out.sheets_skipped
    assert out.problems


@pytest.mark.parametrize(
    "text, expected",
    [
        # Real text shapes measured across all 38 tabs of `JAN - DEC 2026 ORDERabc.xlsx`
        # (round 4, 19 Sep 2026): d.m.yyyy, d.mm.yyyy, dd-mm-yyyy, and one `//` typo.
        ("1.3.2026", date(2026, 3, 1)),
        ("1.12.2026", date(2026, 12, 1)),
        ("30-04-2026", date(2026, 4, 30)),
        ("27/10//2026", date(2026, 10, 27)),
        # Prose that must stay unparsed, same as before this change.
        ("MARCH - APRIL 2026", None),
        ("ASAP", None),
        ("WAREHOUSE MISSING", None),
        ("STOCK TAKE ADJUST", None),
        # An impossible date (month 13) - the shape matches, the value does not exist.
        ("13.13.2026", None),
    ],
)
def test_ac_17_a_text_date_cell_is_read_day_first(text, expected):
    """AC-17 (round 4, 19 Sep 2026). SO314593's own JUNE rows write the DELIVERY DATE cell
    as the literal text `1.6.2026`, day first - not an Excel date at all, which is why
    `_as_date` answered `None` for them regardless of anything 7.4 or its reversal did. A
    range (`MARCH - APRIL 2026`), a plain word (`ASAP`, `WAREHOUSE MISSING`) and an
    impossible date (`13.13.2026`, month 13) all still answer `None`."""
    from app.services.project_order_inquiry_reader import _as_date

    assert _as_date(text) == expected


def test_ac_17b_order_back_as_text_still_carries_no_date():
    """AC-17. `ORDER BACK BRW-BB` is still words, not a date - `_as_date` answers `None`,
    and the ORDER BACK detection (a separate regex over the raw cell, in the importer's own
    read loop) is untouched by this change."""
    from app.services.project_order_inquiry_reader import _ORDER_BACK, _as_date

    assert _as_date("ORDER BACK BRW-BB") is None
    assert _ORDER_BACK.search("ORDER BACK BRW-BB")


# --------------------------------------------------------------------------- #
# AC-OB-1/2/3 (`PLAN-oi-order-back-not-capped.md`, R1): the REMARK cell also says      #
# ORDER BACK, not only the delivery-date cell                                          #
# --------------------------------------------------------------------------- #


def _one_row_sheet(remark: str, delivery_date):
    """A minimal single-sheet-form workbook (`STOCK LOCATION` + `REMARK`), one data row."""
    import io

    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["SO NO", "ITEM CODE", "QTY", "DELIVERY DATE", "STOCK LOCATION", "REMARK"])
    ws.append(["ZZT-OB-SO", "ZZT-OB-ITEM", 3, delivery_date, "BRW-BB", remark])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_ac_ob_1_a_remark_cell_reading_order_back_also_sets_the_flag():
    """AC-OB-1 (R1). "order back" in the REMARK column, case-insensitive and whatever the
    whitespace between the two words, also makes the row an order back - not only the
    delivery-date cell the reader has always read (AC-OB-2). The delivery date cell here
    holds a REAL date, and it must survive: CS did not overwrite it, so the row keeps it
    (unlike the date-cell shape, where the words sit where the date would be)."""
    out = read_order_inquiry(_one_row_sheet("  Order   BACK  ", date(2026, 9, 20)))

    assert out.ok, out.problems
    row = out.rows[0]
    assert row.order_back is True
    assert row.delivery_date == date(2026, 9, 20)


def test_ac_ob_2_a_date_cell_reading_order_back_still_sets_the_flag_with_no_date():
    """AC-OB-2. Unchanged: the delivery-date cell reading `ORDER BACK` still sets the
    flag, with no delivery date (CS wrote words where the date belongs)."""
    out = read_order_inquiry(_one_row_sheet("", "ORDER BACK"))

    assert out.ok, out.problems
    row = out.rows[0]
    assert row.order_back is True
    assert row.delivery_date is None


def test_ac_ob_3_neither_cell_reading_order_back_leaves_the_flag_false():
    """AC-OB-3. A row with neither cell reading ORDER BACK reads `order_back=False`."""
    out = read_order_inquiry(_one_row_sheet("check with supplier", date(2026, 9, 20)))

    assert out.ok, out.problems
    row = out.rows[0]
    assert row.order_back is False
