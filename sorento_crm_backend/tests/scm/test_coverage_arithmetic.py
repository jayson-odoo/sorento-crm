"""The arithmetic contract the Coverage panel owes its reader.

Every case here is written from the purchasing decision backwards. The panel is read by one
person deciding whether to spend money on a container, and its two halves - the verdict and
the dated timeline beside it - must state one number, not two. A screen that contradicts
itself is not a smaller problem than a screen that is simply wrong: the planner stops
believing both figures, and the tool is abandoned in week one.

The contract, clause by clause, in the order the cases appear below:

1. ``buy_qty`` IS the timeline's ``peak_deficit``. Not demand minus current stock: dated
   supply arriving before the demand covers it, and dated supply arriving after it does
   not, so only the dated walk can size the purchase. A buy that reads high recommends a
   container already on the water; one that reads low is discovered on the delivery date.
2. Availability and the opening balance share ONE basis: on hand. The timeline is the only
   place a promise is subtracted, so a reservation is demand once rather than twice.
3. In-transit supply is attributed per allocation and clamped to what is still on the
   water, so one container cannot be counted as cover by two pools.
4. Stock allocated to a bin in no pool counts for no pool AND is reported, because
   "silently dropped" is the one outcome the design rules out.
5. Shipment status and shipment line status are read the way the rest of the repo reads
   them: a ``partially_received`` container still contributes what is outstanding, a
   ``fully_received`` or ``closed`` one contributes nothing.
6. A sales-order or purchase-order line with a NULL warehouse reaches no pool's balance and
   is reported under ``unplaceable_demand_qty`` / ``unplaceable_on_order_qty``, the same
   treatment unplaceable in-transit stock already had.
7. The pool keeps its name in the verdict even when the pool warehouse itself is
   ``counts_as_available = False``.

Plus the S13b demand rule the whole file rests on: a project-class order is demand only
where the Order Inquiry named it (``demand_origin = scm_order_inquiry``). ``_so_line``
stamps that origin, and one case pins the negative so the next fixture drift fails at the
reader rather than two weeks later in a plan run.

These clauses were red once (the defects #222 fixed) and are green now. They stay here as
the pin: each fails on a WRONG NUMBER or an ABSENT REPORT, never on a seeding error - every
product, warehouse, supplier, customer, SO, PO, shipment and allocation is created here
under the ``ZZT`` marker inside a rolled-back transaction. Nothing is borrowed with
``LIMIT 1``: CI's database is empty, so a borrowed row is the difference between green
locally and a NOT NULL violation in CI.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Optional, Sequence

import pytest

from app.models.inventory import Stock, Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.procurement import (
    InboundShipment,
    InboundShipmentLine,
    PurchaseOrder,
    PurchaseOrderLine,
    SPOAllocation,
    Supplier,
)
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.scm.coverage_service import CoverageService
from app.services.scm.demand import ORDER_INQUIRY_ORIGIN, PROJECT_CLASS
from app.services.scm.coverage_timeline import (
    SOURCE_ORDER,
    SOURCE_POOL,
    SUPPLY_IN_TRANSIT,
)
from app.services.sla_service import MALAYSIA_TZ, to_naive_datetime
from tests._pg_fixture import pg_session, unique_code


def _u() -> str:
    return str(uuid.uuid4())


def _today() -> date:
    """The service's own notion of today: Malaysia wall-clock, not the server's zone."""
    return to_naive_datetime(datetime.now(MALAYSIA_TZ)).date()


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


# --------------------------------------------------------------------------- #
# seeding helpers. Local rather than imported, because several cases need shapes
# the existing helpers cannot express: a reservation, a NULL warehouse, a
# partially received shipment line, a per-allocation received quantity.
# --------------------------------------------------------------------------- #


def _product(db) -> Product:
    cat = ProductCategory(
        id=_u(), category_code=unique_code("CAT")[:40], category_name=unique_code("cat")
    )
    uom = UnitOfMeasure(id=_u(), uom_name=unique_code("uom"), uom_code=unique_code("U")[:20])
    db.add_all([cat, uom])
    db.flush()
    p = Product(
        id=_u(), product_code=unique_code("SKU"), product_name="Wall hung WC",
        category_id=cat.id, base_uom_id=uom.id, list_price=0,
    )
    db.add(p)
    db.flush()
    return p


def _warehouse(db, stem: str, *, pool_of=None, counts_as_available=True) -> Warehouse:
    w = Warehouse(
        id=_u(), warehouse_code=unique_code(stem), warehouse_name=stem.lower(),
        is_active=True, counts_as_available=counts_as_available,
    )
    db.add(w)
    db.flush()
    # A pool is its own pool, which is how `pool_members` finds it in its own member list.
    w.pool_warehouse_id = pool_of.id if pool_of is not None else w.id
    db.flush()
    return w


@pytest.fixture()
def chain(db):
    """One product, one pool, two member bins. The single-pool shape."""
    product = _product(db)
    pool = _warehouse(db, "POOL")
    return {
        "product": product,
        "pool": pool,
        "bin_a": _warehouse(db, "BINA", pool_of=pool),
        "bin_b": _warehouse(db, "BINB", pool_of=pool),
    }


@pytest.fixture()
def two_pools(db):
    """One product and TWO independent pools, each with a member bin.

    Two pools is what makes a per-pool cap visible: a quantity counted once too often shows
    up only when there is a second pool for the duplicate to land on.
    """
    product = _product(db)
    pool_a = _warehouse(db, "POOLA")
    pool_b = _warehouse(db, "POOLB")
    return {
        "product": product,
        "pool_a": pool_a, "bin_a": _warehouse(db, "BINA", pool_of=pool_a),
        "pool_b": pool_b, "bin_b": _warehouse(db, "BINB", pool_of=pool_b),
    }


def _stock(db, product, wh, on_hand, reserved=0) -> Stock:
    row = Stock(
        id=_u(), product_id=product.id, warehouse_id=wh.id,
        quantity_on_hand=on_hand, quantity_reserved=reserved,
    )
    db.add(row)
    db.flush()
    return row


def _so_line(
    db, product, wh, qty, when, *, line_status="open", demand_origin=ORDER_INQUIRY_ORIGIN
) -> SalesOrder:
    """One open SO carrying one open line. ``wh`` may be None: the column is nullable.

    The customer is a project customer (TUJU RESIDENCE), so the order is project-class, and
    S13b says a project-class order is demand only where the Order Inquiry named it. The
    origin stamp is therefore part of the seed, not decoration: without it every case below
    would resolve against zero demand and would be proving nothing about the arithmetic.
    ``demand_origin=None`` is the one case that WANTS the line set aside - see
    ``test_a_project_line_the_order_inquiry_never_named_is_not_demand``.
    """
    cust = Customer(id=_u(), customer_code=unique_code("C"), customer_name="TUJU RESIDENCE")
    db.add(cust)
    db.flush()
    so = SalesOrder(
        id=_u(), so_number=unique_code("SO"), status="open",
        customer_id=cust.id, demand_class=PROJECT_CLASS, demand_origin=demand_origin,
    )
    db.add(so)
    db.flush()
    db.add(SalesOrderLine(
        id=_u(), sales_order_id=so.id, product_id=product.id,
        warehouse_id=(wh.id if wh is not None else None),
        qty_ordered=qty, qty_delivered=0, line_status=line_status, required_date=when,
    ))
    db.flush()
    return so


def _po_line(db, product, wh, qty, when, *, status="active", line_status="open"):
    """A placed PO carrying one line, returned so an allocation can point at the line."""
    sup = Supplier(id=_u(), supplier_code=unique_code("S"), supplier_name="GUANGDONG SW")
    db.add(sup)
    db.flush()
    po = PurchaseOrder(id=_u(), po_number=unique_code("PO"), supplier_id=sup.id, status=status)
    db.add(po)
    db.flush()
    line = PurchaseOrderLine(
        id=_u(), purchase_order_id=po.id, product_id=product.id,
        warehouse_id=(wh.id if wh is not None else None),
        qty_ordered=qty, qty_received=0, expected_date=when, line_status=line_status,
    )
    db.add(line)
    db.flush()
    return po, line


def _shipment(
    db, product, *, shipped, received, arrival, status="in_transit", line_status="in_transit"
):
    """One inbound shipment carrying one line for ``product``.

    ``spo_allocations`` rows are added separately by ``_alloc`` because the interesting cases
    are all about several allocations against ONE line.
    """
    sup = Supplier(id=_u(), supplier_code=unique_code("S"), supplier_name="GUANGDONG SW")
    db.add(sup)
    db.flush()
    ship = InboundShipment(
        id=_u(), shipment_number=unique_code("SH")[:50], supplier_id=sup.id,
        shipment_date=_today() - timedelta(days=20),
        estimated_arrival_date=arrival, shipment_status=status,
    )
    db.add(ship)
    db.flush()
    line = InboundShipmentLine(
        id=_u(), shipment_id=ship.id, product_id=product.id,
        quantity_shipped=shipped, quantity_received=received, cartons_count=1,
        spo_allocated_quantity=0, line_status=line_status,
    )
    db.add(line)
    db.flush()
    return ship, line


def _alloc(db, ship, product, wh, *, allocated, received=0) -> SPOAllocation:
    row = SPOAllocation(
        id=_u(), spo_number=unique_code("SPO")[:50], inbound_shipment_id=ship.id,
        product_id=product.id, warehouse_id=wh.id,
        allocated_quantity=allocated, quantity_received=received,
    )
    db.add(row)
    db.flush()
    return row


def _in_transit_qty(cov) -> float:
    return sum(r.event.qty for r in cov.timeline.rows if r.event.supply_stage == SUPPLY_IN_TRANSIT)


# =========================================================================== #
# CLAUSE 0: what counts as demand at all (S13b)
#
# Every case below seeds a project customer, so every case below depends on the origin
# stamp `_so_line` writes. Pinned first, in both directions, because the failure it guards
# is silent: a project line the Order Inquiry never named is correctly set aside, and a
# fixture that forgets the stamp turns every arithmetic case underneath into an assertion
# about zero demand that happens to be green.
# =========================================================================== #


def test_a_project_line_the_order_inquiry_never_named_is_not_demand(db, chain):
    """CS decides what purchasing sees on the project side; the book does not.

    A project-class sales order carrying no `demand_origin` was never named by the Order
    Inquiry, which is CS saying "not yet". It stays on the customer's order (they are still
    owed it) and it is not a commitment the engine plans against, so it puts nothing on the
    timeline and buys nothing. The whole of this file rests on that rule holding, which is
    why it is asserted here rather than assumed.
    """
    product = chain["product"]
    _so_line(db, product, chain["bin_a"], 100, _today() + timedelta(days=30),
             demand_origin=None)

    cov = CoverageService(db).coverage_for(product.id, pool_id=chain["pool"].id)

    assert [r.event.kind for r in cov.timeline.rows if r.event.kind == "demand"] == [], (
        "a project line the Order Inquiry never named is not a demand event"
    )
    assert cov.timeline.closing_balance == 0
    assert cov.timeline.peak_deficit == 0
    assert cov.buy_qty == 0


def test_the_same_line_named_by_the_order_inquiry_is_demand(db, chain):
    """The positive half, so "count nothing" cannot pass for the rule above.

    One character of difference from the case above - the origin stamp - and the same 100
    units are a commitment the engine plans against. Without this pair, an engine that
    dropped project demand entirely would satisfy the guard and quietly stop buying for
    every project in the book.
    """
    product = chain["product"]
    _so_line(db, product, chain["bin_a"], 100, _today() + timedelta(days=30))

    cov = CoverageService(db).coverage_for(product.id, pool_id=chain["pool"].id)

    assert cov.timeline.peak_deficit == 100
    assert cov.buy_qty == 100


# =========================================================================== #
# CLAUSE 1: buy_qty is the timeline's peak deficit
#
# What must be bought is what DATED supply cannot cover, which the timeline already
# computes: `peak_deficit` against the floor. Sizing the buy on total demand against
# CURRENT stock instead prints a dateless residual beside a dated timeline that disagrees
# with it, which is what these cases exist to stop coming back.
# =========================================================================== #


def test_supply_arriving_before_the_demand_means_nothing_has_to_be_bought(db, chain):
    """Buying a second container because the first one is not on this screen is real money.

    500 units land ten days from now, 100 are due thirty days from now, and the pool holds
    nothing today. The timeline closes at 400 and never dips below zero, so the only correct
    advice is "it is covered, do not buy". A panel that prints "Buy 100" in an alarm colour
    beside a healthy balance puts the two figures two inches apart on one screen: a planner
    who acts on the loud one orders a container that is already on the water, and a planner
    who learns to ignore it stops reading the panel at all.
    """
    product = chain["product"]
    # An allocated shipment, not a purchase order: PO -> SPO -> GRN, and only the allocation
    # is stock actually on the water. The point of the test is unchanged.
    ship, _line = _shipment(
        db, product, shipped=500, received=0, arrival=_today() + timedelta(days=10)
    )
    _alloc(db, ship, product, chain["bin_a"], allocated=500)
    _so_line(db, product, chain["bin_a"], 100, _today() + timedelta(days=30))

    cov = CoverageService(db).coverage_for(product.id, pool_id=chain["pool"].id)

    # The timeline's own verdict first, so a failure here is unambiguously about `buy_qty`
    # rather than about the balance being wrong.
    assert cov.timeline.closing_balance == 400
    assert cov.timeline.shortfall is None
    assert cov.timeline.peak_deficit == 0

    assert cov.buy_qty == 0, "recommends buying what is already arriving"
    assert cov.buy_qty == cov.timeline.peak_deficit
    assert cov.use_stock is True


def test_supply_arriving_after_the_demand_still_has_to_be_bought(db, chain):
    """The opposite direction, so "always trust the closing balance" cannot pass for a fix.

    Late supply does not cover an earlier commitment. 100 are due in thirty days and 500
    arrive in fifty, so the closing balance is a comfortable 400 while the order due first
    cannot be shipped. Netting on the closing balance would silently drop the buy and the
    customer would find out on the delivery date.
    """
    product = chain["product"]
    _so_line(db, product, chain["bin_a"], 100, _today() + timedelta(days=30))
    ship, _line = _shipment(
        db, product, shipped=500, received=0, arrival=_today() + timedelta(days=50)
    )
    _alloc(db, ship, product, chain["bin_a"], allocated=500)

    cov = CoverageService(db).coverage_for(product.id, pool_id=chain["pool"].id)

    assert cov.timeline.closing_balance == 400, "healthy at the end, short in the middle"
    assert cov.timeline.peak_deficit == 100
    assert cov.buy_qty == 100
    assert cov.buy_qty == cov.timeline.peak_deficit
    assert cov.use_stock is False


def test_with_no_supply_at_all_the_whole_shortfall_is_bought(db, chain):
    """The base case, pinned so a fix cannot reach zero by ignoring demand instead.

    Nothing on hand, nothing on order, 100 committed. The answer is the full 100, and it is
    the answer the panel gives today - which is exactly why it has to be pinned: a change
    that makes the first case pass by always returning zero would be worse than the defect.
    """
    product = chain["product"]
    _so_line(db, product, chain["bin_a"], 100, _today() + timedelta(days=30))

    cov = CoverageService(db).coverage_for(product.id, pool_id=chain["pool"].id)

    assert cov.timeline.peak_deficit == 100
    assert cov.buy_qty == 100
    assert cov.buy_qty == cov.timeline.peak_deficit
    assert cov.use_stock is False


def test_the_allocations_still_say_where_todays_cover_comes_from_when_nothing_is_bought(
    db, chain
):
    """The split survives, but it can never imply a purchase the timeline contradicts.

    The allocations answer a different question from ``buy_qty``: they say WHERE the units a
    person can pick today come from (own bin, shared pool, another holder's bin), and that is
    what turns "you have cover" into an instruction somebody can act on. So 30 units sitting
    in the pool must still be reported as pool cover. What must NOT survive is the residual:
    with 500 arriving before the 100 is due, the 70 the dateless comparison cannot place is
    not a purchase, it is an artefact of comparing a dated commitment against an undated
    snapshot.
    """
    product = chain["product"]
    _stock(db, product, chain["pool"], 30)
    ship, _line = _shipment(
        db, product, shipped=500, received=0, arrival=_today() + timedelta(days=10)
    )
    _alloc(db, ship, product, chain["bin_a"], allocated=500)
    _so_line(db, product, chain["bin_a"], 100, _today() + timedelta(days=30))

    cov = CoverageService(db).coverage_for(product.id, pool_id=chain["pool"].id)

    assert cov.timeline.peak_deficit == 0
    assert cov.buy_qty == 0
    # The pool slice is still described, so the panel can still say "use the pool".
    pool_slice = [a for a in cov.allocations if a.source_type == SOURCE_POOL]
    assert [a.qty for a in pool_slice] == [30]
    # And no purchase slice, because a purchase slice IS the recommendation.
    assert [a for a in cov.allocations if a.source_type == SOURCE_ORDER] == []


def test_the_buy_is_sized_on_the_floor_the_timeline_was_given(db, chain):
    """A reorder point is a floor, and the buy has to reach it, not merely reach zero.

    The floor is a computed reorder point for a continuous SKU, so "covered" means "never
    falls below the reorder point", not "never falls below zero". With 500 arriving early
    against 100 of demand the balance never touches zero, yet the SKU opens at nothing
    against a floor of 200: it is under its reorder point today. Sizing the buy on demand
    minus stock reports 100 - the demand - when the quantity that actually has to be covered
    is the 200 the floor is short by.
    """
    product = chain["product"]
    # An allocated shipment, not a purchase order: PO -> SPO -> GRN, and only the allocation
    # is stock actually on the water. The point of the test is unchanged.
    ship, _line = _shipment(
        db, product, shipped=500, received=0, arrival=_today() + timedelta(days=10)
    )
    _alloc(db, ship, product, chain["bin_a"], allocated=500)
    _so_line(db, product, chain["bin_a"], 100, _today() + timedelta(days=30))

    cov = CoverageService(db).coverage_for(product.id, pool_id=chain["pool"].id, floor=200)

    assert cov.timeline.peak_deficit == 200
    assert cov.buy_qty == 200
    assert cov.buy_qty == cov.timeline.peak_deficit


# =========================================================================== #
# CLAUSE 2: a reservation is demand once
#
# `availability()` and `_opening()` share one basis, on hand, because the SO line that DID
# the reserving is already a demand event on the timeline. Reading the GENERATED
# `Stock.quantity_available` (on hand minus reserved) in one half and `quantity_on_hand` in
# the other subtracts the same reservation twice.
# =========================================================================== #


def test_a_reservation_is_demand_once_not_twice(db, chain):
    """A reserved unit must not read as a unit that has to be bought.

    100 sit in the pool, all 100 reserved against one open order for 100. The timeline is
    exactly right: opening 100, demand 100, balance 0, nothing short. A panel that answered
    opening 100, own 0, pool 0, "Buy 100" would be asking the database for
    on-hand-minus-reserved and then subtracting the very same order again on the timeline.
    Reserving stock is the normal state of a healthy order book, so that does not misfire on
    an edge case: it fires on every SKU with a live reservation, and it recommends re-buying
    stock already standing in the warehouse with the customer's name on it.
    """
    product = chain["product"]
    _stock(db, product, chain["pool"], 100, reserved=100)
    _so_line(db, product, chain["bin_a"], 100, _today() + timedelta(days=30))

    cov = CoverageService(db).coverage_for(product.id, pool_id=chain["pool"].id)

    # The timeline, which already reads on-hand, is the basis availability has to share.
    assert cov.opening_balance == 100
    assert cov.timeline.closing_balance == 0
    assert cov.timeline.shortfall is None

    # The source split has to show the 100 that are physically there.
    assert cov.availability.pool == 100, "reserved stock is still stock, and it is here"
    assert [(a.source_type, a.qty) for a in cov.allocations] == [(SOURCE_POOL, 100)]
    assert cov.buy_qty == 0
    assert cov.use_stock is True


def test_partly_reserved_stock_reports_the_whole_on_hand_quantity(db, chain):
    """The same rule where only part of the pool is spoken for, so no cancellation hides it.

    200 on hand, 60 reserved, 60 committed on the timeline. If ``availability`` reads
    on-hand-minus-reserved it reports 140 and the balance reports 140 too - the numbers agree
    by coincidence because the reservation and the commitment are the same 60. What is being
    pinned is the BASIS: availability describes what is in the building (200), and the
    timeline is the thing that subtracts what is promised.
    """
    product = chain["product"]
    _stock(db, product, chain["pool"], 200, reserved=60)
    _so_line(db, product, chain["bin_a"], 60, _today() + timedelta(days=30))

    cov = CoverageService(db).coverage_for(product.id, pool_id=chain["pool"].id)

    assert cov.opening_balance == 200
    assert cov.availability.pool == 200, "availability and the opening balance share a basis"
    assert cov.timeline.closing_balance == 140
    assert cov.buy_qty == 0


# =========================================================================== #
# CLAUSE 3: a partial receipt is attributed per allocation, across pools
#
# `spo_allocations.allocated_quantity` is never decremented on receipt
# (incoming_stock_service.py:78-80), so the quantity still coming to a site is its
# allocation minus its own `quantity_received`, and the total attributed is clamped to what
# the line still owes. A per-pool cap lets every pool claim the whole outstanding quantity
# and one container becomes cover twice.
# =========================================================================== #


def test_a_partial_receipt_is_attributed_per_allocation_not_capped_per_pool(db, two_pools):
    """40 units are on the water and the system reports 80 units of cover.

    One container: 100 shipped, 60 landed, 40 still coming. Half was allocated to each of two
    sites; site A has taken all 50 of its half, site B only 10 of its. The 40 outstanding are
    therefore all site B's. Today each pool caps the line's outstanding at its own allocation
    and both claim 40, so the business believes it has 80 units arriving against 40 that
    exist. Two purchases are suppressed by one container, and neither screen says anything
    that looks wrong on its own, which is why this survives review.
    """
    product = two_pools["product"]
    arrival = _today() + timedelta(days=12)
    ship, _line = _shipment(db, product, shipped=100, received=60, arrival=arrival)
    _alloc(db, ship, product, two_pools["bin_a"], allocated=50, received=50)
    _alloc(db, ship, product, two_pools["bin_b"], allocated=50, received=10)

    svc = CoverageService(db)
    cov_a = svc.coverage_for(product.id, pool_id=two_pools["pool_a"].id)
    cov_b = svc.coverage_for(product.id, pool_id=two_pools["pool_b"].id)

    # Site A has already received everything it was allocated: nothing more is coming there.
    assert _in_transit_qty(cov_a) == 0
    # Site B is still owed 40 of its 50.
    assert _in_transit_qty(cov_b) == 40
    # The invariant behind both: the quantity still on the water exists exactly once.
    assert _in_transit_qty(cov_a) + _in_transit_qty(cov_b) == 40
    assert cov_a.timeline.closing_balance == 0
    assert cov_b.timeline.closing_balance == 40


def test_the_attributed_total_never_exceeds_what_is_still_on_the_water(db, two_pools):
    """Over-allocation is a data error, and inflating supply is the wrong way to survive it.

    The allocations here claim 120 against a line that shipped 100 and received 60, so the
    remaining allocations (50 + 50) already exceed the 40 outstanding. Clamping to the line's
    outstanding is the honest answer: an allocation cannot deliver units the supplier is not
    sending. Understating cover costs one visible extra purchase; overstating it suppresses
    purchases silently, which is the failure nobody catches.
    """
    product = two_pools["product"]
    ship, _line = _shipment(
        db, product, shipped=100, received=60, arrival=_today() + timedelta(days=12)
    )
    _alloc(db, ship, product, two_pools["bin_a"], allocated=60, received=0)
    _alloc(db, ship, product, two_pools["bin_b"], allocated=60, received=0)

    svc = CoverageService(db)
    cov_a = svc.coverage_for(product.id, pool_id=two_pools["pool_a"].id)
    cov_b = svc.coverage_for(product.id, pool_id=two_pools["pool_b"].id)

    total = _in_transit_qty(cov_a) + _in_transit_qty(cov_b)
    assert total <= 40, f"attributed {total} against 40 still outstanding"


# =========================================================================== #
# CLAUSE 4: an allocation to a warehouse in NO pool is reported, not dropped
#
# `pool_members()` filters `counts_as_available`, so a quarantine bin belongs to no pool and
# is rightly on no pool's timeline. It must therefore reach `unattributed_in_transit_qty`:
# counting it as "placed" for that total as well leaves the stock on no timeline AND on no
# report, which is the one outcome the design rules out.
# =========================================================================== #


def test_stock_allocated_to_a_bin_in_no_pool_is_reported_rather_than_dropped(db, two_pools):
    """Sixty units disappear from the business with nothing on any screen to say so.

    A container allocated to a quarantine bin cannot be sold from any pool, so it is right
    that no pool's balance counts it. But it is real stock somebody paid for, and the ONLY
    way anyone learns it is stuck there is a figure that names it. Today the allocation is
    counted as "placed" for the purpose of the unattributed total and excluded for the
    purpose of every timeline, so it lands in neither: the module reports 0 unattributed
    while 60 units sit somewhere nobody is looking. Silently dropped is the one outcome the
    design rules out.
    """
    product = two_pools["product"]
    quarantine = _warehouse(db, "QUAR", counts_as_available=False)
    ship, _line = _shipment(
        db, product, shipped=60, received=0, arrival=_today() + timedelta(days=12)
    )
    _alloc(db, ship, product, quarantine, allocated=60, received=0)

    svc = CoverageService(db)
    cov_a = svc.coverage_for(product.id, pool_id=two_pools["pool_a"].id)
    cov_b = svc.coverage_for(product.id, pool_id=two_pools["pool_b"].id)

    # On no pool's timeline: a quarantine bin is not cover for anyone.
    assert _in_transit_qty(cov_a) == 0
    assert _in_transit_qty(cov_b) == 0
    # And SAID, on both, because "which pool should have told me" has no answer.
    assert cov_a.unattributed_in_transit_qty == 60
    assert cov_b.unattributed_in_transit_qty == 60


# =========================================================================== #
# CLAUSE 5: shipment status is read the way the rest of the repo reads it
#
# The column's vocabulary is fixed by the `inbound_shipments_shipment_status_check`
# constraint (in_transit, arrived_at_port, at_warehouse, partially_received,
# fully_received, closed), and `incoming_stock_service._still_incoming_filter` and
# `procurement_service._is_received_status` both test against RECEIVED rather than for a
# known-good list. A whitelist here drops the most common live state, `partially_received`,
# and the shipment half must apply a line-status predicate the purchase-order half already
# applies.
# =========================================================================== #


def test_a_partially_received_shipment_still_contributes_what_is_outstanding(db, chain):
    """The most common state of a live container is the one state that reports nothing.

    A container half unloaded carries ``partially_received``, and that value was not in the
    coverage whitelist, so the 60 units still on the vessel dropped out of the plan entirely.
    The planner sees no supply, buys again, and the second container arrives behind the
    first. Every long-running import passes through this status, so the whitelist does not
    fail on an exotic value - it fails in the middle of the normal lifecycle.
    """
    product = chain["product"]
    ship, _line = _shipment(
        db, product, shipped=100, received=40,
        arrival=_today() + timedelta(days=12), status="partially_received",
    )
    _alloc(db, ship, product, chain["bin_a"], allocated=100, received=40)

    cov = CoverageService(db).coverage_for(product.id, pool_id=chain["pool"].id)

    assert _in_transit_qty(cov) == 60
    assert cov.timeline.closing_balance == 60


def test_a_fully_received_shipment_contributes_nothing(db, chain):
    """The other side of the blacklist: landed stock is on hand, and counting it twice.

    Pinned alongside the case above so a fix cannot simply widen the whitelist until
    everything qualifies. ``fully_received`` is the terminal value ``procurement_service``
    writes, and the units it describes are already in the ``stock`` table feeding the
    opening balance.
    """
    product = chain["product"]
    _stock(db, product, chain["pool"], 100)
    ship, _line = _shipment(
        db, product, shipped=100, received=100,
        arrival=_today() - timedelta(days=2), status="fully_received",
    )
    _alloc(db, ship, product, chain["bin_a"], allocated=100, received=100)

    cov = CoverageService(db).coverage_for(product.id, pool_id=chain["pool"].id)

    assert _in_transit_qty(cov) == 0
    assert cov.timeline.closing_balance == 100


def test_a_closed_shipment_line_is_not_supply_the_way_a_closed_po_line_is_not(db, chain):
    """One function cannot hold two opinions about what "still open" means.

    The purchase-order half of ``_supply_events`` filters ``PurchaseOrderLine.line_status ==
    'open'`` precisely because a line that left the order book is not incoming, and
    ``incoming_stock_service._still_incoming_filter`` applies the same rule to
    ``InboundShipmentLine.line_status``. The shipment half of this very function applies no
    line-status predicate at all, so a line somebody has closed short keeps arriving on the
    timeline forever and keeps covering demand that is in fact uncovered. The two halves
    disagreeing is the defect; which of them is right is not in question.
    """
    product = chain["product"]
    ship, _line = _shipment(
        db, product, shipped=100, received=0,
        arrival=_today() + timedelta(days=12), line_status="received",
    )
    _alloc(db, ship, product, chain["bin_a"], allocated=100, received=0)

    cov = CoverageService(db).coverage_for(product.id, pool_id=chain["pool"].id)

    assert _in_transit_qty(cov) == 0
    assert cov.timeline.closing_balance == 0


def test_a_closed_shipment_is_not_in_transit_supply(db, chain):
    """A shipment closed off the book is not still on the water.

    Found by the same constraint that rejected the earlier seeds: the column admits
    ``closed`` and the excluded set did not list it, while listing three values
    (``received`` / ``completed`` / ``cancelled``) the constraint forbids. So the one real
    terminal state that was reachable was the one that still contributed cover, which is the
    fail-open direction - it suppresses a purchase and nothing on screen admits it.
    """
    product = chain["product"]
    ship, _line = _shipment(
        db, product, shipped=100, received=0,
        arrival=_today() + timedelta(days=12), status="closed",
    )
    _alloc(db, ship, product, chain["bin_a"], allocated=100, received=0)

    cov = CoverageService(db).coverage_for(product.id, pool_id=chain["pool"].id)

    assert _in_transit_qty(cov) == 0
    assert cov.timeline.closing_balance == 0


# =========================================================================== #
# CLAUSE 6: a line with a NULL warehouse is reported, never dropped in silence
#
# Both `sales_order_lines.warehouse_id` and `purchase_order_lines.warehouse_id` are nullable,
# and `warehouse_id.in_(wh_ids)` evaluates to NULL for them, so the row matches no pool. The
# module already reports in-transit stock it cannot place; demand and on-order supply it
# cannot place are reported the same way rather than vanishing.
#
# SHAPE. The quantity is what is pinned, not the field name: the tests below accept a scalar
# quantity field OR a tuple of records carrying `.qty`, under any of a small set of names
# consistent with the module's existing vocabulary (`unattributed_in_transit_qty`,
# `undated_demand`). The preferred names are the first in each tuple.
# =========================================================================== #

_UNPLACEABLE_DEMAND_FIELDS = (
    "unplaceable_demand_qty",
    "unplaceable_demand",
    "unlocated_demand_qty",
    "unlocated_demand",
    "demand_without_location",
)
_UNPLACEABLE_SUPPLY_FIELDS = (
    "unplaceable_on_order_qty",
    "unplaceable_on_order",
    "unattributed_on_order_qty",
    "unlocated_on_order_qty",
    "supply_without_location",
)


def _reported_qty(cov, names: Sequence[str]) -> Optional[float]:
    """The quantity the payload reports under any of ``names``, or None if it reports none.

    Accepts a scalar (mirroring ``unattributed_in_transit_qty``) or a sequence of records
    carrying ``qty`` (mirroring ``undated_demand``), because both are established shapes in
    this module and the defect is about the quantity being ABSENT, not about which shape
    carries it.
    """
    for name in names:
        value = getattr(cov, name, None)
        if value is None:
            continue
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, (list, tuple)):
            return float(sum(float(getattr(item, "qty", 0) or 0) for item in value))
    return None


def test_demand_with_no_warehouse_is_reported_rather_than_swallowed(db, chain):
    """Eighty units of real commitment must not leave the plan without a trace.

    ``warehouse_id`` is nullable and imports leave it empty whenever the source sheet had no
    location column, so this is not a theoretical row. ``warehouse_id.in_(...)`` is NULL for
    it, NULL is not TRUE, and the line matches no pool - so unless it is reported, a customer
    order the company has accepted contributes to no balance, triggers no shortfall and
    appears on no screen. The
    module already refuses to guess a DATE for a commitment (``undated_demand``) precisely
    because guessing fabricates a shortfall; refusing to guess a LOCATION has to be reported
    the same way, or the same commitment silently disappears instead.
    """
    product = chain["product"]
    _so_line(db, product, None, 80, _today() + timedelta(days=30))

    cov = CoverageService(db).coverage_for(product.id, pool_id=chain["pool"].id)

    reported = _reported_qty(cov, _UNPLACEABLE_DEMAND_FIELDS)
    assert reported == 80, (
        "unplaceable demand is on no timeline and on no report; expected it under one of "
        f"{_UNPLACEABLE_DEMAND_FIELDS}, got {reported!r}"
    )


def test_ordered_supply_with_no_warehouse_is_reported_rather_than_swallowed(db, chain):
    """Five hundred units on order that nobody can see are five hundred bought twice.

    Same nullable column on the purchase side. A purchase order is no longer counted as
    supply, but it is still REPORTED as ordered - and one whose line names no warehouse
    reaches no pool's ordered figure either, so it would be in no number at all. A buyer
    with no way to see the 500 already on order raises a second order for them.
    """
    product = chain["product"]
    _po_line(db, product, None, 500, _today() + timedelta(days=10))

    cov = CoverageService(db).coverage_for(product.id, pool_id=chain["pool"].id)

    reported = _reported_qty(cov, _UNPLACEABLE_SUPPLY_FIELDS)
    assert reported == 500, (
        "unplaceable ordered quantity is on no timeline and on no report; expected it under "
        f"one of {_UNPLACEABLE_SUPPLY_FIELDS}, got {reported!r}"
    )
    assert _in_transit_qty(cov) == 0, "and it is still not supply"


def test_unplaceable_rows_stay_out_of_the_pool_balance(db, chain):
    """GUARD: reporting them must not become netting them into whichever pool was asked.

    A line with no location belongs to no pool, so adding it to the pool the caller happened
    to name would invent cover (or a shortfall) at a site the data never mentioned - and with
    two pools it would do so twice. Excluded from the balance AND named on the report is the
    treatment ``unattributed_in_transit_qty`` already established.
    """
    product = chain["product"]
    _so_line(db, product, None, 80, _today() + timedelta(days=30))
    _po_line(db, product, None, 500, _today() + timedelta(days=10))

    cov = CoverageService(db).coverage_for(product.id, pool_id=chain["pool"].id)

    assert cov.timeline.closing_balance == 0
    assert [r.event.ref for r in cov.timeline.rows] == [""]


def test_a_line_that_does_have_a_warehouse_is_not_reported_as_unplaceable(db, chain):
    """GUARD: the new report must not fire on the ordinary case.

    Without this, an implementation that reports every line as unplaceable would satisfy the
    two cases above while telling a planner that demand they can see on the timeline is also
    missing a location.
    """
    product = chain["product"]
    _so_line(db, product, chain["bin_a"], 80, _today() + timedelta(days=30))
    ship, _line = _shipment(
        db, product, shipped=500, received=0, arrival=_today() + timedelta(days=10)
    )
    _alloc(db, ship, product, chain["bin_a"], allocated=500)

    cov = CoverageService(db).coverage_for(product.id, pool_id=chain["pool"].id)

    assert _reported_qty(cov, _UNPLACEABLE_DEMAND_FIELDS) in (None, 0.0)
    assert _reported_qty(cov, _UNPLACEABLE_SUPPLY_FIELDS) in (None, 0.0)
    assert cov.timeline.closing_balance == 420


# =========================================================================== #
# REPORTING PIN: the pool's name survives an unavailable pool warehouse
# =========================================================================== #


def test_the_pool_keeps_its_name_when_the_pool_bin_itself_is_unavailable(db):
    """The verdict is "use BRW", and without the name it is "use ".

    A site whose own pool row is marked ``counts_as_available = False`` (its stock is not
    sellable, but its sub-bins are) is excluded from ``pool_members``, and ``pool_code`` is
    derived by looking for the pool inside that member list. So the panel prints "pool" with
    a blank beside it and the answer the module exists to give loses the only word that makes
    it actionable: a planner cannot go and fetch stock from a pool nobody named.
    """
    product = _product(db)
    pool = _warehouse(db, "POOL", counts_as_available=False)
    bin_a = _warehouse(db, "BINA", pool_of=pool)
    _stock(db, product, bin_a, 400)

    cov = CoverageService(db).coverage_for(product.id, pool_id=pool.id)

    assert cov.pool_code == pool.warehouse_code, "the pool lost its name"
    # The member bin still nets normally, so this is about the label and nothing else.
    assert cov.opening_balance == 400
