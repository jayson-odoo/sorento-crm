"""DEFECT 2: ``availability`` reports a location's OWN stock as borrowed.

``CoverageService.availability`` buckets stock into own / pool / other, and the pool bucket
now wins whenever the requested bin IS the pool. That is right for the pool-addressed
payload, which has no particular bin to call "own" - but ``availability`` is SHARED, and
``resolve_line`` is its other caller.

A location with no ``pool_warehouse_id`` is its own pool (the no-suffix case). For a demand
line in such a location, the stock sitting in that very bin is the line's OWN stock. Calling
it ``brw`` says it was borrowed from a shared pool when nothing was borrowed, and
``resolve_sources`` persists that string into ``so_line_allocations.source_type`` - so the
wrong word does not stay on a screen, it becomes a record of a transfer that never happened.

Two callers, two truths, one helper. That is the shape of the defect, so the tests are
written against the CALLERS rather than against ``availability(own_warehouse_id=X,
pool_id=X)`` directly: with those exact arguments the pool-scoped payload wants ``pool`` and
a self-pool demand line wants ``own``, so no assertion on that single call can hold for
both. The distinguishing input is whether a SPECIFIC bin was asked about at all.

Test-first, and the last group is a GUARD: the pool-scoped payload's contract
(``availability.own == 0``, the pool bin's stock under ``availability.pool``) is pinned here
so the fix cannot swing back and break the endpoint that
``test_coverage_routes.py::test_demand_of_67_against_a_pool_holding_4397_answers_use_stock_not_a_buy``
asserts on the wire.

Seeding is this file's own, under the ``ZZT`` marker, inside a rolled-back transaction.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest

from app.models.inventory import Warehouse
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.scm.coverage_service import CoverageService
from app.services.scm.coverage_timeline import SOURCE_ORDER, SOURCE_OWN, SOURCE_POOL
from app.services.sla_service import MALAYSIA_TZ, to_naive_datetime
from tests._pg_fixture import pg_session, unique_code
from tests.scm.test_coverage_service import _so_line, _stock


def _u() -> str:
    return str(uuid.uuid4())


def _today() -> date:
    return to_naive_datetime(datetime.now(MALAYSIA_TZ)).date()


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


@pytest.fixture()
def chain(db):
    """A pool with one member bin, plus a LONE location that points at no pool.

    The lone location is the no-suffix case and the whole subject of this file: it is its
    own pool, so ``own_warehouse_id`` and ``pool_id`` collapse to the same value and the
    bucketing has to decide which of the two labels the stock deserves.
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
    pool = Warehouse(
        id=_u(), warehouse_code=unique_code("POOL"), warehouse_name="pool", is_active=True
    )
    db.add_all([product, pool])
    db.flush()

    bin_a = Warehouse(
        id=_u(), warehouse_code=unique_code("BINA"), warehouse_name="bin a",
        is_active=True, pool_warehouse_id=pool.id,
    )
    # No pool pointer at all: this location IS its own pool.
    lone = Warehouse(
        id=_u(), warehouse_code=unique_code("LONE"), warehouse_name="lone site",
        is_active=True,
    )
    pool.pool_warehouse_id = pool.id  # a pool is its own pool
    db.add_all([bin_a, lone])
    db.flush()
    return {"product": product, "pool": pool, "bin_a": bin_a, "lone": lone}


# =========================================================================== #
# a. a location that is its own pool owns its stock
# =========================================================================== #

def test_a_lone_locations_own_stock_resolves_as_own_not_as_a_borrow(db, chain):
    """Nothing was borrowed, so nothing may be recorded as borrowed.

    ``resolve_sources`` writes this string into ``so_line_allocations.source_type``, which is
    what a person later reads to answer "where did these units come from". ``brw`` on a site
    that has no shared pool describes a transfer from a pool that does not exist, and the
    record is indistinguishable from a real one.
    """
    _stock(db, chain["product"], chain["lone"], 50)

    allocs = CoverageService(db).resolve_line(
        chain["product"].id, warehouse_id=chain["lone"].id, qty=30
    )

    assert [(a.source_type, a.qty) for a in allocs] == [(SOURCE_OWN, 30)]
    assert [a for a in allocs if a.source_type == SOURCE_POOL] == []
    # The exact string, because it is persisted rather than displayed.
    assert allocs[0].source_type == "own"


def test_a_lone_location_short_of_its_own_stock_buys_the_remainder(db, chain):
    """The remainder is a purchase, not a borrow from itself.

    Splitting 50 own + 50 order also proves the own bucket is a real quantity rather than a
    relabelling of whatever the resolver happened to pick first.
    """
    _stock(db, chain["product"], chain["lone"], 50)

    allocs = CoverageService(db).resolve_line(
        chain["product"].id, warehouse_id=chain["lone"].id, qty=100
    )

    assert [(a.source_type, a.qty) for a in allocs] == [(SOURCE_OWN, 50), (SOURCE_ORDER, 50)]


def test_a_demand_line_sitting_in_the_pool_bin_owns_that_stock(db, chain):
    """Same rule where the self-pool pointer is explicit rather than absent.

    A pool row whose ``pool_warehouse_id`` is itself is the same situation as no pointer at
    all, and a demand line raised against the pool bin is standing in the stock it is asking
    about. Reporting that as borrowed would make the pool borrow from itself.
    """
    _stock(db, chain["product"], chain["pool"], 500)

    allocs = CoverageService(db).resolve_line(
        chain["product"].id, warehouse_id=chain["pool"].id, qty=100
    )

    assert [(a.source_type, a.qty) for a in allocs] == [(SOURCE_OWN, 100)]


# =========================================================================== #
# b. a bin that DOES point at a pool: unchanged, cheapest source first
# =========================================================================== #

def test_a_bin_pointing_at_a_pool_spends_its_own_stock_before_borrowing(db, chain):
    """GUARD, expected green before and after: this is the case ``brw`` exists for.

    Own bin first, then the shared pool, because the pool is the expensive source (it is
    contested by every other bin at the site) and taking from it first would strand a bin's
    own reserved stock behind a claim nobody needs to make.
    """
    _stock(db, chain["product"], chain["bin_a"], 20)
    _stock(db, chain["product"], chain["pool"], 500)

    allocs = CoverageService(db).resolve_line(
        chain["product"].id, warehouse_id=chain["bin_a"].id, qty=100
    )

    assert [(a.source_type, a.qty) for a in allocs] == [(SOURCE_OWN, 20), (SOURCE_POOL, 80)]
    borrowed = next(a for a in allocs if a.source_type == SOURCE_POOL)
    assert borrowed.location == chain["pool"].warehouse_code
    assert borrowed.needs_claim is False


# =========================================================================== #
# c. the pool-scoped payload's contract, pinned
# =========================================================================== #

def test_the_pool_scoped_payload_keeps_own_zero_and_puts_pool_stock_under_pool(db, chain):
    """GUARD, expected green before and after: SRTWT7408 on the wire.

    ``coverage_for`` is addressed by product plus pool and has no particular bin to call
    "own", so its ``availability.own`` is 0 by definition and the pool bin's 4,397 belong
    under ``availability.pool`` - which is exactly what ``test_coverage_routes`` asserts the
    endpoint returns. Fixing the resolve_line half must not drag this payload with it: if
    the 4,397 moved into ``own``, the answer "use the pool" would lose the word "pool" and
    the frontend panel that reads ``availability.pool`` would go blank on the one case the
    module was built for.
    """
    _stock(db, chain["product"], chain["pool"], 4397)
    _so_line(db, chain["product"], chain["bin_a"], 67, _today() + timedelta(days=10))

    cov = CoverageService(db).coverage_for(chain["product"].id, pool_id=chain["pool"].id)

    assert cov.availability.own == 0
    assert cov.availability.pool == 4397
    assert cov.availability.pool_location == chain["pool"].warehouse_code
    assert [(a.source_type, a.qty) for a in cov.allocations] == [(SOURCE_POOL, 67)]
    assert cov.buy_qty == 0
    assert cov.use_stock is True


def test_a_pool_scoped_payload_for_a_lone_location_still_reports_it_as_the_pool(db, chain):
    """GUARD: the lone location addressed AS a pool is a pool, not a bin.

    The same warehouse is "own" to a demand line standing in it and "the pool" to a
    pool-addressed report, and both readings are correct because the question differs. This
    pins the second reading so the fix cannot be implemented by deciding the warehouse is
    one thing forever.
    """
    _stock(db, chain["product"], chain["lone"], 120)

    cov = CoverageService(db).coverage_for(chain["product"].id, pool_id=chain["lone"].id)

    assert cov.availability.own == 0
    assert cov.availability.pool == 120
    assert cov.availability.pool_location == chain["lone"].warehouse_code
