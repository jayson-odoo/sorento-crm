"""An Order Inquiry row is a SCHEDULED DELIVERY, not a restatement of a sales-order line.

This suite exists because we got the identity of a row wrong and the demand number was about
three times real. Read the customer's own workbook and the shape is unmistakable:

    SO356448 / SRTWT8270-RG
      JAN 26   24 due 2026-01-03      MAR 26   24 due 2026-03-07
      JAN 26   24 due 2026-01-24      MAR 26   24 due 2026-03-28
      FEB 26   24 due 2026-02-14      APR 26   24 due 2026-04-18
                                      MAY 26   20 due 2026-05-09

One sales-order line, called off in dated instalments, each listed under the month it is due.
So the key of a row is `(sales order, item, delivery date)`. The importer keyed it on
`(sales order, item)` and, worse, never noticed the line it had just created, so every tab
that mentioned a line inserted another one: 15,797 rows became 15,481 demand lines where
there are only 8,272 real instalments.

The workbook makes the same statement more than once on purpose. It carries month tabs
(`JAN 26`), roll-up tabs covering several months (`JAN - APR 26`, `MAY JUNE 26`) and dated
working snapshots (`21.7.26`). A roll-up repeats its component months verbatim - measured on
the real file, only 68 of 8,272 instalments are ever restated with a DIFFERENT quantity. So
the rule is: same instalment seen again is the same instalment, and where two tabs disagree
the later one wins.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models.base import set_company_scope
from app.models.inventory import Warehouse
from app.models.order import SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.scm import order_inquiry_service as svc
from tests._pg_fixture import pg_session

MARKER = "ZZTOIS"
SORENTO = "00000000-0000-0000-0000-000000000001"

SO_NUMBER = "SO900101"
ITEM = "ZZTOIS-ITEM-A"
LOCATION = "ZZTOIS-WH"
PROJECT = "ZZTOIS Project"


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    with pg_session() as s:
        set_company_scope(s, frozenset({SORENTO}))
        yield s


@pytest.fixture()
def world(db):
    cat = ProductCategory(id=_u(), category_code=f"{MARKER}-C-{uuid.uuid4().hex[:6]}",
                          category_name=f"{MARKER} cat")
    uom = UnitOfMeasure(id=_u(), uom_name=f"{MARKER} u",
                        uom_code=f"{MARKER[:4]}{uuid.uuid4().hex[:6]}")
    db.add_all([cat, uom])
    db.flush()
    product = Product(id=_u(), product_code=ITEM, product_name=f"{MARKER} item",
                      category_id=cat.id, base_uom_id=uom.id, list_price=0,
                      is_active=True, is_discontinued=False)
    wh = Warehouse(id=_u(), warehouse_code=LOCATION, warehouse_name=f"{MARKER} wh",
                   is_active=True, counts_as_available=True)
    db.add_all([product, wh])
    db.flush()
    return {"product": product, "warehouse": wh}


class _Row:
    def __init__(self, *, delivery_date, qty=24.0, sheet="JAN 26", so_number=SO_NUMBER,
                 item_code=ITEM, po_numbers=(), not_ordered=False, source_row=2):
        self.so_number = so_number
        self.item_code = item_code
        self.qty = qty
        self.so_date = date(2026, 1, 1)
        self.delivery_date = delivery_date
        self.project = PROJECT
        self.location = LOCATION
        self.supplier = ""
        self.po_numbers = po_numbers
        self.not_ordered = not_ordered
        self.sheet = sheet
        self.source_row = source_row


class _Parsed:
    def __init__(self, rows, sheets=None):
        self.rows = rows
        self.ok = True
        self.problems = []
        self.sheets_read = sheets or ["JAN 26"]
        self.sheets_skipped = []
        self.with_location = sum(1 for r in rows if r.location)
        self.po_claims = sum(len(r.po_numbers) for r in rows)


def _create(db, rows, sheets=None) -> dict:
    return svc._create_orders(db, _Parsed(rows, sheets), svc._now())


def _lines(db) -> list[SalesOrderLine]:
    order = db.query(SalesOrder).filter(SalesOrder.so_number == SO_NUMBER).one()
    return (
        db.query(SalesOrderLine)
        .filter(SalesOrderLine.sales_order_id == str(order.id))
        .order_by(SalesOrderLine.required_date)
        .all()
    )


# --------------------------------------------------------------------------- #
# identity: the instalment, not the line
# --------------------------------------------------------------------------- #

def test_two_dated_call_offs_of_one_line_are_two_instalments(db, world):
    """24 on 3 Jan and 24 on 24 Jan is 48 of demand, on two dates the timeline can read."""
    out = _create(db, [
        _Row(delivery_date=date(2026, 1, 3)),
        _Row(delivery_date=date(2026, 1, 24), source_row=3),
    ])

    assert out["lines_created"] == 2
    lines = _lines(db)
    assert [l.required_date for l in lines] == [date(2026, 1, 3), date(2026, 1, 24)]
    assert sum(float(l.qty_ordered) for l in lines) == 48.0


def test_the_same_instalment_restated_in_a_rollup_tab_is_not_a_second_instalment(db, world):
    """`JAN - APR 26` repeats `JAN 26` verbatim. Summing them doubles real demand."""
    out = _create(
        db,
        [
            _Row(delivery_date=date(2026, 1, 3), sheet="JAN 26"),
            _Row(delivery_date=date(2026, 1, 3), sheet="JAN - APR 26"),
        ],
        sheets=["JAN 26", "JAN - APR 26"],
    )

    assert out["lines_created"] == 1
    assert [float(l.qty_ordered) for l in _lines(db)] == [24.0]


def test_a_later_tab_that_disagrees_restates_the_instalment_rather_than_adding_one(db, world):
    """Measured on the real workbook: 68 of 8,272 instalments are genuinely restated."""
    _create(
        db,
        [
            _Row(delivery_date=date(2026, 5, 9), qty=24.0, sheet="APR 26"),
            _Row(delivery_date=date(2026, 5, 9), qty=20.0, sheet="MAY 26"),
        ],
        sheets=["APR 26", "MAY 26"],
    )

    lines = _lines(db)
    assert len(lines) == 1, "the correction became a second instalment"
    assert float(lines[0].qty_ordered) == 20.0, "the earlier tab won"


def test_uploading_the_same_workbook_twice_changes_nothing(db, world):
    """The customer re-sends the book every month. A non-idempotent import doubles demand."""
    rows = [
        _Row(delivery_date=date(2026, 1, 3)),
        _Row(delivery_date=date(2026, 1, 24), source_row=3),
    ]
    _create(db, rows)
    before = [(l.required_date, float(l.qty_ordered)) for l in _lines(db)]

    out = _create(db, rows)

    assert out["lines_created"] == 0
    assert [(l.required_date, float(l.qty_ordered)) for l in _lines(db)] == before


def test_rows_with_no_delivery_date_collapse_onto_one_instalment(db, world):
    """142 rows in the real book carry no date. Undated is one bucket, not one per sighting."""
    out = _create(
        db,
        [
            _Row(delivery_date=None, sheet="JAN 26"),
            _Row(delivery_date=None, sheet="FEB 26"),
        ],
        sheets=["JAN 26", "FEB 26"],
    )

    assert out["lines_created"] == 1
    assert _lines(db)[0].required_date is None


def test_two_rows_for_the_same_date_in_ONE_tab_are_summed(db, world):
    """`SO324252 / BRP60391N` is written as 80 and 40 on 2026-01-05 inside `JAN 26`.

    Within a single tab a repeat is a second call-off, not a restatement: the tab is one
    statement, and everything it says is part of it.
    """
    _create(db, [
        _Row(delivery_date=date(2026, 1, 5), qty=80.0),
        _Row(delivery_date=date(2026, 1, 5), qty=40.0, source_row=3),
    ])

    lines = _lines(db)
    assert len(lines) == 1
    assert float(lines[0].qty_ordered) == 120.0


def test_an_instalment_the_sheet_no_longer_states_is_withdrawn(db, world):
    """Same, different, new, gone. The fourth case is the one that was missing.

    The sheet is a full restatement of this feed's demand for the documents it names, so an
    instalment it has stopped stating has been withdrawn. Without this the plan keeps buying
    for a call-off that was cancelled or already shipped, and re-uploading a corrected book
    can only ever ADD.
    """
    _create(db, [
        _Row(delivery_date=date(2026, 1, 3)),
        _Row(delivery_date=date(2026, 1, 24), source_row=3),
    ])
    assert len(_lines(db)) == 2

    out = _create(db, [_Row(delivery_date=date(2026, 1, 3))])

    assert out["lines_withdrawn"] == 1
    assert [l.required_date for l in _lines(db)] == [date(2026, 1, 3)]


def test_duplicates_already_in_the_database_are_collapsed_on_the_next_upload(db, world):
    """The repair path. 15,481 rows describing 8,272 instalments are already stored.

    A lookup keyed by instalment keeps ONE of them and leaves the rest invisible to both the
    refresh and the withdrawal, so they survive every future upload and the count never comes
    down. Written as a test because the first attempt at this fix did exactly that.
    """
    order = SalesOrder(so_number=SO_NUMBER, status="open", source_system=svc.SOURCE_SYSTEM,
                       source_ref=svc.SOURCE)
    db.add(order)
    db.flush()
    for _ in range(3):
        db.add(SalesOrderLine(
            sales_order_id=str(order.id), product_id=str(world["product"].id),
            warehouse_id=str(world["warehouse"].id), qty_ordered=24, qty_delivered=0,
            line_status="open", required_date=date(2026, 1, 3),
            source_system=svc.SOURCE_SYSTEM, source_ref=svc.SOURCE,
        ))
    db.flush()
    assert len(_lines(db)) == 3

    out = _create(db, [_Row(delivery_date=date(2026, 1, 3), qty=20.0)])

    assert out["lines_withdrawn"] == 2
    lines = _lines(db)
    assert len(lines) == 1
    assert float(lines[0].qty_ordered) == 20.0, "the survivor carries the sheet's figure"


def test_a_document_the_sheet_does_not_mention_is_left_alone(db, world):
    """Scoped to the documents in the file. A book covering one month must not withdraw the
    demand of every order it does not happen to mention."""
    _create(db, [_Row(delivery_date=date(2026, 1, 3))])
    _create(db, [_Row(so_number="SO900102", delivery_date=date(2026, 2, 3))])

    _create(db, [_Row(delivery_date=date(2026, 1, 3))])

    other = db.query(SalesOrder).filter(SalesOrder.so_number == "SO900102").one()
    assert db.query(SalesOrderLine).filter(
        SalesOrderLine.sales_order_id == str(other.id)
    ).count() == 1


def test_the_collapse_is_reported_rather_than_silent(db, world):
    """A number that drops from 15,797 to 8,272 has to be visible on the upload screen."""
    out = _create(
        db,
        [
            _Row(delivery_date=date(2026, 1, 3), sheet="JAN 26"),
            _Row(delivery_date=date(2026, 1, 3), sheet="JAN - APR 26"),
        ],
        sheets=["JAN 26", "JAN - APR 26"],
    )

    assert out["rows_restating_an_instalment"] == 1


# --------------------------------------------------------------------------- #
# what CS decided, carried on the line
# --------------------------------------------------------------------------- #

def test_a_line_the_sheet_says_ORDER_is_waiting_to_be_purchased(db, world):
    _create(db, [_Row(delivery_date=date(2026, 1, 3), not_ordered=True)])
    assert _lines(db)[0].purchasing_status == "needs_purchase"


def test_a_line_the_sheet_pairs_with_a_purchase_order_is_already_ordered(db, world):
    _create(db, [_Row(delivery_date=date(2026, 1, 3), po_numbers=("202510-S0026",))])
    assert _lines(db)[0].purchasing_status == "ordered"


def test_the_quantity_CS_asks_for_is_recorded_apart_from_the_customer_quantity(db, world):
    """`qty_required` is what to plan for; `qty_ordered` is what the customer asked for.

    They agree on a line this sheet created, because the sheet is the only statement we have.
    They will not agree once the sales-order book lands and CS calls off part of a line, and
    the netting has to read the one CS decided.
    """
    _create(db, [_Row(delivery_date=date(2026, 1, 3), qty=24.0)])

    line = _lines(db)[0]
    assert float(line.qty_required) == 24.0
    assert float(line.qty_ordered) == 24.0
