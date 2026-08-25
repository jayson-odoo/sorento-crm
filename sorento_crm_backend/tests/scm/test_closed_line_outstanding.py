"""A CLOSED line has nothing outstanding, whatever its two quantities say.

Found on SO397450. The sales-order book was re-uploaded and 306 of its lines were closed by
absence ("no longer on the uploaded book"). The lines grid then read, per line:

    CB6633   ordered 1,500   delivered 0   OUTSTANDING 1,500   status Completed

and the footer summed 39,008 outstanding on an order that is almost entirely done. Both
figures came from one expression - `max(ordered - delivered, 0)` - applied without asking
whether the line was still open.

TWO RULES, and they are not the same rule:

  * **outstanding is 0 on a closed line, by definition.** Closed means nobody is waiting for
    it. This is what `is_open_demand()` (and therefore `scm.committed_v`, the netting engine
    and the planning board) has always said, so it is the DETAIL page that disagreed with
    every other reader of the same rows;
  * **`qty_delivered` is NOT invented.** When the book merely stopped naming a line, what
    actually shipped is unknown. Writing `delivered = ordered` to make the subtraction come
    out would be inventing a delivery, so the line keeps the delivered figure it has and
    `outstanding_qty` is stated in its own right.

The same rule and the same field on the purchase book, where "delivered" is `qty_received`.

Postgres only, every FK seeded here, rolled back with the `scm_app` savepoint.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from app.models.inventory import Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from tests.scm.conftest import as_user, requires_pg, seed_user

pytestmark = requires_pg

MARKER = "ZZTCLO"


def _uid() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{_uid()[:8]}".upper()


class World:
    def __init__(self, app, db, product, warehouse, so=None, po=None):
        self.app = app
        self.db = db
        self.product = product
        self.warehouse = warehouse
        self.so = so
        self.po = po


def _base(scm_app):
    app, db, gcu, gcuak = scm_app
    as_user(app, gcu, gcuak, seed_user(db, "purchasing"))

    uom = UnitOfMeasure(id=_uid(), uom_code=_code("UOM")[:20], uom_name="Pieces")
    category = ProductCategory(
        id=_uid(), category_code=_code("CAT"), category_name=f"{MARKER} category"
    )
    db.add_all([uom, category])
    db.flush()
    product = Product(
        id=_uid(), product_code=_code("SKU"), product_name=f"{MARKER} board",
        category_id=category.id, base_uom_id=uom.id, list_price=Decimal("10.00"),
    )
    warehouse = Warehouse(
        id=_uid(), warehouse_code=_code("WH")[:20], warehouse_name=f"{MARKER} store",
        is_active=True,
    )
    db.add_all([product, warehouse])
    db.flush()
    return World(app, db, product, warehouse)


def _sales_order(scm_app, *, lines):
    """`lines` are `(qty_ordered, qty_delivered, line_status)` triples."""
    world = _base(scm_app)
    db = world.db
    customer = Customer(
        id=_uid(), customer_code=_code("CUS"), customer_name=f"{MARKER} Kitchens", is_active=True
    )
    db.add(customer)
    db.flush()
    so = SalesOrder(
        id=_uid(), so_number=_code("SO"), customer_id=customer.id, status="open",
        priority="normal", order_date=date(2026, 2, 1), source_system="scm_upload",
    )
    db.add(so)
    db.flush()
    for ordered, delivered, status in lines:
        db.add(SalesOrderLine(
            id=_uid(), sales_order_id=so.id, product_id=world.product.id,
            warehouse_id=world.warehouse.id,
            qty_ordered=Decimal(str(ordered)), qty_delivered=Decimal(str(delivered)),
            line_status=status,
        ))
    db.flush()
    world.so = so
    return world


def _purchase_order(scm_app, *, lines):
    """`lines` are `(qty_ordered, qty_received, line_status)` triples."""
    world = _base(scm_app)
    db = world.db
    supplier = Supplier(
        id=_uid(), supplier_code=_code("SUP"), supplier_name=f"{MARKER} Works", is_active=True
    )
    db.add(supplier)
    db.flush()
    po = PurchaseOrder(
        id=_uid(), po_number=_code("PO"), supplier_id=supplier.id, status="ordered",
        issue_date=date(2026, 2, 1), source_system="scm_upload",
    )
    db.add(po)
    db.flush()
    for ordered, received, status in lines:
        db.add(PurchaseOrderLine(
            id=_uid(), purchase_order_id=po.id, product_id=world.product.id,
            warehouse_id=world.warehouse.id,
            qty_ordered=Decimal(str(ordered)), qty_received=Decimal(str(received)),
            line_status=status,
        ))
    db.flush()
    world.po = po
    return world


def _so_detail(world) -> dict:
    with TestClient(world.app) as c:
        res = c.get(f"/api/v1/scm/sales-orders/{world.so.id}")
        assert res.status_code == 200, res.text
        return res.json()


def _so_listed(world) -> dict:
    with TestClient(world.app) as c:
        res = c.get("/api/v1/scm/sales-orders", params={"query": world.so.so_number})
        assert res.status_code == 200, res.text
        body = res.json()
    return next(r for r in body["data"] if r["so_number"] == world.so.so_number)


def _po_detail(world) -> dict:
    with TestClient(world.app) as c:
        res = c.get(f"/api/v1/scm/purchase-orders/{world.po.id}")
        assert res.status_code == 200, res.text
        return res.json()


# --- the sales book ---------------------------------------------------------

def test_a_closed_line_is_outstanding_nothing_however_little_shipped(scm_app):
    """The reported row: 1,500 ordered, 0 delivered, Completed. It owes nobody anything."""
    world = _sales_order(scm_app, lines=[(1500, 0, "closed")])

    line = _so_detail(world)["lines"][0]

    # It survives `response_model`, which silently drops anything undeclared.
    assert "outstanding_qty" in line, line.keys()
    assert line["outstanding_qty"] == 0


def test_a_closed_line_keeps_the_delivered_figure_it_actually_has(scm_app):
    """`qty_delivered` is NOT back-filled to make the subtraction come out. What shipped
    before the book stopped naming the line is unknown, and 1,500 would be an invention."""
    world = _sales_order(scm_app, lines=[(1500, 0, "closed")])

    line = _so_detail(world)["lines"][0]

    assert line["qty_ordered"] == 1500
    assert line["qty_delivered"] == 0


def test_an_open_line_is_still_ordered_less_delivered(scm_app):
    world = _sales_order(scm_app, lines=[(100, 40, "open")])

    assert _so_detail(world)["lines"][0]["outstanding_qty"] == 60


def test_an_over_delivered_open_line_is_outstanding_nothing_not_a_negative(scm_app):
    world = _sales_order(scm_app, lines=[(100, 140, "open")])

    assert _so_detail(world)["lines"][0]["outstanding_qty"] == 0


def test_the_header_counts_only_what_is_still_open(scm_app):
    """The Totals card's "Outstanding qty". A mostly-closed order summing 39,008 is the
    defect, in one figure."""
    world = _sales_order(scm_app, lines=[(1500, 0, "closed"), (100, 40, "open")])

    body = _so_detail(world)

    assert body["committed_qty"] == 60
    # `total_qty` is what the ORDER SAYS and still counts every line: a 2020 order reading 0
    # because its lines are closed would be the label lying about the row.
    assert body["total_qty"] == 1600


def test_the_list_row_agrees_with_the_detail(scm_app):
    """The Committed column comes off the same serializer, so the two screens cannot
    disagree about the same order - and both now agree with `scm.committed_v`, which has
    excluded closed lines all along."""
    world = _sales_order(scm_app, lines=[(1500, 0, "closed"), (100, 40, "open")])

    row = _so_listed(world)

    assert row["committed_qty"] == 60
    assert row["total_qty"] == 1600


# --- the purchase book ------------------------------------------------------

def test_a_closed_purchase_line_is_outstanding_nothing(scm_app):
    """Same rule, same field name, "delivered" being `qty_received` over here."""
    world = _purchase_order(scm_app, lines=[(200, 0, "closed")])

    line = _po_detail(world)["lines"][0]

    assert "outstanding_qty" in line, line.keys()
    assert line["outstanding_qty"] == 0
    assert line["qty_received"] == 0


def test_an_open_purchase_line_is_still_ordered_less_received(scm_app):
    world = _purchase_order(scm_app, lines=[(100, 30, "open")])

    assert _po_detail(world)["lines"][0]["outstanding_qty"] == 70


def test_the_purchase_header_states_what_is_still_to_arrive(scm_app):
    """Summed off the same per-line rule the grid prints, so the card and the footer of the
    table under it cannot disagree."""
    world = _purchase_order(scm_app, lines=[(200, 0, "closed"), (100, 30, "open")])

    body = _po_detail(world)

    assert body["outstanding_qty"] == 70
    assert body["total_qty"] == 300
