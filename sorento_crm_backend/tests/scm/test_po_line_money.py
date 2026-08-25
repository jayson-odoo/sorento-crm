"""The purchase-order book keeps the WHOLE money line, not just the unit cost.

The supply-side twin of `test_so_line_money.py`, and it closes the same gap on the other
book: the AutoCount PO detail listing states a discount and a line total beside the unit
cost, and `purchase_order_lines` had no column for either - so the reader dropped them and
the buyer's screen could only ever print a cost beside a quantity.

`UOM` is here for a third reason: it has resolved for `outstanding_po` since migration 311,
the line now has a per-line override column, and a purchase order written in cartons must not
read in pieces because the product master's base unit says so.

Three properties, and they fail differently:

* the reader carries all three off the sheet;
* the write path lands the discount and the line total on the line's own columns, and the
  stated UoM on the line's per-line override;
* a column the file does not state stays NULL - a zero discount reads as "no discount was
  given", which is a claim the file never made.
"""
from __future__ import annotations

import uuid
from datetime import date
from io import BytesIO

import openpyxl
import pytest
from sqlalchemy import text

from app.services.import_alias_service import AliasResolver
from app.services.scm import outstanding_import_service as svc
from app.services.scm.outstanding_reader import PO, read_workbook
from tests._pg_fixture import pg_session
from tests.scm._outstanding_workbooks import Codes, make_codes, seed_catalogue, seed_suppliers

#: The document, the line, and every money-shaped column the AutoCount detail listing
#: carries. `UOM` is here for the same reason the two money columns are: it resolves, and
#: the line has a per-line override column waiting for it.
HEADERS = ("PO NO", "CREDITOR CODE", "ITEM CODE", "QTY ORDERED", "UOM", "UNIT COST",
           "DISCOUNT", "TOTAL (INC)", "ETA", "STOCK LOCATION")

#: The same file with none of the three, so an absent figure is absent rather than
#: blank-in-a-column-that-exists.
HEADERS_BARE = ("PO NO", "CREDITOR CODE", "ITEM CODE", "QTY ORDERED", "ETA",
                "STOCK LOCATION")


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


@pytest.fixture()
def seeded(db) -> Codes:
    codes = make_codes()
    seed_catalogue(db, codes, doc_type="outstanding_po")
    seed_suppliers(db, codes)
    return codes


def _workbook(codes: Codes, *, uom="BOX", cost=100, discount=15, total=985,
              qty: float = 10, headers=HEADERS) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(list(headers))
    row = [codes.main_po, codes.creditor_main, codes.item_rl, qty]
    if headers is HEADERS:
        row += [uom, cost, discount, total]
    row += [date(2026, 7, 1), codes.loc_project]
    ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _line(db, po_number: str):
    return db.execute(text(
        "SELECT pol.unit_cost, pol.discount, pol.line_total, pol.uom "
        "FROM purchase_order_lines pol "
        "JOIN purchase_orders po ON po.id = pol.purchase_order_id "
        "WHERE po.po_number = :n"
    ), {"n": po_number}).one()


def test_the_reader_carries_uom_discount_and_total(seeded, db):
    """All three resolve through the alias table; the reader used to drop two of them."""
    codes = seeded
    resolver = AliasResolver.for_doc_type(db, PO)
    if not resolver.known_fields:
        pytest.skip("no outstanding_po aliases seeded in this database")

    read = read_workbook(_workbook(codes), PO, resolver)

    assert read.lines, read.problems
    extra = read.extras[str(read.lines[0].row_ref)]
    assert extra["uom"] == "BOX"
    assert extra["discount"] == pytest.approx(15.0)
    assert extra["total_inc"] == pytest.approx(985.0)


def test_the_line_carries_the_discount_the_total_and_the_uom(seeded, db):
    """What the supplier actually charged, on the row the detail page prints."""
    codes = seeded

    out = svc.apply(db, _workbook(codes), PO)

    assert out["ok"] and out["applied"]["added"] == 1
    unit_cost, discount, line_total, uom = _line(db, codes.main_po)
    assert float(unit_cost) == pytest.approx(100)
    assert float(discount) == pytest.approx(15)
    assert float(line_total) == pytest.approx(985)
    assert uom == "BOX"


def test_a_figure_the_file_does_not_state_stays_null(seeded, db):
    """A zero discount claims a discount of nothing was given. Absent is absent."""
    codes = seeded

    svc.apply(db, _workbook(codes, headers=HEADERS_BARE), PO)

    unit_cost, discount, line_total, uom = _line(db, codes.main_po)
    assert unit_cost is None
    assert discount is None
    assert line_total is None
    assert uom is None


def test_a_re_upload_of_the_same_file_still_reports_unchanged(seeded, db):
    """Idempotency, with three more columns in the comparison than it had before."""
    codes = seeded
    svc.apply(db, _workbook(codes), PO)

    out = svc.apply(db, _workbook(codes), PO)

    assert out["applied"]["unchanged"] == 1
    assert out["applied"]["updated"] == 0


def test_a_discount_that_really_moved_is_written_and_reported(seeded, db):
    """Nothing else on this channel revisits these columns, so a frozen line quotes last
    week's money for ever - the same rule `unit_cost` already follows."""
    codes = seeded
    svc.apply(db, _workbook(codes), PO)

    out = svc.apply(db, _workbook(codes, discount=25, total=975), PO)

    assert out["applied"]["updated"] == 1
    _unit_cost, discount, line_total, _uom = _line(db, codes.main_po)
    assert float(discount) == pytest.approx(25)
    assert float(line_total) == pytest.approx(975)
