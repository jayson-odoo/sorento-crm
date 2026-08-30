"""What the sales-order API says about MONEY, and about the order's classification.

Two gaps this file closes, both found on the client's own screen.

**Money never reached the browser.** `sales_order_lines` has carried `unit_price` since the
demand popover needed it, and the AutoCount book also states a discount and a line total -
but the detail page's line schema declared none of the three, so `response_model` dropped
them however carefully the serializer built the dict (the standing `response_model` trap).
The header had no money at all, so an order worth RM 46,000 read as a list of quantities.

**The order type could not be round-tripped.** The view rendered `demand_class` (project /
retail / unclassified) while the edit form seeded itself from `order_type`, which is NULL on
96% of this book - and the save then hard-refused an empty order type, so most orders could
not be header-edited at all. The write side now accepts `demand_class` under its own name.
`order_type` stays accepted, unchanged, for anything else that still sends it.

Postgres only, every FK seeded here (never a borrowed `LIMIT 1` row), rolled back with the
`scm_app` savepoint.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.models.inventory import Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from tests.scm.conftest import as_user, requires_pg, seed_user

pytestmark = requires_pg

MARKER = "ZZTSOM"


def _uid() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{_uid()[:8]}".upper()


class World:
    """One customer, one product, one warehouse and one order, all this test's own."""

    def __init__(self, app, db, customer, product, warehouse, so):
        self.app = app
        self.db = db
        self.customer = customer
        self.product = product
        self.warehouse = warehouse
        self.so = so


def _seed(scm_app, *, lines, demand_class=None, order_type=None, order_date=date(2026, 7, 16)):
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
        priority="normal", order_date=order_date, demand_class=demand_class,
        order_type=order_type, source_system="scm_upload",
    )
    db.add(so)
    db.flush()
    for spec in lines:
        db.add(SalesOrderLine(
            id=_uid(), sales_order_id=so.id, product_id=product.id,
            warehouse_id=warehouse.id,
            qty_ordered=Decimal(str(spec.get("qty_ordered", 10))),
            qty_delivered=Decimal(str(spec.get("qty_delivered", 0))),
            unit_price=spec.get("unit_price"),
            discount=spec.get("discount"),
            line_total=spec.get("line_total"),
            uom=spec.get("uom"),
            line_status="open",
        ))
    db.flush()
    return World(app, db, customer, product, warehouse, so)


def _detail(world) -> dict:
    with TestClient(world.app) as c:
        res = c.get(f"/api/v1/scm/sales-orders/{world.so.id}")
        assert res.status_code == 200, res.text
        return res.json()


def _put(world, body) -> dict:
    with TestClient(world.app) as c:
        res = c.put(f"/api/v1/scm/sales-orders/{world.so.id}", json=body)
        assert res.status_code == 200, res.text
        return res.json()


# --- the line's money reaches the browser -----------------------------------

def test_a_line_carries_its_price_discount_and_total(scm_app):
    """`response_model` silently drops an undeclared field, so this is asserted through
    the ROUTE rather than off the serializer."""
    world = _seed(scm_app, lines=[
        {"qty_ordered": 10, "unit_price": Decimal("100.00"),
         "discount": Decimal("15.00"), "line_total": Decimal("985.00")},
    ])

    line = _detail(world)["lines"][0]

    assert Decimal(str(line["unit_price"])) == Decimal("100.00")
    assert Decimal(str(line["discount"])) == Decimal("15.00")
    assert Decimal(str(line["line_total"])) == Decimal("985.00")


def test_a_line_with_no_money_reads_null_rather_than_zero(scm_app):
    """A zero price reads as goods given away; the absence has to survive the wire."""
    world = _seed(scm_app, lines=[{"qty_ordered": 10}])

    line = _detail(world)["lines"][0]

    assert line["unit_price"] is None
    assert line["discount"] is None
    assert line["line_total"] is None


# --- the header's total -----------------------------------------------------

def test_total_amount_sums_the_stated_line_totals(scm_app):
    world = _seed(scm_app, lines=[
        {"qty_ordered": 10, "line_total": Decimal("985.00")},
        {"qty_ordered": 4, "line_total": Decimal("15.50")},
    ])

    assert Decimal(str(_detail(world)["total_amount"])) == Decimal("1000.50")


def test_total_amount_falls_back_to_price_times_qty_less_discount(scm_app):
    """A book that states a price and a discount but no line total is still worth
    something; computing it here beats printing a blank beside 320 units."""
    world = _seed(scm_app, lines=[
        {"qty_ordered": 10, "unit_price": Decimal("100.00"), "discount": Decimal("15.00")},
    ])

    assert Decimal(str(_detail(world)["total_amount"])) == Decimal("985.00")


def test_total_amount_is_absent_when_no_line_carries_money(scm_app):
    """None, not 0: an order nobody priced is not an order worth nothing."""
    world = _seed(scm_app, lines=[{"qty_ordered": 10}])

    assert _detail(world)["total_amount"] is None


# --- what the edit screen may now write -------------------------------------

def test_the_order_date_can_be_corrected(scm_app):
    world = _seed(scm_app, lines=[{"qty_ordered": 10}], order_date=date(2026, 7, 16))

    assert _put(world, {"order_date": "2026-05-04"})["order_date"] == "2026-05-04"


def test_a_line_edit_writes_the_price_and_the_discount(scm_app):
    world = _seed(scm_app, lines=[
        {"qty_ordered": 10, "unit_price": Decimal("100.00"), "discount": Decimal("15.00")},
    ])
    sku = world.product.product_code
    line_id = _detail(world)["lines"][0]["id"]

    body = _put(world, {"lines": [{
        "id": line_id, "sku": sku, "qty_ordered": 10,
        "unit_price": 88.5, "discount": 0,
    }]})

    line = body["lines"][0]
    assert Decimal(str(line["unit_price"])) == Decimal("88.50")
    assert Decimal(str(line["discount"])) == Decimal("0")


def test_a_line_edit_that_omits_the_money_leaves_it_alone(scm_app):
    """`model_fields_set`, the same rule `uom` / `warehouse_code` already follow: a
    qty-only edit must not wipe a price the book imported."""
    world = _seed(scm_app, lines=[
        {"qty_ordered": 10, "unit_price": Decimal("100.00"), "discount": Decimal("15.00")},
    ])
    sku = world.product.product_code
    line_id = _detail(world)["lines"][0]["id"]

    body = _put(world, {"lines": [{"id": line_id, "sku": sku, "qty_ordered": 12}]})

    line = body["lines"][0]
    assert line["qty_ordered"] == 12
    assert Decimal(str(line["unit_price"])) == Decimal("100.00")
    assert Decimal(str(line["discount"])) == Decimal("15.00")


# --- the order type round trip ----------------------------------------------

def test_the_classification_can_be_set_under_its_own_name(scm_app):
    """The view renders `demand_class`; the edit now writes the same column, so what was
    read back is what was chosen."""
    world = _seed(scm_app, lines=[{"qty_ordered": 10}], demand_class=None)

    assert _put(world, {"demand_class": "project"})["demand_class"] == "project"


def test_an_empty_classification_leaves_the_stored_one_alone(scm_app):
    """96% of this book is unclassified, and a header edit must not be refused because of
    it - nor must saving blank quietly un-rank an order the importer classified."""
    world = _seed(scm_app, lines=[{"qty_ordered": 10}], demand_class="retail")

    body = _put(world, {"demand_class": None, "priority": "high"})

    assert body["demand_class"] == "retail"
    assert body["priority"] == "high"


def test_a_word_the_policy_cannot_weigh_is_refused(scm_app):
    """A third class does not rank lower, it drops out of the ranking entirely - so the
    closed vocabulary is enforced where the value is written."""
    world = _seed(scm_app, lines=[{"qty_ordered": 10}], demand_class="retail")

    with TestClient(world.app) as c:
        res = c.put(
            f"/api/v1/scm/sales-orders/{world.so.id}", json={"demand_class": "dealer"}
        )

    assert res.status_code == 400, res.text
    assert "dealer" in res.text


def test_order_type_still_derives_the_class_for_anything_that_sends_it(scm_app):
    """Unchanged behaviour, asserted so the compatibility claim is not just a comment."""
    world = _seed(scm_app, lines=[{"qty_ordered": 10}], demand_class=None)

    body = _put(world, {"order_type": "project"})

    assert body["order_type"] == "project"
    assert body["demand_class"] == "project"
