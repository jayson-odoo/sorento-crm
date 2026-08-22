"""N3 - the Order Inquiry sheet is a source of sales orders, not just an annotation.

> "order inquiry is essentially SO ... to not involve the CS department which handles the SO,
> I can ask Joey to upload order inquiries, so the SO should be a proper SO with header and
> line"

That promotes a SECOND writer onto `sales_orders`, and this suite exists mostly to pin the
ownership rule that makes two writers safe:

* no such order        -> the sheet creates it, header and lines
* an order it created  -> the sheet refreshes it
* anybody else's order -> the sheet does not touch a single figure

The last one is the important one. "Last writer wins" across two feeds with different refresh
rhythms is how a quantity CS corrected silently reverts to what a spreadsheet said last week.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models.base import set_company_scope
from app.models.inventory import Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services import project_order_inquiry_import_service as svc
from app.services.scm.demand_class import class_of
from tests._pg_fixture import pg_session

MARKER = "ZZTOID"
SORENTO = "00000000-0000-0000-0000-000000000001"

SO_NUMBER = "SO900001"
ITEM_A = "ZZTOID-ITEM-A"
ITEM_B = "ZZTOID-ITEM-B"
GHOST = "ZZTOID-NOT-IN-CATALOGUE"
LOCATION = "ZZTOID-WH"
PROJECT = "ZZTOID Project Alpha"


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
    products = {}
    for code in (ITEM_A, ITEM_B):
        p = Product(id=_u(), product_code=code, product_name=f"{MARKER} {code}",
                    category_id=cat.id, base_uom_id=uom.id, list_price=0,
                    is_active=True, is_discontinued=False)
        db.add(p)
        products[code] = p
    wh = Warehouse(id=_u(), warehouse_code=LOCATION, warehouse_name=f"{MARKER} wh",
                   is_active=True, counts_as_available=True)
    db.add(wh)
    db.flush()
    return {"products": products, "warehouse": wh}


class _Row:
    """One sheet row. Built here rather than parsed, because the reader has its own suite and
    the subject of this one is the WRITE."""

    def __init__(self, *, so_number=SO_NUMBER, item_code=ITEM_A, qty=10.0,
                 so_date=date(2026, 7, 1), delivery_date=date(2026, 9, 1),
                 project=PROJECT, location=LOCATION, po_numbers=(), not_ordered=False):
        self.so_number = so_number
        self.item_code = item_code
        self.qty = qty
        self.so_date = so_date
        self.delivery_date = delivery_date
        self.project = project
        self.location = location
        self.supplier = ""
        self.po_numbers = po_numbers
        self.not_ordered = not_ordered
        self.sheet = "Sheet1"
        self.source_row = 2


class _Parsed:
    def __init__(self, rows):
        self.rows = rows
        self.ok = True
        self.problems = []
        self.sheets_read = ["Sheet1"]
        self.sheets_skipped = []
        self.with_location = sum(1 for r in rows if r.location)
        self.po_claims = sum(len(r.po_numbers) for r in rows)


def _create(db, rows) -> dict:
    return svc._create_orders(db, _Parsed(rows), svc._now())


def _order(db) -> SalesOrder:
    return db.query(SalesOrder).filter(SalesOrder.so_number == SO_NUMBER).one()


def _lines(db, order) -> list[SalesOrderLine]:
    return db.query(SalesOrderLine).filter(
        SalesOrderLine.sales_order_id == str(order.id)
    ).all()


# --------------------------------------------------------------------------- #
# it creates a proper order
# --------------------------------------------------------------------------- #

def test_a_sheet_row_becomes_a_sales_order_with_a_line(db, world):
    out = _create(db, [_Row()])

    assert out["orders_created"] == 1
    assert out["lines_created"] == 1
    order = _order(db)
    assert order.source_system == svc.SOURCE_SYSTEM, "provenance is what the whole rule reads"
    assert order.order_date == date(2026, 7, 1)
    # AC-E01: this is one of the two demand-class stamp points, and the stamp goes through
    # the shared mapper rather than a second literal, so a change to what counts as project
    # work cannot reach the outstanding import and miss this sheet. Pinned to the literal
    # the mapper is expected to produce: `class_of("project")` on both sides of the equals
    # would agree with itself no matter what the mapper did.
    assert order.order_type == "project"
    assert order.demand_class == "project"
    assert class_of(order.order_type) == "project"

    line = _lines(db, order)[0]
    assert float(line.qty_ordered) == 10.0
    assert line.required_date == date(2026, 9, 1)
    assert str(line.warehouse_id) == str(world["warehouse"].id)


def test_two_rows_on_one_order_number_make_one_order_with_two_lines(db, world):
    """An order is a header with lines, not a row. Two orders here would double the demand."""
    out = _create(db, [_Row(item_code=ITEM_A), _Row(item_code=ITEM_B)])

    assert out["orders_created"] == 1
    assert out["lines_created"] == 2
    assert len(_lines(db, _order(db))) == 2


def test_the_created_order_is_demand(db, world):
    """Open lines with a required date, which is all the netting and the timeline read."""
    _create(db, [_Row()])

    line = _lines(db, _order(db))[0]
    assert line.line_status == "open"
    assert float(line.qty_delivered) == 0
    assert line.required_date is not None


def test_a_project_links_an_existing_customer(db, world):
    customer = Customer(id=_u(), customer_code=f"{MARKER}-{uuid.uuid4().hex[:6]}",
                        customer_name=PROJECT)
    db.add(customer)
    db.flush()

    _create(db, [_Row()])

    assert str(_order(db).customer_id) == str(customer.id)


def test_an_unknown_project_is_kept_as_text_and_no_customer_is_invented(db, world):
    """`customers` needs a code and is unique on (code, name), so inventing one either
    collides with a real account or duplicates it. The name is preserved instead."""
    before = db.query(Customer).count()

    _create(db, [_Row(project="ZZTOID Nobody Has Heard Of")])

    assert db.query(Customer).count() == before, "the upload invented a customer"
    order = _order(db)
    assert order.customer_id is None
    assert "ZZTOID Nobody Has Heard Of" in (order.internal_note or "")


# --------------------------------------------------------------------------- #
# what it refuses to invent
# --------------------------------------------------------------------------- #

def test_an_item_we_do_not_hold_is_named_and_skipped(db, world):
    """`product_id` is NOT NULL, so the only alternative to skipping is inventing a product."""
    before = db.query(Product).count()

    out = _create(db, [_Row(item_code=ITEM_A), _Row(item_code=GHOST)])

    assert db.query(Product).count() == before, "the upload invented a product"
    assert GHOST in out["unmatched_item_codes"]
    assert out["lines_created"] == 1, "the resolvable sibling still became a line"


def test_an_order_whose_every_item_is_unknown_is_not_created_at_all(db, world):
    """A header with no line is a phantom: it shows in the list and no plan can read it."""
    out = _create(db, [_Row(item_code=GHOST)])

    assert out["orders_created"] == 0
    assert db.query(SalesOrder).filter(SalesOrder.so_number == SO_NUMBER).count() == 0


# --------------------------------------------------------------------------- #
# the ownership rule
# --------------------------------------------------------------------------- #

def test_it_refreshes_the_orders_it_created_rather_than_duplicating_them(db, world):
    """Re-uploading the sheet is the normal case - it is somebody's working record."""
    _create(db, [_Row(qty=10.0)])
    out = _create(db, [_Row(qty=25.0)])

    assert out["orders_created"] == 0
    assert out["lines_created"] == 0
    assert out["lines_refreshed"] == 1
    lines = _lines(db, _order(db))
    assert len(lines) == 1, "a second line would double the demand"
    assert float(lines[0].qty_ordered) == 25.0, "the sheet is the truth for its own line"


def test_it_does_not_touch_an_order_another_source_owns(db, world):
    """THE rule. CS's figures are CS's, whatever the spreadsheet says this week."""
    theirs = SalesOrder(id=_u(), so_number=SO_NUMBER, status="open",
                        order_type="dealer", source_system="scm_upload",
                        order_date=date(2026, 1, 1))
    db.add(theirs)
    db.flush()
    db.add(SalesOrderLine(
        id=_u(), sales_order_id=str(theirs.id),
        product_id=str(world["products"][ITEM_A].id),
        qty_ordered=999, qty_delivered=0, line_status="open",
        required_date=date(2026, 12, 31),
    ))
    db.flush()

    out = _create(db, [_Row(qty=1.0, delivery_date=date(2026, 9, 1))])

    assert out["orders_created"] == 0
    assert out["orders_owned_elsewhere"] == 1
    order = _order(db)
    assert order.source_system == "scm_upload", "ownership was taken over"
    assert order.order_type == "dealer"
    assert order.order_date == date(2026, 1, 1)
    line = _lines(db, order)[0]
    assert float(line.qty_ordered) == 999, "the sheet overwrote a quantity it does not own"
    assert line.required_date == date(2026, 12, 31)
