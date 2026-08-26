"""The outstanding-SO book links its customer, and keeps the debtor code either way.

The importer read the debtor code and threw it away: nothing consumed
`sales_orders.customer_id` from this channel, so linking was deferred "to the day a
consumer exists". That day arrived with the plan's demand and trend popovers, which name
who ordered every line - and 2,546 of the 2,548 orders this feed had created read
"Unnamed customer" while the code sat in the file.

Two halves, and they fail differently:

* the code that RESOLVES links the customer, exactly as the PO side links its supplier;
* the code that resolves to NOBODY is still written to `sales_orders.debtor_code`, and is
  NOT reported as a problem - nothing is lost, the order stays attributable, and 2,546
  resolution issues would bury the rows in the same file that really did fail.

Plus the date half of the same story (AC-4.4): the extract states an SO DATE and the
header had none, so a product could carry open demand and no dated history at all. The
column is FILLED, never restated: a date already on the header stands.
"""
from __future__ import annotations

import uuid
from datetime import date
from io import BytesIO

import pytest
from sqlalchemy import text

from app.models.order import Customer
from app.services.scm import outstanding_import_service as svc
from app.services.scm.outstanding_reader import SO
from tests._pg_fixture import pg_session
from tests.scm._outstanding_workbooks import (
    Codes,
    make_codes,
    seed_catalogue,
    so_headers,
    so_row,
)

MARKER = "ZZTCUS"

#: The columns this file needs: the document, who it is for, the line, and the SO DATE
#: whose fill is under test.
# The ORDER TYPE column comes from `so_headers`: since QP1 an SO upload naming an order
# nothing can classify is refused outright, and these debtor codes are invented per run.
HEADERS = so_headers("S/O NO", "SO DATE", "DEBTOR CODE", "ITEM CODE", "QTY",
                     "DELIVERY DATE", "STOCK LOCATION")


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


@pytest.fixture()
def codes() -> Codes:
    c = make_codes()
    return c


@pytest.fixture()
def seeded(db, codes) -> Codes:
    seed_catalogue(db, codes)
    return codes


def _customer(db, code: str, name: str) -> str:
    cid = str(uuid.uuid4())
    db.add(Customer(id=cid, customer_code=code, customer_name=name, is_active=True))
    db.flush()
    return cid


def _debtor_code() -> str:
    return f"{MARKER}-{uuid.uuid4().hex[:8]}".upper()


def _upload(codes: Codes, debtor: str, *, so_date=date(2026, 5, 4), qty: float = 40,
            doc: str | None = None) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(list(HEADERS))
    ws.append(list(so_row(doc or codes.project_so, so_date, debtor, codes.item_rl, qty,
                          date(2026, 7, 1), codes.loc_project)))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _header(db, so_number: str):
    return db.execute(text(
        "SELECT customer_id::text AS customer_id, debtor_code, order_date "
        "FROM sales_orders WHERE so_number = :n"
    ), {"n": so_number}).mappings().first()


# --- the customer ---------------------------------------------------------------

def test_the_debtor_code_links_the_customer(seeded, db):
    """AC-4.3: the same three lines the PO side has always had for its supplier."""
    codes = seeded
    debtor = _debtor_code()
    cid = _customer(db, debtor, f"{MARKER} Vivo Homes")

    out = svc.apply(db, _upload(codes, debtor), SO)

    assert out["ok"] and out["applied"]["added"] == 1
    header = _header(db, codes.project_so)
    assert header["customer_id"] == cid
    assert header["debtor_code"] == debtor


def test_an_unresolvable_debtor_code_is_kept_and_is_not_a_problem(seeded, db):
    """The code is not lost, so there is nothing for the operator to fix in this file.

    Reported it would be 2,546 issues on the client's own book, on the same lists that
    carry the rows which really did fail - and the order would be no more attributable for
    it. Kept on the header, "Debtor 300-R009" is a name the buyer can act on, and the day
    that customer is created the code is what makes the link fixable.
    """
    codes = seeded
    debtor = _debtor_code()

    preview = svc.preview(db, _upload(codes, debtor), SO)
    out = svc.apply(db, _upload(codes, debtor), SO)

    assert [i.field for i in preview.resolution_issues] == []
    assert out["resolution_issues"] == []
    assert out["applied"]["added"] == 1, "the line is written; only the link is missing"
    header = _header(db, codes.project_so)
    assert header["customer_id"] is None
    assert header["debtor_code"] == debtor


def test_an_unresolvable_debtor_code_never_back_creates_a_customer(seeded, db):
    """Unlike the PO side's creditor code (`outstanding_import_service.py`, AC: back-create
    the supplier), an unresolvable debtor code creates nothing here. A back-created customer
    with no market segment would only make the demand-class fallback WORSE than the kept
    code already does, so this half of the import is deliberately unchanged.
    """
    codes = seeded
    debtor = _debtor_code()
    before = db.execute(text("SELECT count(*) FROM customers")).scalar()

    out = svc.apply(db, _upload(codes, debtor), SO)

    after = db.execute(text("SELECT count(*) FROM customers")).scalar()
    assert after == before, "an unresolvable debtor code back-created a customer"
    assert out.get("suppliers_created", 0) == 0
    assert db.execute(text("SELECT count(*) FROM customers WHERE customer_code = :c"),
                      {"c": debtor}).scalar() == 0


def test_a_second_upload_relinks_an_order_whose_customer_now_exists(seeded, db):
    """No backfill script exists (the code was never stored), so the re-upload IS the fix."""
    codes = seeded
    debtor = _debtor_code()
    svc.apply(db, _upload(codes, debtor), SO)
    assert _header(db, codes.project_so)["customer_id"] is None

    cid = _customer(db, debtor, f"{MARKER} Late Arrival")
    svc.apply(db, _upload(codes, debtor), SO)

    assert _header(db, codes.project_so)["customer_id"] == cid


# --- the order date (AC-4.4) ----------------------------------------------------

def test_the_so_date_fills_an_order_that_had_none(seeded, db):
    """The trend reads `order_date` over 24 months; an order imported without one carries
    open demand and no history at all."""
    codes = seeded

    svc.apply(db, _upload(codes, _debtor_code(), so_date=date(2026, 5, 4)), SO)

    assert _header(db, codes.project_so)["order_date"] == date(2026, 5, 4)


def test_a_date_already_on_the_header_wins(seeded, db):
    """FILL, not restate. A weekly re-upload silently overwriting a date somebody else set
    is the failure this column shape exists to avoid."""
    codes = seeded
    svc.apply(db, _upload(codes, _debtor_code(), so_date=date(2026, 5, 4)), SO)

    svc.apply(db, _upload(codes, _debtor_code(), so_date=date(2026, 6, 30), qty=50), SO)

    assert _header(db, codes.project_so)["order_date"] == date(2026, 5, 4)
