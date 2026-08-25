"""What the sales-order list says a delivery date IS.

The list used to print the header's `requested_delivery_date`, which is a different figure
from the one the lines carry and is blank on most of this book. What a person scanning the
list is asking is "when is this order due", and the answer lives on the LINES
(`sales_order_lines.required_date`) - one order routinely ships across two dates.

So the order carries the SPAN of its line dates: the earliest and the latest any line names.
Both `None` when no line names one, because an order nobody dated is not due today. The
header's own figure is untouched and stays on the detail page.

Asserted through the ROUTE, not off the serializer: `response_model` silently drops an
undeclared field however carefully the dict was built.

Postgres only, every FK seeded here (never a borrowed `LIMIT 1` row), rolled back with the
`scm_app` savepoint.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from app.models.inventory import Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from tests.scm.conftest import as_user, requires_pg, seed_user

pytestmark = requires_pg

MARKER = "ZZTSODD"


def _uid() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{_uid()[:8]}".upper()


class World:
    def __init__(self, app, db, so):
        self.app = app
        self.db = db
        self.so = so


def _seed(scm_app, *, lines, requested_delivery_date=None):
    """One customer, product, warehouse and order, all this test's own.

    `lines` is a list of dicts: `required_date` (a `date` or None) and optionally
    `line_total`, so the money assertion can share the same seeding.
    """
    app, db, gcu, gcuak = scm_app
    as_user(app, gcu, gcuak, seed_user(db, "purchasing"))

    uom = UnitOfMeasure(id=_uid(), uom_code=_code("UOM")[:20], uom_name="Pieces")
    category = ProductCategory(
        id=_uid(), category_code=_code("CAT"), category_name=f"{MARKER} category"
    )
    db.add_all([uom, category])
    db.flush()
    product = Product(
        id=_uid(), product_code=_code("SKU"), product_name=f"{MARKER} basin",
        category_id=category.id, base_uom_id=uom.id, list_price=Decimal("120.00"),
    )
    customer = Customer(
        id=_uid(), customer_code=_code("CUS"), customer_name=f"{MARKER} Kitchens Sdn Bhd",
        is_active=True,
    )
    warehouse = Warehouse(
        id=_uid(), warehouse_code=_code("WH")[:20], warehouse_name=f"{MARKER} store",
        is_active=True,
    )
    db.add_all([product, customer, warehouse])
    db.flush()

    so = SalesOrder(
        id=_uid(), so_number=_code("SO"), customer_id=customer.id, status="open",
        priority="normal", order_date=date(2026, 1, 2),
        requested_delivery_date=requested_delivery_date,
        source_system="scm_upload",
    )
    db.add(so)
    db.flush()
    for spec in lines:
        db.add(SalesOrderLine(
            id=_uid(), sales_order_id=so.id, product_id=product.id,
            warehouse_id=warehouse.id,
            qty_ordered=Decimal(str(spec.get("qty_ordered", 10))),
            qty_delivered=Decimal("0"),
            required_date=spec.get("required_date"),
            line_total=spec.get("line_total"),
            line_status="open",
        ))
    db.flush()
    return World(app, db, so)


def _detail(world) -> dict:
    with TestClient(world.app) as c:
        res = c.get(f"/api/v1/scm/sales-orders/{world.so.id}")
        assert res.status_code == 200, res.text
        return res.json()


def _listed(world) -> dict:
    """The order's row off the LIST endpoint, found by its own number."""
    with TestClient(world.app) as c:
        res = c.get("/api/v1/scm/sales-orders", params={"query": world.so.so_number})
        assert res.status_code == 200, res.text
        body = res.json()
    return next(r for r in body["data"] if r["so_number"] == world.so.so_number)


# --- the span of the line dates ---------------------------------------------

def test_the_span_runs_from_the_earliest_line_date_to_the_latest(scm_app):
    """Three lines, two distinct dates: the column has to say the order is due across
    that whole stretch, not on whichever line happens to sort first."""
    world = _seed(scm_app, lines=[
        {"required_date": date(2026, 3, 10)},
        {"required_date": date(2026, 1, 12)},
        {"required_date": date(2026, 1, 12)},
    ])

    row = _listed(world)

    # It survives `response_model`, which silently drops anything undeclared.
    assert "delivery_date_from" in row, row.keys()
    assert row["delivery_date_from"] == "2026-01-12"
    assert row["delivery_date_to"] == "2026-03-10"


def test_lines_that_agree_report_the_same_date_at_both_ends(scm_app):
    """The common case, and what lets the cell print one date rather than a range of
    one day."""
    world = _seed(scm_app, lines=[
        {"required_date": date(2026, 1, 12)},
        {"required_date": date(2026, 1, 12)},
    ])

    row = _listed(world)

    assert row["delivery_date_from"] == "2026-01-12"
    assert row["delivery_date_to"] == "2026-01-12"


def test_an_order_no_line_dates_reports_neither_end(scm_app):
    """None, not the order date and not today: an order nobody dated is not due now.

    The HEADER's own `requested_delivery_date` is set here and must not leak into the
    span - it is a different figure, and conflating the two is what this change undoes.
    """
    world = _seed(
        scm_app,
        lines=[{"required_date": None}, {"required_date": None}],
        requested_delivery_date=date(2026, 9, 1),
    )

    row = _listed(world)

    assert row["delivery_date_from"] is None
    assert row["delivery_date_to"] is None
    # Unchanged, and still the thing the detail page reads.
    assert row["requested_delivery_date"] == "2026-09-01"


def test_an_undated_line_never_pulls_the_span_earlier(scm_app):
    """A mix of dated and undated lines answers with what is known, not with a null."""
    world = _seed(scm_app, lines=[
        {"required_date": None},
        {"required_date": date(2026, 2, 4)},
    ])

    row = _listed(world)

    assert row["delivery_date_from"] == "2026-02-04"
    assert row["delivery_date_to"] == "2026-02-04"


def test_the_detail_read_carries_the_same_span(scm_app):
    """Off the same serializer, so the list and the order cannot disagree about when it
    is due."""
    world = _seed(scm_app, lines=[
        {"required_date": date(2026, 1, 12)},
        {"required_date": date(2026, 3, 10)},
    ])

    body = _detail(world)

    assert body["delivery_date_from"] == "2026-01-12"
    assert body["delivery_date_to"] == "2026-03-10"


# --- ordering by it ---------------------------------------------------------

def test_the_list_can_be_ordered_by_the_start_of_the_span(scm_app):
    """"What is due first" is the question the column is scanned with, so the header has
    to be able to answer it - which means the sort happens in SQL, over the same
    `min(required_date)` the cell prints."""
    world = _seed(scm_app, lines=[{"required_date": date(2026, 5, 20)}])
    app, db = world.app, world.db
    # A second order of this test's own, due earlier, sharing the marker so one query
    # returns both.
    first = SalesOrder(
        id=_uid(), so_number=_code("SO"), customer_id=world.so.customer_id,
        status="open", priority="normal", order_date=date(2026, 1, 2),
        source_system="scm_upload",
    )
    db.add(first)
    db.flush()
    line = db.query(SalesOrderLine).filter(
        SalesOrderLine.sales_order_id == world.so.id).first()
    db.add(SalesOrderLine(
        id=_uid(), sales_order_id=first.id, product_id=line.product_id,
        warehouse_id=line.warehouse_id, qty_ordered=Decimal("5"),
        qty_delivered=Decimal("0"), required_date=date(2026, 2, 1), line_status="open",
    ))
    db.flush()

    with TestClient(app) as c:
        res = c.get("/api/v1/scm/sales-orders", params={
            "query": MARKER, "sort": "delivery_date_from", "dir": "asc", "limit": 200,
        })

    assert res.status_code == 200, res.text
    numbers = [r["so_number"] for r in res.json()["data"]]
    assert numbers.index(first.so_number) < numbers.index(world.so.so_number)


# --- what the order is worth, on the LIST too -------------------------------

def test_the_list_row_carries_the_order_total(scm_app):
    """The column beside Committed. Asserted on the LIST specifically: the figure was
    only ever read off the detail page, and `response_model` is per-route."""
    world = _seed(scm_app, lines=[
        {"required_date": date(2026, 1, 12), "line_total": Decimal("985.00")},
        {"required_date": date(2026, 1, 12), "line_total": Decimal("15.50")},
    ])

    assert Decimal(str(_listed(world)["total_amount"])) == Decimal("1000.50")


def test_the_list_row_leaves_an_unpriced_order_blank(scm_app):
    """None, not 0: 15,000 of the absorbed rows carry no money at all, and an order
    nobody priced is not an order worth nothing."""
    world = _seed(scm_app, lines=[{"required_date": date(2026, 1, 12)}])

    assert _listed(world)["total_amount"] is None
