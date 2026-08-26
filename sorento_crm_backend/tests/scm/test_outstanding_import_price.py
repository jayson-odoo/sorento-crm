"""The outstanding-SO book keeps what the customer pays for the line.

The demand popover quotes a unit price on every line it lists, and on the client's own
database that price was blank on every one of them: `sales_order_lines.unit_price` had no
writer at all on this channel, while the extract has carried a `UNIT PRICE` column since
migration 338 seeded the alias for it. The buyer's "sells RM 0.94" question was therefore
answerable from the file and not from the screen.

Three properties, and they fail differently:

* the price the file states lands on the line;
* a price the file does NOT state stays NULL, never 0 - a zero reads as free goods, and it
  is the column the cash side ranks on;
* a re-upload of the same file is still `unchanged`, and a price that really moved is
  written and reported as `updated`. Both compared at 2 decimal places, which is the
  precision the column stores, so a 0.945 in the sheet cannot flap against the 0.94 (or
  0.95) that came back out of it.
"""
from __future__ import annotations

import uuid
from datetime import date
from io import BytesIO

import pytest
from sqlalchemy import text

from app.services.scm import outstanding_import_service as svc
from app.services.scm.outstanding_reader import SO
from tests._pg_fixture import pg_session
from tests.scm._outstanding_workbooks import (
    Codes,
    DEALER_ORDER_TYPE,
    make_codes,
    seed_catalogue,
    so_headers,
)

MARKER = "ZZTPRC"

#: The document, the line, and the money column under test.
HEADERS = so_headers("S/O NO", "DEBTOR CODE", "ITEM CODE", "QTY", "UNIT PRICE",
                     "DELIVERY DATE", "STOCK LOCATION")

#: The same file without the money column at all, so an absent price is absent rather
#: than blank-in-a-column-that-exists.
HEADERS_NO_PRICE = so_headers("S/O NO", "DEBTOR CODE", "ITEM CODE", "QTY",
                              "DELIVERY DATE", "STOCK LOCATION")


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


@pytest.fixture()
def seeded(db) -> Codes:
    codes = make_codes()
    seed_catalogue(db, codes)
    return codes


def _upload(codes: Codes, price, *, qty: float = 40, headers=HEADERS) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(list(headers))
    row = [codes.project_so, f"{MARKER}-{uuid.uuid4().hex[:6]}".upper(), codes.item_rl, qty]
    if headers is HEADERS:
        row.append(price)
    # The class the file has to state since QP1, or the whole upload is refused - this
    # file's debtor code is invented per run and resolves to no customer.
    row += [date(2026, 7, 1), codes.loc_project, DEALER_ORDER_TYPE]
    ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _price(db, so_number: str):
    return db.execute(text(
        "SELECT sol.unit_price FROM sales_order_lines sol "
        "JOIN sales_orders so ON so.id = sol.sales_order_id "
        "WHERE so.so_number = :n"
    ), {"n": so_number}).scalar()


def test_the_line_carries_the_price_the_file_states(seeded, db):
    """The demand popover quotes this column; nothing else on this channel writes it."""
    codes = seeded

    out = svc.apply(db, _upload(codes, 0.94), SO)

    assert out["ok"] and out["applied"]["added"] == 1
    assert float(_price(db, codes.project_so)) == pytest.approx(0.94)


def test_a_price_the_file_does_not_state_stays_null(seeded, db):
    """A zero would read as free goods. Absent is absent, exactly as the PO cost is."""
    codes = seeded

    svc.apply(db, _upload(codes, None, headers=HEADERS_NO_PRICE), SO)

    assert _price(db, codes.project_so) is None


def test_a_re_upload_of_the_same_file_reports_unchanged(seeded, db):
    """Idempotency: the same book twice must not churn every line into an update."""
    codes = seeded
    svc.apply(db, _upload(codes, 0.94), SO)

    out = svc.apply(db, _upload(codes, 0.94), SO)

    assert out["applied"]["unchanged"] == 1
    assert out["applied"]["updated"] == 0
    assert float(_price(db, codes.project_so)) == pytest.approx(0.94)


def test_a_third_decimal_in_the_sheet_does_not_flap(seeded, db):
    """The column stores 2 decimals, so 0.945 comes back out as 0.95 and re-uploading the
    same sheet must not read as a price change on every single run."""
    codes = seeded
    svc.apply(db, _upload(codes, 0.945), SO)

    out = svc.apply(db, _upload(codes, 0.945), SO)

    assert out["applied"]["unchanged"] == 1
    assert out["applied"]["updated"] == 0


def test_a_price_that_really_moved_is_written_and_reported(seeded, db):
    """The line is otherwise identical, so without this the buyer reads last week's money
    for ever: nothing else on this channel ever revisits the column."""
    codes = seeded
    svc.apply(db, _upload(codes, 0.94), SO)

    out = svc.apply(db, _upload(codes, 1.10), SO)

    assert out["applied"]["updated"] == 1
    assert out["applied"]["unchanged"] == 0
    assert float(_price(db, codes.project_so)) == pytest.approx(1.10)
