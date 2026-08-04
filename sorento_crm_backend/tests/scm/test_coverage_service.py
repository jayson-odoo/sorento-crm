"""CoverageService against real tables, seeding its own chain end to end.

Nothing here reads a pre-existing row. Every product, warehouse, customer, supplier, SO and
PO is created by the test with a marker prefix, because CI's database has no data and a
borrowed lookup is the failure mode that turned one missing row into sixteen failures.

The centrepiece is `test_pool_covers_a_bin_shortage_so_nothing_is_bought`: the SRTWT7408
shape, proven through the DB rather than only through the pure function.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import text

from app.models.inventory import Stock, Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.scm.coverage_service import CoverageService
from app.services.scm.coverage_timeline import (
    SOURCE_ORDER,
    SOURCE_OWN,
    SOURCE_POOL,
    SUPPLY_ON_ORDER,
)
from app.services.scm.coverage_timeline import buy_quantity, is_use_stock
from tests._pg_fixture import pg_session, unique_code


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


@pytest.fixture()
def chain(db):
    """product + pool warehouse + two bins pointing at it. The whole FK chain, seeded."""
    # Postgres enforces every NOT NULL the ORM defaults do not cover, so the fixture seeds
    # the real required columns rather than a loose approximation: category_code,
    # uom_code/uom_name, and products.base_uom_id + list_price.
    cat = ProductCategory(
        id=_u(), category_code=unique_code("CAT")[:40], category_name=unique_code("cat")
    )
    uom = UnitOfMeasure(
        id=_u(), uom_name=unique_code("uom"), uom_code=unique_code("U")[:20]
    )
    db.add_all([cat, uom])
    db.flush()

    product = Product(
        id=_u(),
        product_code=unique_code("SKU"),
        product_name="Wall hung WC",
        category_id=cat.id,
        base_uom_id=uom.id,
        list_price=0,
    )
    pool = Warehouse(id=_u(), warehouse_code=unique_code("POOL"), warehouse_name="pool", is_active=True)
    db.add_all([product, pool])
    db.flush()

    bin_a = Warehouse(
        id=_u(), warehouse_code=unique_code("BINA"), warehouse_name="bin a",
        is_active=True, pool_warehouse_id=pool.id,
    )
    bin_b = Warehouse(
        id=_u(), warehouse_code=unique_code("BINB"), warehouse_name="bin b",
        is_active=True, pool_warehouse_id=pool.id,
    )
    pool.pool_warehouse_id = pool.id  # a pool is its own pool
    db.add_all([bin_a, bin_b])
    db.flush()
    return {"product": product, "pool": pool, "bin_a": bin_a, "bin_b": bin_b}


def _stock(db, product, wh, qty):
    db.add(Stock(id=_u(), product_id=product.id, warehouse_id=wh.id, quantity_on_hand=qty,
                 quantity_reserved=0))
    db.flush()


def _so_line(db, product, wh, qty, when, *, demand_class="project", customer_name=None):
    cust = None
    if customer_name:
        cust = Customer(id=_u(), customer_code=unique_code("C"), customer_name=customer_name)
        db.add(cust)
        db.flush()
    so = SalesOrder(
        id=_u(), so_number=unique_code("SO"), status="open",
        customer_id=cust.id if cust else None, demand_class=demand_class,
    )
    db.add(so)
    db.flush()
    line = SalesOrderLine(
        id=_u(), sales_order_id=so.id, product_id=product.id, warehouse_id=wh.id,
        qty_ordered=qty, qty_delivered=0, line_status="open", required_date=when,
    )
    db.add(line)
    db.flush()
    return so


def _po_line(db, product, wh, qty, when, *, status="active"):
    sup = Supplier(id=_u(), supplier_code=unique_code("S"), supplier_name="KAILU")
    db.add(sup)
    db.flush()
    po = PurchaseOrder(id=_u(), po_number=unique_code("PO"), supplier_id=sup.id, status=status)
    db.add(po)
    db.flush()
    db.add(PurchaseOrderLine(
        id=_u(), purchase_order_id=po.id, product_id=product.id, warehouse_id=wh.id,
        qty_ordered=qty, qty_received=0, expected_date=when, line_status="open",
    ))
    db.flush()
    return po


# --------------------------------------------------------------------------- #
# the regression case, through the database
# --------------------------------------------------------------------------- #

def test_pool_covers_a_bin_shortage_so_nothing_is_bought(db, chain):
    """SRTWT7408: 67 demanded against bins, 4,397 sitting in the pool.

    Per-warehouse netting recommends buying 67 units of an item holding 4,397. That would be
    the first row of the first report anyone reads, so this is the case that matters most.
    """
    _stock(db, chain["product"], chain["pool"], 4397)
    _so_line(db, chain["product"], chain["bin_a"], 60, date(2026, 9, 30))
    _so_line(db, chain["product"], chain["bin_a"], 7, date(2026, 10, 30))

    svc = CoverageService(db)
    allocs = svc.resolve_line(chain["product"].id, warehouse_id=chain["bin_a"].id, qty=67)

    assert [a.source_type for a in allocs] == [SOURCE_POOL]
    assert buy_quantity(allocs) == 0
    assert is_use_stock(allocs) is True


def test_bin_stock_is_consumed_before_pool_stock(db, chain):
    _stock(db, chain["product"], chain["bin_a"], 20)
    _stock(db, chain["product"], chain["pool"], 500)

    allocs = CoverageService(db).resolve_line(
        chain["product"].id, warehouse_id=chain["bin_a"].id, qty=100
    )
    assert [(a.source_type, a.qty) for a in allocs] == [(SOURCE_OWN, 20), (SOURCE_POOL, 80)]


def test_another_bins_stock_is_offered_as_a_borrow_not_silently_taken(db, chain):
    _stock(db, chain["product"], chain["bin_b"], 90)

    allocs = CoverageService(db).resolve_line(
        chain["product"].id, warehouse_id=chain["bin_a"].id, qty=100
    )
    borrow = [a for a in allocs if a.needs_claim]
    assert len(borrow) == 1 and borrow[0].qty == 90
    assert buy_quantity(allocs) == 10


def test_a_location_in_a_different_pool_is_not_a_source(db, chain):
    """Cross-site stock is real but needs a physical movement, so it is never netted."""
    other_pool = Warehouse(id=_u(), warehouse_code=unique_code("OTHR"), is_active=True)
    db.add(other_pool)
    db.flush()
    other_pool.pool_warehouse_id = other_pool.id
    _stock(db, chain["product"], other_pool, 9999)
    db.flush()

    allocs = CoverageService(db).resolve_line(
        chain["product"].id, warehouse_id=chain["bin_a"].id, qty=50
    )
    assert [(a.source_type, a.qty) for a in allocs] == [(SOURCE_ORDER, 50)]


def test_a_location_marked_unavailable_contributes_nothing(db, chain):
    _stock(db, chain["product"], chain["bin_b"], 500)
    chain["bin_b"].counts_as_available = False
    db.flush()

    allocs = CoverageService(db).resolve_line(
        chain["product"].id, warehouse_id=chain["bin_a"].id, qty=50
    )
    assert [(a.source_type, a.qty) for a in allocs] == [(SOURCE_ORDER, 50)]


# --------------------------------------------------------------------------- #
# the timeline, through the database
# --------------------------------------------------------------------------- #

def test_timeline_orders_real_documents_by_date(db, chain):
    _stock(db, chain["product"], chain["pool"], 140)
    _so_line(db, chain["product"], chain["bin_a"], 135, date(2026, 7, 1),
             customer_name="TUJU RESIDENCE")
    _so_line(db, chain["product"], chain["bin_a"], 72, date(2026, 8, 3),
             customer_name="TUJU RESIDENCE")
    _po_line(db, chain["product"], chain["bin_a"], 200, date(2026, 8, 25))

    cov = CoverageService(db).coverage_for(chain["product"].id, pool_id=chain["pool"].id)

    assert [r.balance for r in cov.timeline.rows] == [140, 5, -67, 133]
    assert cov.timeline.shortfall is not None
    assert cov.timeline.shortfall.at == date(2026, 8, 3)
    assert cov.timeline.shortfall.qty == 67
    # Closing is positive, so a dateless net position would have reported nothing wrong.
    assert cov.timeline.closing_balance == 133


def test_a_draft_po_is_not_counted_as_supply(db, chain):
    """A draft PO is a recommendation nobody committed to. Counting it would suppress the
    very buy that created it."""
    _stock(db, chain["product"], chain["pool"], 0)
    _so_line(db, chain["product"], chain["bin_a"], 100, date(2026, 9, 1))
    _po_line(db, chain["product"], chain["bin_a"], 100, date(2026, 8, 1), status="draft")

    cov = CoverageService(db).coverage_for(chain["product"].id, pool_id=chain["pool"].id)
    assert cov.timeline.closing_balance == -100
    assert cov.timeline.shortfall is not None


def test_supply_stage_distinguishes_on_order_from_in_transit(db, chain):
    _po_line(db, chain["product"], chain["bin_a"], 400, date(2026, 8, 1))
    cov = CoverageService(db).coverage_for(chain["product"].id, pool_id=chain["pool"].id)
    stages = [r.event.supply_stage for r in cov.timeline.rows if r.event.supply_stage]
    assert stages == [SUPPLY_ON_ORDER]


def test_a_closed_po_line_is_not_supply_and_the_timeline_agrees_with_on_order_v(db, chain):
    """Two readers of "on order" must not disagree, and here the disagreement HIDES a
    shortfall.

    ``scm.on_order_v`` excludes a line whose ``line_status`` the outstanding-orders importer
    has closed; the demand half of this very service applies the same predicate to
    ``sales_order_lines``. The supply half does not, so a container the supplier is no longer
    holding for us still arrives on the timeline and covers demand that is in fact uncovered.
    A planner reading a shortfall of zero next to a dashboard reading a shortfall stops
    trusting both numbers, so the agreement of the two figures is the real invariant, which
    is why it is asserted directly rather than inferred from one of them.
    """
    sup = Supplier(id=_u(), supplier_code=unique_code("S"), supplier_name="KAILU")
    db.add(sup)
    db.flush()
    po = PurchaseOrder(id=_u(), po_number=unique_code("PO"), supplier_id=sup.id, status="active")
    db.add(po)
    db.flush()
    # Same PO, same product, same pool member: the only difference is line_status, so
    # nothing else can explain a divergence between the two readers.
    db.add(PurchaseOrderLine(
        id=_u(), purchase_order_id=po.id, product_id=chain["product"].id,
        warehouse_id=chain["bin_a"].id, qty_ordered=200, qty_received=0,
        expected_date=date(2026, 8, 25), line_status="open",
    ))
    db.add(PurchaseOrderLine(
        id=_u(), purchase_order_id=po.id, product_id=chain["product"].id,
        warehouse_id=chain["bin_a"].id, qty_ordered=500, qty_received=0,
        expected_date=date(2026, 8, 10), line_status="closed",
    ))
    db.flush()

    on_order = db.execute(
        text(
            "SELECT COALESCE(SUM(on_order), 0) FROM scm.on_order_v "
            "WHERE product_id = :p AND warehouse_id = :w"
        ),
        {"p": chain["product"].id, "w": chain["bin_a"].id},
    ).scalar()

    cov = CoverageService(db).coverage_for(chain["product"].id, pool_id=chain["pool"].id)

    # The invariant: the dashboard's on-order figure and the timeline's supply are the
    # same quantity described two ways.
    assert cov.timeline.closing_balance == float(on_order)
    # And the absolute figure, so a future change that breaks BOTH readers together still
    # fails here rather than agreeing on the wrong number.
    assert float(on_order) == 200
    assert cov.timeline.closing_balance == 200
    # One supply row, not two: the closed line must be absent from the timeline entirely,
    # not merely netted to zero, or the planner reads a delivery that is not coming.
    assert [r.event.ref for r in cov.timeline.rows] == ["", po.po_number]
    assert [r.event.qty for r in cov.timeline.rows] == [0.0, 200.0]


def test_an_undated_commitment_is_reported_rather_than_dated_today(db, chain):
    """Dating it now would fabricate a shortfall; dropping it would hide real demand."""
    so = _so_line(db, chain["product"], chain["bin_a"], 40, None)
    cov = CoverageService(db).coverage_for(chain["product"].id, pool_id=chain["pool"].id)

    assert len(cov.undated_demand) == 1
    assert cov.undated_demand[0].qty == 40
    assert cov.undated_demand[0].so_number == so.so_number
    # It is NOT in the balance, so the plan does not silently act on it either way.
    assert cov.timeline.closing_balance == 0


def test_horizon_excludes_far_future_demand(db, chain):
    _so_line(db, chain["product"], chain["bin_a"], 10, date(2026, 9, 1))
    _so_line(db, chain["product"], chain["bin_a"], 900, date(2030, 9, 1))

    cov = CoverageService(db).coverage_for(
        chain["product"].id, pool_id=chain["pool"].id, horizon_end=date(2027, 1, 1)
    )
    assert cov.timeline.closing_balance == -10


def test_pool_membership_includes_the_pool_itself(db, chain):
    svc = CoverageService(db)
    codes = {w.warehouse_code for w in svc.pool_members(chain["pool"].id)}
    assert chain["pool"].warehouse_code in codes
    assert chain["bin_a"].warehouse_code in codes
    assert chain["bin_b"].warehouse_code in codes


def test_a_location_with_no_pointer_is_its_own_pool(db, chain):
    lone = Warehouse(id=_u(), warehouse_code=unique_code("LONE"), is_active=True)
    db.add(lone)
    db.flush()
    assert CoverageService(db).pool_for_location(lone.id) == lone.id


def test_empty_everything_yields_a_zero_timeline_not_a_crash(db, chain):
    cov = CoverageService(db).coverage_for(chain["product"].id, pool_id=chain["pool"].id)
    assert cov.timeline.closing_balance == 0
    assert cov.timeline.shortfall is None
    assert cov.undated_demand == ()
