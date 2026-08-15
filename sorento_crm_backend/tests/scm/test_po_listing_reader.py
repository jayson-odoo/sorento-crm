"""L1 - reading AutoCount's "Purchase Order Listing With Detail" (banded report).

Read against a REAL slice of the customer's own 13 MB export, not a fixture invented to suit
the parser: the first three PO blocks, both label rows, the report preamble, and the
`Doc Count:` marker with the summary section that follows it.

The three traps this file sets, each of which corrupts the import in silence:

  * **Merged cells shift the columns, in both directions.** The label `Curr.` sits at 47 with
    its value at 48; `Total` at 54 with its value at 50; the item code is written one column
    BEFORE its own label. Neither absolute columns nor nearest-label survives that, so values
    align to labels by sequence.
  * **A trailing "Final Summary By Items" section** repeats every item with
    `Item Code | UOM | Qty | Amount`, which looks exactly like line rows. Parsing stops at
    `Doc Count:` or every quantity is counted twice.
  * **Non-stock lines.** `MISC` and `HANDLING CHARGES` are real money on the order and no
    product at all. They are the order's cost, not any item's supply.

The report also cannot say what is still OUTSTANDING - its only quantity is what was ordered.
That is why this reader produces an order-book history and never an on-order position.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.services.scm.po_listing_reader import read_po_listing

FIXTURE = Path(__file__).parent / "fixtures" / "po_listing_with_detail_sample.xls"


@pytest.fixture(scope="module")
def result():
    return read_po_listing(FIXTURE.read_bytes())


def test_it_reads_the_orders_in_the_file(result):
    assert result.ok, result.problems
    numbers = [o.po_number for o in result.orders]
    # All three doc-number families the export uses are legitimate and none may be dropped.
    assert "202001-S0001" in numbers
    assert "SPO-2020/01-0001" in numbers


def test_a_header_binds_its_values_through_the_merged_columns(result):
    """The first block is the one absolute column mapping gets wrong."""
    order = next(o for o in result.orders if o.po_number == "202001-S0001")
    assert order.order_date == date(2020, 1, 2)
    assert order.supplier_code == "400-F020"
    assert order.supplier_name.startswith("FOSHAN ROYAL MIRROR")
    assert order.currency == "CNY"


def test_lines_belong_to_the_order_above_them(result):
    order = next(o for o in result.orders if o.po_number == "202001-S0001")
    assert [l.item_code for l in order.lines] == ["CBM1030"]
    line = order.lines[0]
    assert line.qty_ordered == 450.0
    assert line.unit_price == 24.0
    assert line.uom == "UNIT"
    assert line.description.startswith("CABANA MIRROR")


def test_an_order_with_several_lines_keeps_them_all_and_in_order(result):
    order = next(o for o in result.orders if o.po_number == "SPO-2020/01-0001")
    assert [l.item_code for l in order.lines] == [
        "SRTSCBD290A",
        "MISC",
        "HANDLING CHARGES",
    ]
    assert [l.line_no for l in order.lines] == [1, 2, 3]


def test_non_stock_lines_are_marked_rather_than_dropped_or_resolved(result):
    """`MISC` and `HANDLING CHARGES` are the order's cost, not an item's supply.

    Dropped, the order total no longer adds up. Treated as products, they arrive at the
    catalogue as two codes that will never match and are reported as failures every upload.
    """
    order = next(o for o in result.orders if o.po_number == "SPO-2020/01-0001")
    by_code = {l.item_code: l for l in order.lines}
    assert by_code["SRTSCBD290A"].is_stock_item is True
    assert by_code["MISC"].is_stock_item is False
    assert by_code["HANDLING CHARGES"].is_stock_item is False
    # Still carried, with their money, so the order total reconciles.
    assert by_code["HANDLING CHARGES"].amount == 3529.06


def test_parsing_stops_at_the_doc_count_marker(result):
    """The summary section repeats every item and would double every quantity.

    Asserted on a quantity rather than on a row count: the failure mode is not "extra rows",
    it is "the same item counted twice", and only the total shows that.
    """
    assert result.stopped_at_marker is True
    total_cbm = sum(
        l.qty_ordered
        for o in result.orders
        for l in o.lines
        if l.item_code == "CBM1030"
    )
    assert total_cbm == 450.0


def test_it_reports_what_was_ordered_and_never_what_is_outstanding(result):
    """The report has no received or outstanding column, so the reader must not invent one.

    A history file read as an outstanding book would import 1,586 closed 2020 orders as
    incoming supply and inflate every position in the system.
    """
    line = result.orders[0].lines[0]
    assert not hasattr(line, "qty_received")
    assert not hasattr(line, "qty_outstanding")
    assert result.is_order_book is True


def test_a_file_that_is_not_this_report_says_so_rather_than_returning_nothing():
    """An empty result and "this is the wrong report" are different answers."""
    from app.services.scm.outstanding_reader import sheet_rows  # noqa: F401

    other = (Path(__file__).parent / "fixtures" / "legacy_biff_sample.xls").read_bytes()
    out = read_po_listing(other)
    assert out.ok is False
    assert out.problems, "a wrong file must be explained, not silently empty"


# --------------------------------------------------------------------------- #
# The linkage the file carries on its own
# --------------------------------------------------------------------------- #

def test_a_description_only_row_is_a_note_and_not_a_broken_line(result):
    """812 of these in the customer's file, and every one was reported as a failure.

    A row with a line number, a description and no item or quantity is how this export
    writes a note. Calling them problems buries the real ones and teaches the operator to
    stop reading the list.
    """
    assert result.problems == []


def test_the_sales_order_a_note_names_is_captured():
    """The PO file carries SOME of the linkage on its own - `**SO:174830**` inside the block.

    Only 43 of 1,586 orders in the real 2020 file, so it supplements the Order Inquiry sheet
    rather than replacing it. Throwing it away would discard linkage nobody has to re-enter.
    """
    from app.services.scm.po_listing_reader import _SO_NOTE

    # The decoration varies; the digits do not.
    assert _SO_NOTE.findall("**SO:174830**") == ["174830"]
    assert _SO_NOTE.findall("-HOMEPRO @ SO:174830") == ["174830"]
    assert _SO_NOTE.findall("**ECO WORLD TRADING @ SO:176008**") == ["176008"]
    assert _SO_NOTE.findall("MOCHA PAPER HOLDER M203") == []


def test_the_sales_order_link_is_order_level_in_this_report(result):
    """A note sits BETWEEN lines, and nothing in THIS file says which side it describes.

    Guessing assigns one customer's stock to another customer's order. The pairing this
    report supports is "this PO relates to that SO", which is true whichever lines the note
    was written for; the per-line pairing comes from files that state it outright - the Order
    Inquiry sheet, and (since S5) the structured PO + SPO extract's `FromSODocList` column.

    The line type therefore HAS a `so_number` field, shared with that reader, and this report
    must leave every one of them unset: the claim written from a note names no item
    (`po_history_service._claim_so_link`), and a note guessed onto a line would be a
    line-level claim this file cannot support.
    """
    order = next(o for o in result.orders if o.po_number == "202001-S0001")
    assert hasattr(order, "so_numbers")
    for line in order.lines:
        assert line.so_number is None


def test_a_charge_is_recognised_however_it_is_spelled():
    """The real export contains `CURRENCY ROUNDING DIFFERENCE` three ways.

    `ROUDING` and `DIFERRENCE` are typed by hand, so an exact list rots on the next typo -
    and each miss becomes an item code reported as an unmatched product on every upload,
    for ever. Matching on a stem PAIR is deliberately narrow: both stems must be present,
    and no product could satisfy either pair. Across the customer's whole 2020 file this
    classifies 7 distinct codes, all of them genuine charges, and leaves 0 unmatched.
    """
    from app.services.scm.po_listing_reader import _is_charge_code

    assert _is_charge_code("CURRENCY ROUNDING DIFFERENCE")
    assert _is_charge_code("CURRENCY ROUDING DIFFERENCE")
    assert _is_charge_code("CURRENCY ROUNDING DIFERRENCE")
    assert _is_charge_code("HANDLING CHARGES")
    assert _is_charge_code("  misc  ")

    # And nothing that could be stock. `CBM1030` is a mirror, `SRTSCBD290A` a bidet seat.
    assert not _is_charge_code("CBM1030")
    assert not _is_charge_code("SRTSCBD290A")
    assert not _is_charge_code("MWCX7604-S")
    # A product whose name merely contains a charge word is still a product.
    assert not _is_charge_code("MISCELLANEOUS-TAP-500")
