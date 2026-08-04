"""The Summary Order Report's dated shortfall must be the SAME engine the coverage panel uses.

AC-C2.1 puts a shortfall on every row of the report, and the contract is explicit that it is
the dated Coverage Timeline figure, not `on hand + on order - demand`. The report covers
thousands of products, so it cannot call `coverage_for` once per product (three queries each).
`network_positions` batches the event reads and then runs the SAME `build_timeline` per product
over in-memory events.

The property under test is therefore AGREEMENT, not merely "a number comes back". If the
batched path ever grows its own arithmetic, a report row and the coverage panel for the same
product state different shortfalls on the same screen, which is the one class of disagreement
that ends trust in a planning tool. Every test here pins the batched figure against something
independent: the per-pool service, or a hand-computed balance.

The second property is scope. `coverage_for` nets over ONE pool; this nets over every location
that counts toward availability, because a purchase order is raised once for the company rather
than once per pool. A test with TWO pools is what makes the difference visible: the network
shortfall is the shortfall of the pools COMBINED, which is not the sum of their separate
shortfalls when one pool's surplus covers another's gap.

Postgres, marker-prefixed seeding of its own chain, inside `pg_session`'s rolled-back
transaction. Nothing borrowed with `LIMIT 1`: CI's database has no products at all.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest

from app.models.inventory import Stock, Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.scm.coverage_service import CoverageService
from app.services.sla_service import MALAYSIA_TZ, to_naive_datetime
from tests._pg_fixture import pg_session, unique_code

MARKER = "ZZTNET"


def _u() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:8]}".upper()


def _today() -> date:
    """The service's own notion of today: Malaysia wall-clock, not the server's zone."""
    return to_naive_datetime(datetime.now(MALAYSIA_TZ)).date()


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


@pytest.fixture()
def two_pools(db):
    """Two products across TWO independent pools, each pool with one member bin.

    Two pools because a network figure that is secretly one pool's figure passes every
    single-pool test. Two products because a batched reader that returns the first product's
    events for every key also passes every single-product test.
    """
    cat = ProductCategory(
        id=_u(), category_code=_code("CAT")[:40], category_name=_code("cat")
    )
    uom = UnitOfMeasure(id=_u(), uom_name=_code("uom"), uom_code=_code("U")[:20])
    db.add_all([cat, uom])
    db.flush()

    p1 = Product(
        id=_u(), product_code=_code("SKU1"), product_name="wall hung wc",
        category_id=cat.id, base_uom_id=uom.id, list_price=0,
        is_active=True, is_discontinued=False,
    )
    p2 = Product(
        id=_u(), product_code=_code("SKU2"), product_name="basin mixer",
        category_id=cat.id, base_uom_id=uom.id, list_price=0,
        is_active=True, is_discontinued=False,
    )
    pool_a = Warehouse(
        id=_u(), warehouse_code=_code("POOLA")[:30], warehouse_name="pool a",
        is_active=True, counts_as_available=True,
    )
    pool_b = Warehouse(
        id=_u(), warehouse_code=_code("POOLB")[:30], warehouse_name="pool b",
        is_active=True, counts_as_available=True,
    )
    db.add_all([p1, p2, pool_a, pool_b])
    db.flush()

    bin_a = Warehouse(
        id=_u(), warehouse_code=_code("BINA")[:30], warehouse_name="bin a",
        is_active=True, counts_as_available=True, pool_warehouse_id=pool_a.id,
    )
    bin_b = Warehouse(
        id=_u(), warehouse_code=_code("BINB")[:30], warehouse_name="bin b",
        is_active=True, counts_as_available=True, pool_warehouse_id=pool_b.id,
    )
    pool_a.pool_warehouse_id = pool_a.id
    pool_b.pool_warehouse_id = pool_b.id
    db.add_all([bin_a, bin_b])
    db.flush()
    return {
        "p1": p1, "p2": p2,
        "pool_a": pool_a, "bin_a": bin_a,
        "pool_b": pool_b, "bin_b": bin_b,
    }


def _stock(db, product, wh, qty):
    db.add(Stock(id=_u(), product_id=product.id, warehouse_id=wh.id, quantity_on_hand=qty))
    db.flush()


def _demand(db, product, wh, qty, when):
    """One open SO line, dated, in `wh`."""
    cust = Customer(id=_u(), customer_code=_code("C")[:30], customer_name="dealer")
    db.add(cust)
    db.flush()
    so = SalesOrder(
        id=_u(), so_number=_code("SO")[:50], customer_id=cust.id, status="open",
        order_date=_today() - timedelta(days=3),
    )
    db.add(so)
    db.flush()
    db.add(SalesOrderLine(
        id=_u(), sales_order_id=so.id, product_id=product.id, warehouse_id=wh.id,
        qty_ordered=qty, qty_delivered=0, required_date=when, line_status="open",
    ))
    db.flush()
    return so


def _on_order(db, product, wh, qty, when):
    """One placed PO carrying one open line, dated, into `wh`."""
    sup = Supplier(id=_u(), supplier_code=_code("S")[:30], supplier_name="guangdong sw")
    db.add(sup)
    db.flush()
    po = PurchaseOrder(
        id=_u(), po_number=_code("PO")[:50], supplier_id=sup.id, status="active"
    )
    db.add(po)
    db.flush()
    db.add(PurchaseOrderLine(
        id=_u(), purchase_order_id=po.id, product_id=product.id, warehouse_id=wh.id,
        qty_ordered=qty, qty_received=0, expected_date=when, line_status="open",
    ))
    db.flush()
    return po


# --------------------------------------------------------------------------- #
# agreement with the per-pool engine
# --------------------------------------------------------------------------- #


def test_a_single_pool_network_position_matches_the_per_pool_coverage(db, two_pools):
    """With all the stock and demand in ONE pool, the two paths must state one figure.

    This is the agreement test in its simplest form: same product, same events, one pool, so
    a network position and a pool position are answering the same question and any difference
    is the batched path having grown its own arithmetic.
    """
    f = two_pools
    _stock(db, f["p1"], f["bin_a"], 40)
    _demand(db, f["p1"], f["bin_a"], 100, _today() + timedelta(days=10))
    _on_order(db, f["p1"], f["bin_a"], 25, _today() + timedelta(days=30))

    svc = CoverageService(db)
    pool = svc.coverage_for(f["p1"].id, pool_id=f["pool_a"].id)
    net = svc.network_positions([f["p1"].id])[str(f["p1"].id)]

    assert net.shortfall == pool.timeline.peak_deficit
    assert net.closing_balance == pool.timeline.closing_balance
    assert net.on_hand == pool.opening_balance
    assert net.shortfall_at == (pool.timeline.shortfall.at if pool.timeline.shortfall else None)


def test_the_network_nets_pools_together_rather_than_summing_their_shortfalls(db, two_pools):
    """One pool's surplus covers the other's gap, and a purchase order is raised once.

    Pool A is 60 short and pool B holds 100 spare. Summing the pools' separate shortfalls
    says buy 60; netting the network says buy nothing. Both are defensible answers to
    DIFFERENT questions, and the report asks the purchasing one - so this pins the network
    figure and, by asserting the per-pool figure alongside, pins that the two are deliberately
    different rather than accidentally equal.
    """
    f = two_pools
    _stock(db, f["p1"], f["bin_b"], 100)
    _demand(db, f["p1"], f["bin_a"], 60, _today() + timedelta(days=10))

    svc = CoverageService(db)
    pool_a = svc.coverage_for(f["p1"].id, pool_id=f["pool_a"].id)
    net = svc.network_positions([f["p1"].id])[str(f["p1"].id)]

    assert pool_a.timeline.peak_deficit == 60, "pool A on its own is short"
    assert net.on_hand == 100, "the network holds every counting location's stock"
    assert net.shortfall == 0, "the network is covered, so nothing has to be bought"
    assert net.closing_balance == 40


def test_late_supply_does_not_cover_earlier_demand(db, two_pools):
    """The dated property, which is the whole reason the report cannot use a net position.

    On hand 0, demand 50 in ten days, 50 on order in ninety. `on hand + on order - demand` is
    zero and reads as covered. The dated balance goes to -50 on the demand date and stays
    there for eighty days, which is a real stockout somebody has to be told about.
    """
    f = two_pools
    _demand(db, f["p1"], f["bin_a"], 50, _today() + timedelta(days=10))
    _on_order(db, f["p1"], f["bin_a"], 50, _today() + timedelta(days=90))

    net = CoverageService(db).network_positions([f["p1"].id])[str(f["p1"].id)]

    assert net.shortfall == 50, "a dateless net position would report nothing wrong here"
    assert net.shortfall_at == _today() + timedelta(days=10)
    assert net.closing_balance == 0, "it does get covered, eighty days late"


# --------------------------------------------------------------------------- #
# the batch itself
# --------------------------------------------------------------------------- #


def test_each_product_gets_its_own_events(db, two_pools):
    """A batched reader that leaks one product's events into another is the obvious failure.

    Two products with deliberately different positions, asserted in one call, so a grouping
    bug cannot pass by coincidence.
    """
    f = two_pools
    _stock(db, f["p1"], f["bin_a"], 10)
    _demand(db, f["p1"], f["bin_a"], 30, _today() + timedelta(days=5))
    _stock(db, f["p2"], f["bin_a"], 500)

    out = CoverageService(db).network_positions([f["p1"].id, f["p2"].id])

    assert out[str(f["p1"].id)].on_hand == 10
    assert out[str(f["p1"].id)].shortfall == 20
    assert out[str(f["p2"].id)].on_hand == 500
    assert out[str(f["p2"].id)].shortfall == 0


def test_a_product_with_no_events_still_gets_a_position(db, two_pools):
    """Absent from the result would read as "not planned" rather than "nothing is happening".

    The report has a row for the product either way, so the position has to exist for it.
    """
    f = two_pools

    out = CoverageService(db).network_positions([f["p2"].id])

    assert str(f["p2"].id) in out
    pos = out[str(f["p2"].id)]
    assert (pos.on_hand, pos.shortfall, pos.closing_balance) == (0.0, 0.0, 0.0)


def test_an_empty_product_list_reads_nothing(db):
    """No products asked about means no queries run, not every product returned."""
    assert CoverageService(db).network_positions([]) == {}


def test_on_order_and_in_transit_stay_separate(db, two_pools):
    """AC-C2.2: their sum drives the balance, the split is what a person reads.

    Only the on-order half is still negotiable, so a single "incoming" figure would hide the
    one thing a buyer can act on.
    """
    f = two_pools
    _on_order(db, f["p1"], f["bin_a"], 25, _today() + timedelta(days=30))

    pos = CoverageService(db).network_positions([f["p1"].id])[str(f["p1"].id)]

    assert pos.qty_on_order == 25
    assert pos.qty_in_transit == 0
    assert pos.closing_balance == 25


def test_supply_beyond_the_horizon_is_excluded_from_both_the_balance_and_the_split(
    db, two_pools
):
    """A container arriving after the window cannot be the reason a row looks covered.

    The horizon bounds the balance already; the on-order figure beside it has to honour the
    same bound or the row shows incoming stock the shortfall did not count.
    """
    f = two_pools
    _demand(db, f["p1"], f["bin_a"], 40, _today() + timedelta(days=20))
    _on_order(db, f["p1"], f["bin_a"], 40, _today() + timedelta(days=400))

    pos = CoverageService(db).network_positions(
        [f["p1"].id], horizon_months=6
    )[str(f["p1"].id)]

    assert pos.qty_on_order == 0, "supply past the horizon was counted as incoming"
    assert pos.shortfall == 40
