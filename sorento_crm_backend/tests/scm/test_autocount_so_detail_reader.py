"""The client's real AutoCount sales-order detail listing, and the trap inside it.

Provenance: `autocount_so_detail_excerpt.xlsx` is a verbatim excerpt of
"Project Sales Order 2020 - 2026.xlsx" (81,361 rows, 11,275 documents, supplied 7 Aug 2026).
Ten rows, chosen for what they exercise rather than for being the first ten: two ordinary
orders, a `MISC` item, an `IP` item-package line, a blank-item package caption, a
"TRANSPORT CHARGE" row with a quantity but no item code, and the grand-totals row the report
prints at the bottom.

The trap this file carries: **its `Qty` column is the quantity ORDERED**, and the outstanding
figure sits in a separate `Remaining Qty` column. The seeded alias table already mapped `QTY`
to `qty_outstanding`, so onboarding this layout by adding a `Doc No` alias and nothing else
would have made every partly-delivered line import with its ordered quantity read as
outstanding. Committed demand inflated, every buy computed from it inflated, on a file that
imports perfectly cleanly and stays stable upload after upload.

The netting cases are built in memory rather than cut from the client file, and deliberately
so: **every one of its 81,361 lines is fully delivered**, so the file itself cannot
demonstrate a partial. That fact is asserted here too, because it is the answer to "can we
upload this to get the demand" and it is not the answer anybody expects.
"""
from __future__ import annotations

import io
from pathlib import Path

import openpyxl
import pytest

from app.services.import_alias_service import AliasResolver
from app.services.scm.outstanding_reader import PO, SO, read_workbook
from tests._pg_fixture import pg_session

_FIX = Path(__file__).parent / "fixtures"

#: The client's header row, verbatim.
AUTOCOUNT_HEADERS = [
    "Doc No", "Doc Date", "Delivery Date", "Debtor Code", "Debtor Name", "Agent",
    "Ref Doc No", "Ref", "Remark 1", "Item Code", "Item Description", "Location",
    "Qty", "Transfered Qty", "Remaining Qty", "Unit Price", "Discount", "Total (Inc)",
    "Note",
]


@pytest.fixture()
def resolver():
    """The real alias table, so the test proves the SEEDED aliases resolve this wording.

    Skips rather than passes on a database with no aliases: a green test there would be
    stating nothing at all.
    """
    with pg_session() as db:
        r = AliasResolver.for_doc_type(db, SO)
        if not r.known_fields:
            pytest.skip("no outstanding_so aliases seeded in this database")
        yield r


@pytest.fixture()
def po_resolver():
    with pg_session() as db:
        r = AliasResolver.for_doc_type(db, PO)
        if not r.known_fields:
            pytest.skip("no outstanding_po aliases seeded in this database")
        yield r


def _wb(headers, rows) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(list(headers))
    for r in rows:
        ws.append(list(r))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _autocount_row(**over):
    """One row in the client's column order, so a test states only what it varies."""
    row = {
        "Doc No": "SO900001", "Doc Date": "2026-07-01", "Delivery Date": "2026-08-15",
        "Debtor Code": "300-Z001", "Debtor Name": "ZZT CUSTOMER", "Agent": "ACT",
        "Ref Doc No": None, "Ref": None, "Remark 1": None,
        "Item Code": "ZZT-SKU-1", "Item Description": "a basin", "Location": "BRW",
        "Qty": 10, "Transfered Qty": None, "Remaining Qty": None,
        "Unit Price": 100, "Discount": None, "Total (Inc)": 1000, "Note": "PS26-0001",
    }
    row.update(over)
    return [row[h] for h in AUTOCOUNT_HEADERS]


# --------------------------------------------------------------------------- #
# the trap: which column is the outstanding one
# --------------------------------------------------------------------------- #

def test_ordered_minus_delivered_is_the_outstanding_quantity(resolver):
    """THE defect this file would otherwise have caused.

    Ten ordered, four already delivered. The outstanding figure is six. Reading the `Qty`
    column as outstanding would say ten, which is not a rounding error: it is a 67% overstated
    commitment on this line, and the buy computed from it is overstated by the same.
    """
    data = _wb(AUTOCOUNT_HEADERS, [_autocount_row(Qty=10, **{"Transfered Qty": 4})])

    res = read_workbook(data, SO, resolver)

    assert [ln.qty for ln in res.lines] == [6.0], (
        "the quantity column is ORDERED when the file also states what has gone out"
    )


def test_the_stated_remaining_quantity_wins_over_the_arithmetic(resolver):
    """When the file says the remaining figure outright, believe it.

    Deliberately inconsistent input: ordered 10, delivered 4, remaining 5. Real exports do
    disagree with themselves (two rows of this client's own file report a remaining quantity
    of -1 against 175 ordered and 176 delivered). The stated column is the report's own
    answer, and second-guessing it with arithmetic would substitute our view for theirs.
    """
    data = _wb(AUTOCOUNT_HEADERS, [
        _autocount_row(Qty=10, **{"Transfered Qty": 4, "Remaining Qty": 5}),
    ])

    res = read_workbook(data, SO, resolver)

    assert [ln.qty for ln in res.lines] == [5.0]


def test_the_remaining_column_wins_even_when_it_comes_first(resolver):
    """GUARD: the choice must not be decided by column order.

    This is why `qty_remaining` is its own field rather than a second alias onto
    `qty_outstanding`. Two headers pointing at one field resolve by position, so a file that
    listed the remaining column before the quantity column would have silently gone back to
    reading ORDERED as outstanding - the exact defect, reintroduced by a column reshuffle
    nobody would think to re-test.
    """
    headers = ["Doc No", "Delivery Date", "Item Code", "Location", "Remaining Qty", "Qty"]
    data = _wb(headers, [["SO900002", "2026-08-15", "ZZT-SKU-1", "BRW", 3, 10]])

    res = read_workbook(data, SO, resolver)

    assert [ln.qty for ln in res.lines] == [3.0]


def test_a_file_with_only_a_quantity_column_is_unchanged(resolver):
    """GUARD: the existing single-column shape must not start netting against nothing.

    An outstanding-only report states one already-netted figure. Nothing in this change may
    reinterpret it.
    """
    headers = ["S/O NO", "DELIVERY DATE", "ITEM CODE", "STOCK LOCATION", "QTY"]
    data = _wb(headers, [["SO900003", "2026-08-15", "ZZT-SKU-1", "BRW", 7]])

    res = read_workbook(data, SO, resolver)

    assert [ln.qty for ln in res.lines] == [7.0]


def test_the_purchase_order_side_honours_a_stated_remaining_column_too(po_resolver):
    """The same tool emits the purchase-order listing, so it gets the same rule.

    The PO path already netted `qty_received`; what it lacked was the stated-remaining case.
    Ordered 10, received 4, remaining 5 - the file's own answer, not ours.
    """
    headers = ["Doc No", "ETA", "Item Code", "Location", "Qty Ordered",
               "Transfered Qty", "Remaining Qty"]
    data = _wb(headers, [["PO900001", "2026-09-01", "ZZT-SKU-1", "BRW", 10, 4, 5]])

    res = read_workbook(data, PO, po_resolver)

    assert [ln.qty for ln in res.lines] == [5.0]


# --------------------------------------------------------------------------- #
# layout rows are not failed rows
# --------------------------------------------------------------------------- #

def test_a_row_with_no_item_and_no_quantity_is_layout_not_a_failure(resolver):
    """9,141 of the client's 81,362 rows are package captions and spacers.

    Reporting each as a failed row buries the six rows that really did fail under nine
    thousand that were never lines at all, and an import screen showing 9,147 problems reads
    as a broken file. They are counted rather than dropped in silence, because a big number
    appearing there is itself worth seeing.
    """
    data = _wb(AUTOCOUNT_HEADERS, [
        _autocount_row(**{"Item Code": None, "Item Description": "ITEM PACKAGE :",
                          "Location": None, "Qty": 0, "Transfered Qty": 0}),
        _autocount_row(Qty=10, **{"Transfered Qty": 4}),
    ])

    res = read_workbook(data, SO, resolver)

    assert res.layout_rows == 1
    assert res.problems == []
    assert len(res.lines) == 1


def test_a_row_with_a_quantity_but_no_item_is_still_a_problem(resolver):
    """GUARD: the layout rule must not swallow a real gap.

    Two shapes hit this. The report's grand-totals row carries a quantity and no document,
    and a "TRANSPORT CHARGE" line carries a quantity against no item code - a charge the
    order really does bill, which the plan cannot place and must therefore name.
    """
    data = _wb(AUTOCOUNT_HEADERS, [
        _autocount_row(**{"Item Code": None, "Item Description": "TRANSPORT CHARGE",
                          "Qty": 1, "Transfered Qty": 1, "Remaining Qty": 1}),
    ])

    res = read_workbook(data, SO, resolver)

    assert res.layout_rows == 0
    assert [p.reason for p in res.problems] == ["missing item_code"]


# --------------------------------------------------------------------------- #
# the client's real file
# --------------------------------------------------------------------------- #

def test_the_real_header_row_resolves_every_column_the_plan_needs(resolver):
    """The point of the alias table: onboarding a wording is INSERTs, not code.

    Asserted on the header row rather than on rows, because a missing required column stops
    the read before any row is examined and the failure would otherwise read as "no data".
    """
    for header, field in (
        ("Doc No", "so_number"),
        ("Doc Date", "so_date"),
        ("Delivery Date", "required_date"),
        ("Debtor Code", "debtor_code"),
        ("Debtor Name", "customer_name"),
        ("Item Code", "item_code"),
        ("Location", "stock_location"),
        ("Qty", "qty_outstanding"),
        ("Transfered Qty", "qty_delivered"),
        ("Remaining Qty", "qty_remaining"),
        ("Note", "remark"),
    ):
        assert resolver.field_for_header(header) == field, header


def test_the_clients_excerpt_reads_with_no_missing_columns(resolver):
    """A read of the genuine file, not of a fixture written to a spec."""
    res = read_workbook(
        (_FIX / "autocount_so_detail_excerpt.xlsx").read_bytes(), SO, resolver)

    assert res.missing_columns == []
    assert res.total_rows == 10


def test_the_clients_file_states_no_outstanding_demand_at_all(resolver):
    """The answer to "can we upload this to get the demand", and it is no.

    Every line in the excerpt - and every one of the 81,361 lines in the file it came from -
    has been fully delivered. So the reader yields nothing, which is correct and is the whole
    point: this is delivered sales HISTORY, not the outstanding order book. Uploading it
    through this channel adds no committed demand. A test that quietly expected some lines
    would be asserting a hope.
    """
    res = read_workbook(
        (_FIX / "autocount_so_detail_excerpt.xlsx").read_bytes(), SO, resolver)

    assert res.lines == []
    # The caption row is layout; the transport charge and the totals row are named.
    assert res.layout_rows == 1
    assert sorted(p.reason for p in res.problems) == [
        "missing item_code", "missing so_number, item_code",
    ]


def test_every_column_of_the_clients_real_header_is_recognised(resolver):
    """AC-1.1, against the client's own file rather than a header list somebody retyped.

    This test used to assert the opposite - that `Agent` and `Discount` were REPORTED as
    unrecognised - on the reasoning that silence about a column nobody read is how a file
    looks understood when it is not. The client's answer settled it: a warning list that is
    never empty on a file we have already onboarded is a list nobody reads, and it sits on the
    same screen as the columns that really are new.

    So the seven that were left over are now alias rows. `Agent` resolves to a field the
    reader carries and the classification spends (AC-3); the rest resolve to fields nothing
    consumes, which is the same "we know what this column is and we are not interested"
    mechanism `Unit Price` and `Note` have always used. What still appears here is a column
    this export has never carried - which is exactly what the list is for.
    """
    res = read_workbook(
        (_FIX / "autocount_so_detail_excerpt.xlsx").read_bytes(), SO, resolver)

    assert res.unmapped_headers == [], (
        f"the client's own export still reports unrecognised columns: {res.unmapped_headers}")


def test_a_column_this_export_has_never_carried_is_still_reported(resolver):
    """The other half: the warning list has to keep working.

    Emptying it by aliasing everything in sight would trade one failure for a worse one - an
    export that grows a column, silently dropped, producing confidently wrong numbers.
    """
    data = _wb(AUTOCOUNT_HEADERS + ["Rebate Scheme"],
               [_autocount_row() + ["Q3 dealer scheme"]])

    res = read_workbook(data, SO, resolver)

    assert res.unmapped_headers == ["Rebate Scheme"]
