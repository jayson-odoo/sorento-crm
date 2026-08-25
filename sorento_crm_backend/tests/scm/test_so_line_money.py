"""The sales-order book keeps the WHOLE money line, not just the unit price.

`UOM`, `Discount` and `Total (Inc)` have resolved through `import_field_alias` since
migration 357 seeded them, and the reader threw all three away: `extras` was built by hand
and simply did not list them. Nothing reported the loss, because resolving a header and
reading it are two different things - the columns were "known", so they never appeared in
the unrecognised-column warning either.

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
from app.services.scm.outstanding_reader import SO, read_workbook
from tests._pg_fixture import pg_session
from tests.scm._outstanding_workbooks import Codes, make_codes, seed_catalogue

MARKER = "ZZTMON"

#: The document, the line, and every money-shaped column the AutoCount detail listing
#: carries. `UOM` is here for the same reason the two money columns are: it resolves, and
#: the line has a per-line override column waiting for it.
HEADERS = ("S/O NO", "DEBTOR CODE", "ITEM CODE", "QTY", "UOM", "UNIT PRICE", "DISCOUNT",
           "TOTAL (INC)", "DELIVERY DATE", "STOCK LOCATION")

#: The same file with none of the three, so an absent figure is absent rather than
#: blank-in-a-column-that-exists.
HEADERS_BARE = ("S/O NO", "DEBTOR CODE", "ITEM CODE", "QTY", "DELIVERY DATE",
                "STOCK LOCATION")


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


@pytest.fixture()
def seeded(db) -> Codes:
    codes = make_codes()
    seed_catalogue(db, codes)
    return codes


def _workbook(codes: Codes, *, uom="BOX", price=100, discount=15, total=985,
              qty: float = 10, headers=HEADERS) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(list(headers))
    row = [codes.project_so, f"{MARKER}-{uuid.uuid4().hex[:6]}".upper(), codes.item_rl, qty]
    if headers is HEADERS:
        row += [uom, price, discount, total]
    row += [date(2026, 7, 1), codes.loc_project]
    ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _line(db, so_number: str):
    return db.execute(text(
        "SELECT sol.unit_price, sol.discount, sol.line_total, sol.uom "
        "FROM sales_order_lines sol "
        "JOIN sales_orders so ON so.id = sol.sales_order_id "
        "WHERE so.so_number = :n"
    ), {"n": so_number}).one()


def test_the_reader_carries_uom_discount_and_total(seeded, db):
    """All three resolve through the alias table; the reader used to drop them silently."""
    codes = seeded
    resolver = AliasResolver.for_doc_type(db, SO)
    if not resolver.known_fields:
        pytest.skip("no outstanding_so aliases seeded in this database")

    read = read_workbook(_workbook(codes), SO, resolver)

    assert read.lines, read.problems
    extra = read.extras[str(read.lines[0].row_ref)]
    assert extra["uom"] == "BOX"
    assert extra["discount"] == pytest.approx(15.0)
    assert extra["total_inc"] == pytest.approx(985.0)


def test_the_line_carries_the_discount_the_total_and_the_uom(seeded, db):
    """What the customer was actually charged, on the row the detail page prints."""
    codes = seeded

    out = svc.apply(db, _workbook(codes), SO)

    assert out["ok"] and out["applied"]["added"] == 1
    unit_price, discount, line_total, uom = _line(db, codes.project_so)
    assert float(unit_price) == pytest.approx(100)
    assert float(discount) == pytest.approx(15)
    assert float(line_total) == pytest.approx(985)
    assert uom == "BOX"


def test_a_figure_the_file_does_not_state_stays_null(seeded, db):
    """A zero discount claims a discount of nothing was given. Absent is absent."""
    codes = seeded

    svc.apply(db, _workbook(codes, headers=HEADERS_BARE), SO)

    unit_price, discount, line_total, uom = _line(db, codes.project_so)
    assert unit_price is None
    assert discount is None
    assert line_total is None
    assert uom is None


def test_a_re_upload_of_the_same_file_still_reports_unchanged(seeded, db):
    """Idempotency, with three more columns in the comparison than it had before."""
    codes = seeded
    svc.apply(db, _workbook(codes), SO)

    out = svc.apply(db, _workbook(codes), SO)

    assert out["applied"]["unchanged"] == 1
    assert out["applied"]["updated"] == 0


def test_a_discount_that_really_moved_is_written_and_reported(seeded, db):
    """Nothing else on this channel revisits these columns, so a frozen line quotes last
    week's money for ever - the same rule `unit_price` already follows."""
    codes = seeded
    svc.apply(db, _workbook(codes), SO)

    out = svc.apply(db, _workbook(codes, discount=25, total=975), SO)

    assert out["applied"]["updated"] == 1
    _unit_price, discount, line_total, _uom = _line(db, codes.project_so)
    assert float(discount) == pytest.approx(25)
    assert float(line_total) == pytest.approx(975)
