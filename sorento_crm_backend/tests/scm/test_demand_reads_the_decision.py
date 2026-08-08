"""Demand is what CS decided to cover, and the view and the engine must say the same thing.

`scm.committed_v` feeds the dashboard; `CoverageService` feeds the plan. They are two
implementations of one rule - SQL in a view, Python over the ORM - and when they drift the
symptom is a dashboard that contradicts a plan run for reasons nobody can see from either
screen. So every case here is asserted through BOTH.

The rule: `GREATEST(COALESCE(qty_required, qty_ordered) - qty_delivered, 0)`, skipping lines
CS has marked covered.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import text

from app.models.inventory import Warehouse
from app.models.order import SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.scm.coverage_service import CoverageService
from app.services.scm.demand import COMMITTED_V_SQL
from app.services.sla_service import MALAYSIA_TZ, to_naive_datetime
from tests._pg_fixture import pg_session, unique_code

MARKER = "ZZTDMD"


def _u() -> str:
    return str(uuid.uuid4())


def _today() -> date:
    return to_naive_datetime(datetime.now(MALAYSIA_TZ)).date()


#: The view is installed by a migration body, and no fixture runs one, so this suite builds it
#: itself - under a private name. Installing it as `scm.committed_v` would REPLACE the real
#: view for the duration of the transaction, and every other test running against the same
#: database would be reading a view this one owns. Same schema-pollution family as the dead
#: `zzt_blank` schema: the damage lands in unrelated files and looks like flakiness.
_SCHEMA = f"zzt_demand_{uuid.uuid4().hex[:8]}"
VIEW_SQL = COMMITTED_V_SQL.replace("scm.committed_v", f"{_SCHEMA}.committed_v")


@pytest.fixture()
def db():
    with pg_session() as s:
        s.execute(text(f'CREATE SCHEMA "{_SCHEMA}"'))
        s.execute(text(VIEW_SQL))
        yield s


@pytest.fixture()
def world(db):
    cat = ProductCategory(id=_u(), category_code=unique_code(MARKER),
                          category_name=f"{MARKER} cat")
    uom = UnitOfMeasure(id=_u(), uom_code=unique_code("U")[:20], uom_name=f"{MARKER} u")
    db.add_all([cat, uom])
    db.flush()
    product = Product(id=_u(), product_code=unique_code("P"), product_name=f"{MARKER} p",
                      category_id=cat.id, base_uom_id=uom.id, list_price=0,
                      is_active=True, is_discontinued=False)
    wh = Warehouse(id=_u(), warehouse_code=unique_code("W")[:20],
                   warehouse_name=f"{MARKER} wh", is_active=True, counts_as_available=True)
    db.add_all([product, wh])
    db.flush()
    return {"product": product, "warehouse": wh}


def _line(db, world, **over) -> SalesOrderLine:
    so = SalesOrder(id=_u(), so_number=unique_code("SO"), status="open",
                    demand_class="project")
    db.add(so)
    db.flush()
    fields = dict(
        qty_ordered=100, qty_delivered=0, qty_required=None,
        purchasing_status="not_reviewed", line_status="open",
        required_date=_today() + timedelta(days=30),
    )
    fields.update(over)
    line = SalesOrderLine(id=_u(), sales_order_id=so.id, product_id=world["product"].id,
                          warehouse_id=world["warehouse"].id, **fields)
    db.add(line)
    db.flush()
    return line


def _committed(db, world) -> float:
    row = db.execute(
        text(f"SELECT COALESCE(SUM(committed), 0) FROM {_SCHEMA}.committed_v"
             " WHERE product_id = :p"),
        {"p": str(world["product"].id)},
    ).scalar()
    return float(row or 0)


def _planned(db, world) -> float:
    """The demand the netting engine sees, as a positive quantity."""
    svc = CoverageService(db)
    events, _undated, _unplaceable = svc._demand_events(
        str(world["product"].id), [str(world["warehouse"].id)]
    )
    return round(-sum(e.qty for e in events), 4)


def _both(db, world) -> tuple[float, float]:
    return _committed(db, world), _planned(db, world)


# --------------------------------------------------------------------------- #

def test_an_unreviewed_line_counts_as_what_is_still_owed(db, world):
    """NULL `qty_required` is "nobody has looked", not "nothing needed"."""
    _line(db, world, qty_ordered=100, qty_delivered=40)
    assert _both(db, world) == (60.0, 60.0)


def test_the_quantity_CS_stated_wins_over_the_customer_quantity(db, world):
    """CS calls off 30 of a 100 line. The plan buys for 30."""
    _line(db, world, qty_ordered=100, qty_required=30)
    assert _both(db, world) == (30.0, 30.0)


def test_delivery_still_nets_against_the_quantity_CS_stated(db, world):
    """`qty_required` replaces what the customer asked for, not what has shipped."""
    _line(db, world, qty_ordered=100, qty_required=30, qty_delivered=10)
    assert _both(db, world) == (20.0, 20.0)


def test_a_line_CS_has_ruled_out_is_not_demand(db, world):
    """`covered` means CS says do not buy it. It stays owed to the customer either way."""
    _line(db, world, qty_ordered=100, purchasing_status="covered")
    assert _both(db, world) == (0.0, 0.0)


def test_a_line_waiting_to_be_purchased_is_demand(db, world):
    _line(db, world, qty_ordered=100, qty_required=100,
          purchasing_status="needs_purchase")
    assert _both(db, world) == (100.0, 100.0)


def test_a_line_already_on_a_purchase_order_is_still_demand(db, world):
    """The purchase order is SUPPLY and nets on its own. Dropping the demand as well would
    net it twice and hide the day the two do not line up."""
    _line(db, world, qty_ordered=100, qty_required=100, purchasing_status="ordered")
    assert _both(db, world) == (100.0, 100.0)


def test_a_quantity_CS_lowered_below_what_already_shipped_is_zero_not_negative(db, world):
    """A correction downward after part shipped must not become negative demand, which would
    read as supply and suppress a real purchase elsewhere in the same pool."""
    _line(db, world, qty_ordered=100, qty_required=10, qty_delivered=40)
    assert _both(db, world) == (0.0, 0.0)
