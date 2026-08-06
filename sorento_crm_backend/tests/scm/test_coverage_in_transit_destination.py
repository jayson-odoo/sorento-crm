"""DEFECT 1: in-transit supply has no destination, so one container is counted once PER POOL.

``CoverageService._supply_events`` scopes the PURCHASE-ORDER half by
``PurchaseOrderLine.warehouse_id.in_(wh_ids)``, but the INBOUND-SHIPMENT half filters on
product and shipment status only. Neither ``inbound_shipments`` nor
``inbound_shipment_lines`` carries a destination warehouse column at all, so every
in-transit quantity for a SKU is added to EVERY pool's timeline for that SKU. With two
pools the same 60-unit container arrives twice, the plan reads 120 units of cover that do
not exist, and the purchase that should have been raised is suppressed - invisibly, because
each pool's screen looks internally consistent.

The destination is derivable: ``spo_allocations`` names the shipment, the product and the
PO line it draws down (``po_line_id``, added by migration 311 for exactly this chain), and
``purchase_order_lines.warehouse_id`` names the bin, which resolves to a pool. A shipment
line with NO allocation therefore has no derivable destination, and the honest treatment is
to EXCLUDE it from every pool rather than add it to all of them - with the excluded quantity
surfaced on the result (``unattributed_in_transit_qty``) so a person can see that supply was
set aside rather than silently vanished.

TEST-FIRST. These are expected to be red on the current behaviour: the pool that owns the
container is right today by accident, the pool that does not own it is wrong, and the
unattributed figure does not exist yet.

Seeding. Every product, warehouse, supplier, PO, shipment and allocation is created here
under the ``ZZT`` marker inside a rolled-back transaction. Nothing is borrowed with
``LIMIT 1``: CI's database is empty, so a borrowed row is the difference between green
locally and a NOT NULL violation in CI.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest

from app.models.inventory import Warehouse
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
from app.services.scm.coverage_timeline import SUPPLY_IN_TRANSIT, SUPPLY_ON_ORDER
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


@pytest.fixture()
def two_pools(db):
    """One product and TWO independent pools, each with a member bin.

    Two pools is the whole point: a defect that adds one container to every pool is
    invisible with a single pool, because there is nowhere for the duplicate to show up.
    """
    cat = ProductCategory(
        id=_u(), category_code=unique_code("CAT")[:40], category_name=unique_code("cat")
    )
    uom = UnitOfMeasure(id=_u(), uom_name=unique_code("uom"), uom_code=unique_code("U")[:20])
    db.add_all([cat, uom])
    db.flush()

    product = Product(
        id=_u(), product_code=unique_code("SKU"), product_name="Wall hung WC",
        category_id=cat.id, base_uom_id=uom.id, list_price=0,
    )
    pool_a = Warehouse(
        id=_u(), warehouse_code=unique_code("POOLA"), warehouse_name="pool a", is_active=True
    )
    pool_b = Warehouse(
        id=_u(), warehouse_code=unique_code("POOLB"), warehouse_name="pool b", is_active=True
    )
    db.add_all([product, pool_a, pool_b])
    db.flush()

    bin_a = Warehouse(
        id=_u(), warehouse_code=unique_code("BINA"), warehouse_name="bin a",
        is_active=True, pool_warehouse_id=pool_a.id,
    )
    bin_b = Warehouse(
        id=_u(), warehouse_code=unique_code("BINB"), warehouse_name="bin b",
        is_active=True, pool_warehouse_id=pool_b.id,
    )
    pool_a.pool_warehouse_id = pool_a.id  # a pool is its own pool
    pool_b.pool_warehouse_id = pool_b.id
    db.add_all([bin_a, bin_b])
    db.flush()
    return {
        "product": product,
        "pool_a": pool_a, "bin_a": bin_a,
        "pool_b": pool_b, "bin_b": bin_b,
    }


def _po_with_line(db, product, wh, qty, when, *, status="active"):
    """A placed PO carrying one open line, returned so an allocation can point at the line.

    ``test_coverage_service._po_line`` returns only the header, and the allocation chain
    needs the LINE, so this is a local variant rather than a reuse.
    """
    sup = Supplier(id=_u(), supplier_code=unique_code("S"), supplier_name="GUANGDONG SW")
    db.add(sup)
    db.flush()
    po = PurchaseOrder(id=_u(), po_number=unique_code("PO"), supplier_id=sup.id, status=status)
    db.add(po)
    db.flush()
    line = PurchaseOrderLine(
        id=_u(), purchase_order_id=po.id, product_id=product.id, warehouse_id=wh.id,
        qty_ordered=qty, qty_received=0, expected_date=when, line_status="open",
    )
    db.add(line)
    db.flush()
    return po, line


def _in_transit(db, product, qty, arrival, *, po_line=None, status="in_transit"):
    """One inbound shipment carrying one line for ``product``.

    With ``po_line`` an ``spo_allocations`` row is written, which is the ONLY thing that
    says where the container is going. Without it the line is deliberately destination-less,
    which is the shape the unattributed case is about.
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
    db.add(InboundShipmentLine(
        id=_u(), shipment_id=ship.id, product_id=product.id,
        quantity_shipped=qty, quantity_received=0, cartons_count=1,
        spo_allocated_quantity=(qty if po_line is not None else 0),
        line_status="in_transit",
    ))
    db.flush()
    if po_line is not None:
        db.add(SPOAllocation(
            id=_u(), spo_number=unique_code("SPO")[:50], inbound_shipment_id=ship.id,
            product_id=product.id, warehouse_id=po_line.warehouse_id,
            allocated_quantity=qty, po_line_id=po_line.id,
        ))
        db.flush()
    return ship


def _in_transit_rows(cov):
    return [r for r in cov.timeline.rows if r.event.supply_stage == SUPPLY_IN_TRANSIT]


# =========================================================================== #
# a. THE regression: one container, one pool
# =========================================================================== #

def test_an_allocated_container_reaches_only_the_pool_it_is_allocated_to(db, two_pools):
    """The defect, stated as arithmetic: 60 units in transit are 60 units, not 120.

    Both halves are asserted in one test on purpose. "Pool A sees it" alone passes today,
    and "pool B does not" alone could be satisfied by dropping in-transit supply entirely -
    which would hide a container that IS coming. The claim is that the quantity is
    attributed exactly once across the pools, so the sum over the two pools is the
    assertion that cannot be satisfied the wrong way.
    """
    product = two_pools["product"]
    arrival = _today() + timedelta(days=12)
    _po, po_line = _po_with_line(
        db, product, two_pools["bin_a"], 200, _today() + timedelta(days=10)
    )
    ship = _in_transit(db, product, 60, arrival, po_line=po_line)

    svc = CoverageService(db)
    cov_a = svc.coverage_for(product.id, pool_id=two_pools["pool_a"].id)
    cov_b = svc.coverage_for(product.id, pool_id=two_pools["pool_b"].id)

    in_a, in_b = _in_transit_rows(cov_a), _in_transit_rows(cov_b)

    # Pool A owns the allocation, so it carries the container exactly once.
    assert [r.event.ref for r in in_a] == [ship.shipment_number]
    assert [r.event.qty for r in in_a] == [60.0]
    # Pool B has no claim on it at all. Today it gets the same 60 units for free.
    assert in_b == [], f"pool B counted a container bound for pool A: {in_b}"
    # The invariant behind both: the quantity exists once across the whole business.
    assert sum(r.event.qty for r in in_a + in_b) == 60.0
    # And the balances the two screens show, so a change that breaks the attribution
    # while keeping the row counts right still fails here. 60, not 260: the 200 on the
    # purchase order is ORDERED, not incoming, so it is reported beside the balance and
    # never inside it.
    assert cov_a.timeline.closing_balance == 60
    assert cov_b.timeline.closing_balance == 0
    assert cov_a.qty_ordered_not_incoming == 200
    assert cov_b.qty_ordered_not_incoming == 0


def test_attribution_follows_the_allocation_rather_than_favouring_one_pool(db, two_pools):
    """The mirror direction, so "pool A wins" cannot pass for a fix.

    Same shape as above with the PO line in pool B's bin instead: the container has to
    follow the data it is allocated against, not the pool that happens to be asked first
    or the pool whose code sorts lower.
    """
    product = two_pools["product"]
    _po, po_line = _po_with_line(
        db, product, two_pools["bin_b"], 200, _today() + timedelta(days=10)
    )
    ship = _in_transit(db, product, 45, _today() + timedelta(days=12), po_line=po_line)

    svc = CoverageService(db)
    cov_a = svc.coverage_for(product.id, pool_id=two_pools["pool_a"].id)
    cov_b = svc.coverage_for(product.id, pool_id=two_pools["pool_b"].id)

    assert [r.event.ref for r in _in_transit_rows(cov_b)] == [ship.shipment_number]
    assert _in_transit_rows(cov_a) == []
    assert cov_a.timeline.closing_balance == 0
    assert cov_b.timeline.closing_balance == 45
    # The purchase order follows the same allocation, and is reported, not counted.
    assert cov_a.qty_ordered_not_incoming == 0
    assert cov_b.qty_ordered_not_incoming == 200


# =========================================================================== #
# b. no allocation, no destination: excluded everywhere, and SAID so
# =========================================================================== #

def test_an_unallocated_container_is_excluded_from_every_pool_and_reported(db, two_pools):
    """A container nobody can place is not cover for everybody.

    Adding it to every pool is the current behaviour and it is the worst of the three
    options: it inflates every pool at once. Excluding it silently would be the second
    worst, because supply that is genuinely on the water would disappear from the plan with
    nothing to show a person why. So it is excluded from the balance AND surfaced as a
    quantity a human can chase the allocation for.
    """
    product = two_pools["product"]
    _in_transit(db, product, 60, _today() + timedelta(days=12))  # no spo_allocations row

    svc = CoverageService(db)
    cov_a = svc.coverage_for(product.id, pool_id=two_pools["pool_a"].id)
    cov_b = svc.coverage_for(product.id, pool_id=two_pools["pool_b"].id)

    assert _in_transit_rows(cov_a) == []
    assert _in_transit_rows(cov_b) == []
    assert cov_a.timeline.closing_balance == 0
    assert cov_b.timeline.closing_balance == 0

    # Visible, not merely absent. The attribute does not exist yet, hence the getattr:
    # a red on a missing field is the point, not an AttributeError in the test harness.
    assert getattr(cov_a, "unattributed_in_transit_qty", None) == 60


def test_an_allocated_container_leaves_nothing_unattributed(db, two_pools):
    """The other side of the same field: a fully allocated container is not "set aside".

    Without this, an implementation that reports every in-transit quantity as unattributed
    would satisfy the test above while telling a planner that supply they can see on the
    timeline is also missing a destination.
    """
    product = two_pools["product"]
    _po, po_line = _po_with_line(
        db, product, two_pools["bin_a"], 200, _today() + timedelta(days=10)
    )
    _in_transit(db, product, 60, _today() + timedelta(days=12), po_line=po_line)

    cov_a = CoverageService(db).coverage_for(product.id, pool_id=two_pools["pool_a"].id)

    assert getattr(cov_a, "unattributed_in_transit_qty", None) == 0


# =========================================================================== #
# c. the split the existing suite relies on survives the fix
# =========================================================================== #

def test_the_order_stays_off_the_timeline_the_shipment_against_it_stays_on(db, two_pools):
    """The two halves are still distinguished, but by which side of the balance they sit on.

    They used to be two supply stages summed into one balance, on the reasoning that an
    order can still be cancelled while a loaded container cannot. The live book showed that
    reasoning was buying the wrong thing: 9 open PO lines against 842 allocations, so the
    balance was made almost entirely of the half that had not shipped. An order is not stock
    on the water. It is reported, so a buyer looking at a shortfall can see somebody already
    acted on it, and it changes no number the plan computes.
    """
    product = two_pools["product"]
    _po, po_line = _po_with_line(
        db, product, two_pools["bin_a"], 200, _today() + timedelta(days=10)
    )
    _in_transit(db, product, 60, _today() + timedelta(days=12), po_line=po_line)

    cov = CoverageService(db).coverage_for(product.id, pool_id=two_pools["pool_a"].id)

    assert [r.event.supply_stage for r in cov.timeline.rows] == [None, SUPPLY_IN_TRANSIT]
    assert [r.balance for r in cov.timeline.rows] == [0, 60]
    assert cov.qty_ordered_not_incoming == 200
    assert not any(
        r.event.supply_stage == SUPPLY_ON_ORDER for r in cov.timeline.rows
    ), "a purchase order must produce no timeline event at all"


def test_a_received_shipment_is_not_in_transit_supply(db, two_pools):
    """GUARD: a received container is on hand, and counting it here counts it twice.

    Seeded with a real allocation so that the exclusion has to come from the shipment
    status rather than from the destination chain being unable to place it.

    The status is ``fully_received`` rather than ``received`` because the column's CHECK
    constraint does not admit the latter: `procurement_service` normalises it before any
    write, so a `received` row cannot exist to be tested against.
    """
    product = two_pools["product"]
    _po, po_line = _po_with_line(
        db, product, two_pools["bin_a"], 200, _today() + timedelta(days=10)
    )
    _in_transit(
        db, product, 60, _today() - timedelta(days=2), po_line=po_line,
        status="fully_received",
    )

    cov = CoverageService(db).coverage_for(product.id, pool_id=two_pools["pool_a"].id)

    assert _in_transit_rows(cov) == []
    # Zero, not 200: the received container is on hand (counted in the opening balance once
    # its GRN lands) and the purchase order behind it was never part of the balance.
    assert cov.timeline.closing_balance == 0
