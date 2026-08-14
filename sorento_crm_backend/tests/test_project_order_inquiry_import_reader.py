"""L3 - reading the Order Inquiry sheet, against a real slice of the customer's own file.

This sheet is the reason no curation screen is needed: it carries the stock location a sales
order line ships from, and the purchase order that line is waiting on. Both were believed
missing.

Three shapes in the nine fixture rows, all of them real:

  * `ORDER`                          - nothing placed for this line yet
  * `202605-S0042`                   - waiting on one purchase order
  * `202606-S0024 & 202607-S0043`    - ONE line split across two purchase orders
  * `202605-S0042 & ORDER`           - partly ordered, partly not

The reader moved to Project Sales ownership with its importer (ADR 0010), so this suite lives
in `tests/` rather than `tests/scm/`. The workbook itself stays in `tests/scm/fixtures/`
because two SCM suites - the purchase-history routes and the SO<->PO link test - read the same
file, and one sample file is better than three copies drifting apart.
"""
from __future__ import annotations

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
