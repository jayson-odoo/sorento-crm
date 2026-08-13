"""Demand the plan cannot see is counted and reported, not silently omitted.

> "it has a few thousands of committed quantity for these 2 SO ... but why when i search
>  MWC7624-RL-S10 in the reorder planning, it does not exist"

Because planning nets per product AND location, and the line names no warehouse, so there
is nothing to net it against. On the customer's book that is 8,011 of 8,136 open lines. A
plan that leaves that out without saying so reads as "nothing to buy".

Nothing here decides where such demand SHOULD land - that is a business rule about which
location serves an unlocated order. This only proves it is counted and named.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models.inventory import Warehouse
from app.models.order import SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.scm import unplanned_demand_service as svc
from tests._pg_fixture import blank_session, unique_code


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _u() -> str:
    return str(uuid.uuid4())


def _product(db, code: str) -> Product:
    cat = ProductCategory(id=_u(), category_code=f"C-{code}"[:50], category_name=code)
    uom = UnitOfMeasure(id=_u(), uom_code=f"U-{code}"[:50], uom_name="Each")
    db.add_all([cat, uom])
    db.flush()
    p = Product(id=_u(), product_code=code, product_name=code, category_id=cat.id,
                base_uom_id=uom.id, list_price=0, is_active=True)
    db.add(p)
    db.flush()
    return p


def _warehouse(db) -> Warehouse:
    w = Warehouse(id=_u(), warehouse_code=unique_code("WH")[:50], warehouse_name="Main")
    db.add(w)
    db.flush()
    return w


def _line(db, product, qty, *, warehouse=None, status="open", line_status="open",
          purchasing_status=None, delivered=0):
    so = SalesOrder(id=_u(), so_number=unique_code("SO"), status=status,
                    order_date=date(2026, 1, 1))
    db.add(so)
    db.flush()
    line = SalesOrderLine(
        id=_u(), sales_order_id=so.id, product_id=product.id,
        warehouse_id=warehouse.id if warehouse else None,
        qty_ordered=qty, qty_delivered=delivered, line_status=line_status,
    )
    if purchasing_status is not None:
        line.purchasing_status = purchasing_status
    db.add(line)
    db.flush()
    return line


def test_demand_with_no_location_is_counted_and_the_products_are_named(db):
    p = _product(db, unique_code("MWC"))
    _line(db, p, 419)

    result = svc.unlocated_demand(db)

    assert result["lines"] == 1
    assert result["products"] == 1
    assert result["quantity"] == 419.0
    assert result["sample"][0]["product_code"] == p.product_code
    assert result["sample"][0]["quantity"] == 419.0


def test_demand_that_names_a_warehouse_is_plannable_and_is_not_counted(db):
    p = _product(db, unique_code("MWC"))
    _line(db, p, 50, warehouse=_warehouse(db))

    result = svc.unlocated_demand(db)

    assert result["lines"] == 0
    assert result["quantity"] == 0.0


def test_only_the_demand_the_plan_would_have_used_counts(db):
    # The same filter committed_v applies. A closed order, a closed line, a line already
    # covered by a purchase, and a line fully delivered are all demand the plan would not
    # have netted even WITH a location, so counting them would overstate what is missing.
    p = _product(db, unique_code("MWC"))
    _line(db, p, 10, status="closed")
    _line(db, p, 10, line_status="closed")
    _line(db, p, 10, purchasing_status="covered")
    _line(db, p, 10, delivered=10)
    _line(db, p, 7)                       # the only one that counts

    result = svc.unlocated_demand(db)

    assert result["lines"] == 1
    assert result["quantity"] == 7.0


def test_the_sample_leads_with_the_biggest_gap(db):
    small = _product(db, unique_code("SMALL"))
    big = _product(db, unique_code("BIG"))
    _line(db, small, 5)
    _line(db, big, 900)

    sample = svc.unlocated_demand(db)["sample"]

    assert sample[0]["product_code"] == big.product_code
    assert sample[0]["quantity"] == 900.0


def test_a_book_with_every_line_located_reports_nothing_rather_than_failing(db):
    p = _product(db, unique_code("MWC"))
    _line(db, p, 12, warehouse=_warehouse(db))

    result = svc.unlocated_demand(db)

    assert result == {"lines": 0, "products": 0, "quantity": 0.0, "sample": []}
