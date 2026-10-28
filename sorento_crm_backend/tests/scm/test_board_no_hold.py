"""BOARD-NO-HOLD slice 2 (+ BORROW-NO-HOLD, 28 Oct): a confirmed Reserve OR Borrow holds no stock.

Owner, 27 Oct 2026: "board decision don't hold stock, board decision is just a planning
choice". Reserve = `ALLOC_RESERVE_SOURCES` (own / brw / group_take): a plan only, which
keeps one job (card Q1 a), the line may draw the location its plan names AT ITS OWN DATE
(`Hold(route=True)` in the walk, slice 1). Borrow = `ALLOC_BORROW_SOURCES` is the same since
BORROW-NO-HOLD (owner 28 Oct). `order` (Buy) never held.

Plan: documentation/plans/scm/PLAN-board-no-hold-27oct.md (red-first list 1-11). Written
BEFORE the wiring: `ProjectSupplyService._hold_query` still matches Reserve rows, Stock
Debt `_holds` still returns them as pinned holds, the reorder reduction still deducts them.

Postgres only, every row seeded here under a ZZT marker, in the rolled-back savepoint
`scm_app` gives (the idiom of the other Stock Debt tests; the helpers are theirs). Each
test seeds ONE product, so nothing here depends on what else the database holds.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.models.project_so import (
    ALLOC_SOURCE_BRW,
    ALLOC_SOURCE_GROUP_TAKE,
    ALLOC_SOURCE_OTHER_LOCATION,
    ALLOC_SOURCE_OWN,
    SOLineAllocation,
)
from app.services.scm.supply_assignment import KIND_ON_HAND, SupplyEvent
from tests.scm.conftest import SORENTO_COMPANY_ID, requires_pg
from tests.scm.test_stock_debt_locations import _site_pool
from tests.scm.test_stock_debt_routes import (
    TODAY,
    _demand,
    _product,
    _project_line_for,
    _u,
    _warehouse,
)
from tests.scm.test_stock_debt_stale_pin import _stock

pytestmark = requires_pg

BORROW = ALLOC_SOURCE_OTHER_LOCATION


def _alloc(db, project_line, warehouse, qty, source_type):
    """One CONFIRMED allocation of `source_type` holding/planning `qty` at `warehouse`."""
    row = SOLineAllocation(
        id=_u(),
        company_id=SORENTO_COMPANY_ID,
        so_line_id=project_line.id,
        source_type=source_type,
        warehouse_id=warehouse.id,
        qty=Decimal(str(qty)),
        confirmed_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    return row


def _planned_line(db, product, warehouse, *, qty, days, so_number, source_type,
                  plan_at=None, plan_qty=None):
    """An open order line `days` out, with a confirmed `source_type` allocation at
    `plan_at` (its own bin unless given). Returns `(core_line, project_line)`."""
    _order, core = _demand(
        db, product, warehouse, qty=qty, required_date=TODAY + timedelta(days=days),
        so_number=so_number,
    )
    _pso, project_line = _project_line_for(db, core)
    _alloc(db, project_line, plan_at or warehouse, plan_qty or qty, source_type)
    return core, project_line


def _walk(db, product, span):
    """The Stock Debt VIEW's own walk, one product, over the given bins."""
    from app.services.scm.stock_debt_service import StockDebtService

    result = StockDebtService(db)._assignments(
        [(str(product.id), product.product_code, None)], span, view=True
    )
    return {row.line.so_number: row for row in result[str(product.id)].lines}


def _board_walk(db, product, span):
    """The BOARD / ladder reading of the same walk (`assignments_for`, view=False). Since
    STOCKDEBT-NO-PLAN-REACH (owner 28 Oct 2026) only this path takes a plan as a route; the
    view walks a decided line as if it were undecided."""
    from app.services.scm.stock_debt_service import StockDebtService

    result = StockDebtService(db).assignments_for([str(product.id)], span)
    return {row.line.so_number: row for row in result[str(product.id)].lines}


def _world(db, *, source_type, on_hand=36):
    """CB4702, own-bin shape: `on_hand` at a flagged bin; a LATER order (+60d) confirmed
    `source_type` for 36 there; an EARLIER undecided order (+10d) needing 36."""
    marker = f"ZZTNH{_u()[:6]}".upper()
    bin_ib = _warehouse(db, f"ZZTBRW{_u()[:4]}-IB")
    product = _product(db, f"{marker}-A")
    _stock(db, product, bin_ib, on_hand=on_hand)
    _demand(
        db, product, bin_ib, qty=36, required_date=TODAY + timedelta(days=10),
        so_number=f"{marker}-EARLY",
    )
    core, project_line = _planned_line(
        db, product, bin_ib, qty=36, days=60, so_number=f"{marker}-LATE",
        source_type=source_type,
    )
    db.flush()
    return marker, product, bin_ib, core, project_line


# --------------------------------------------------------------------------- 1, 2


@pytest.mark.parametrize(
    "source_type", [ALLOC_SOURCE_OWN, ALLOC_SOURCE_BRW, ALLOC_SOURCE_GROUP_TAKE]
)
def test_1_a_reserve_is_served_in_date_order_and_never_pins(scm_app, source_type):
    """CB4702: 36 on hand, the later order has a confirmed Reserve of 36 there, the earlier
    undecided order needs 36. The earlier one is covered; the later one is short, and
    neither reads pinned. (Today: later `pinned` 36, earlier short 36.)"""
    _app, db, *_ = scm_app
    marker, product, bin_ib, _core, _pl = _world(db, source_type=source_type)

    rows = _walk(db, product, {str(bin_ib.id): bin_ib})
    early, late = rows[f"{marker}-EARLY"], rows[f"{marker}-LATE"]

    assert early.status == "covered"
    assert early.uncovered == 0
    assert sum(item.qty for item in early.assigned) == pytest.approx(36)
    assert late.status == "short"
    assert late.uncovered == pytest.approx(36)
    assert late.assigned == ()
    assert not any(item.pinned for row in rows.values() for item in row.assigned)


def test_1b_a_reserve_line_that_comes_first_covers_itself_and_is_not_pinned(scm_app):
    """The planned line is the EARLIER one: it draws its bin at its own date and reads
    `covered`, with a take that is not pinned (a plan, not a promise)."""
    _app, db, *_ = scm_app
    marker = f"ZZTNH{_u()[:6]}".upper()
    bin_ib = _warehouse(db, f"ZZTBRW{_u()[:4]}-IB")
    product = _product(db, f"{marker}-A")
    _stock(db, product, bin_ib, on_hand=36)
    _planned_line(
        db, product, bin_ib, qty=36, days=10, so_number=f"{marker}-PLANNED",
        source_type=ALLOC_SOURCE_OWN,
    )

    row = _walk(db, product, {str(bin_ib.id): bin_ib})[f"{marker}-PLANNED"]

    assert row.status == "covered"
    assert row.uncovered == 0
    assert [(item.event.key, item.qty, item.pinned) for item in row.assigned] == [
        (f"on_hand:{bin_ib.id}", 36.0, False)
    ]


def test_2_a_borrow_is_served_in_date_order_and_never_pins(scm_app):
    """BORROW-NO-HOLD AC-BNH-1: the same shape with the later order's allocation
    `other_location` reads like a Reserve: earlier covered, later short, nothing pinned.
    (Today: later `pinned` 36, earlier short 36.)"""
    _app, db, *_ = scm_app
    marker, product, bin_ib, _core, _pl = _world(db, source_type=BORROW)

    rows = _walk(db, product, {str(bin_ib.id): bin_ib})
    early, late = rows[f"{marker}-EARLY"], rows[f"{marker}-LATE"]

    assert early.status == "covered"
    assert early.uncovered == 0
    assert late.status == "short"
    assert late.uncovered == pytest.approx(36)
    assert late.assigned == ()
    assert not any(item.pinned for row in rows.values() for item in row.assigned)


# --------------------------------------------------------------------------- 3, 4, 5


def _key(product, warehouse):
    return (str(product.id), str(warehouse.id))


def test_3_free_stock_ignores_a_reserve_and_a_borrow(scm_app):
    """On hand 40, AutoCount reserved 4. A confirmed Reserve of 10 changes nothing: free 36,
    held 0. Add a Borrow of 20 and nothing changes (BORROW-NO-HOLD AC-BNH-6)."""
    from app.services.project_supply_service import ProjectSupplyService

    _app, db, *_ = scm_app
    marker = f"ZZTNH{_u()[:6]}".upper()
    bin_ib = _warehouse(db, f"ZZTBRW{_u()[:4]}-IB")
    product = _product(db, f"{marker}-A")
    _stock(db, product, bin_ib, on_hand=40, reserved=4)
    _planned_line(db, product, bin_ib, qty=10, days=30, so_number=f"{marker}-R",
                  source_type=ALLOC_SOURCE_OWN)
    key = _key(product, bin_ib)
    supply = ProjectSupplyService(db)

    assert supply.free_stock_by_location([str(product.id)])[key] == Decimal("36")
    assert supply.held_stock_by_location([str(product.id)]).get(key, Decimal("0")) == 0

    _planned_line(db, product, bin_ib, qty=20, days=40, so_number=f"{marker}-B",
                  source_type=BORROW)
    supply = ProjectSupplyService(db)

    assert supply.free_stock_by_location([str(product.id)])[key] == Decimal("36")
    assert supply.held_stock_by_location([str(product.id)]).get(key, Decimal("0")) == 0


def test_4_holds_at_locations_lists_neither_a_reserve_nor_a_borrow(scm_app):
    from app.services.project_supply_service import ProjectSupplyService

    _app, db, *_ = scm_app
    marker = f"ZZTNH{_u()[:6]}".upper()
    bin_ib = _warehouse(db, f"ZZTBRW{_u()[:4]}-IB")
    product = _product(db, f"{marker}-A")
    _stock(db, product, bin_ib, on_hand=40)
    _planned_line(db, product, bin_ib, qty=10, days=30, so_number=f"{marker}-R",
                  source_type=ALLOC_SOURCE_OWN)
    _planned_line(db, product, bin_ib, qty=20, days=40, so_number=f"{marker}-B",
                  source_type=BORROW)

    rows = ProjectSupplyService(db).holds_at_locations(
        [str(product.id)], [str(bin_ib.id)]
    )

    assert rows == []


def test_5_location_stock_free_figure_ignores_a_reserve(scm_app):
    from app.services.scm.location_stock_service import location_stock_for_product

    _app, db, *_ = scm_app
    marker = f"ZZTNH{_u()[:6]}".upper()
    bin_ib = _warehouse(db, f"ZZTBRW{_u()[:4]}-IB")
    product = _product(db, f"{marker}-A")
    _stock(db, product, bin_ib, on_hand=40, reserved=4)
    _planned_line(db, product, bin_ib, qty=10, days=30, so_number=f"{marker}-R",
                  source_type=ALLOC_SOURCE_OWN)

    body = location_stock_for_product(db, str(product.id))
    [row] = [r for r in body["locations"] if r["warehouse_id"] == str(bin_ib.id)]

    assert row["on_hand"] == 40
    assert row["held_by_decisions"] == 0
    assert row["free"] == 36


# --------------------------------------------------------------------------- 6


def _holds(db, product, core_lines, **kwargs):
    from app.services.scm.stock_debt_service import StockDebtService

    return StockDebtService(db)._holds(
        [str(product.id)], {str(line.id) for line in core_lines}, **kwargs
    )


def test_6_stock_debt_hands_a_reserve_and_a_borrow_over_as_routes(scm_app):
    _app, db, *_ = scm_app
    marker = f"ZZTNH{_u()[:6]}".upper()
    bin_ib = _warehouse(db, f"ZZTBRW{_u()[:4]}-IB")
    product = _product(db, f"{marker}-A")
    _stock(db, product, bin_ib, on_hand=100)
    reserve_core, _ = _planned_line(
        db, product, bin_ib, qty=30, days=30, so_number=f"{marker}-R",
        source_type=ALLOC_SOURCE_OWN,
    )
    borrow_core, _ = _planned_line(
        db, product, bin_ib, qty=20, days=40, so_number=f"{marker}-B",
        source_type=BORROW,
    )

    holds = _holds(db, product, [reserve_core, borrow_core])
    by_line = {hold.line_key: hold for hold in holds}

    reserve, borrow = by_line[str(reserve_core.id)], by_line[str(borrow_core.id)]
    assert reserve.route is True
    assert (reserve.kind, reserve.qty, reserve.supply_key) == (
        KIND_ON_HAND, 30.0, f"on_hand:{bin_ib.id}"
    )
    assert reserve.warehouse == bin_ib.warehouse_code
    assert borrow.route is True
    assert (borrow.kind, borrow.qty, borrow.supply_key) == (
        KIND_ON_HAND, 20.0, f"on_hand:{bin_ib.id}"
    )


def test_6b_a_reserve_on_an_in_span_bin_with_no_stock_is_dropped(scm_app):
    """The STALE-PIN rule: a bin the read looked at and found empty covers nobody. With an
    on-hand event for the bin the same Reserve is kept as a route."""
    _app, db, *_ = scm_app
    marker = f"ZZTNH{_u()[:6]}".upper()
    bin_ib = _warehouse(db, f"ZZTBRW{_u()[:4]}-IB")
    product = _product(db, f"{marker}-A")
    core, _ = _planned_line(
        db, product, bin_ib, qty=30, days=30, so_number=f"{marker}-R",
        source_type=ALLOC_SOURCE_OWN,
    )
    span = {str(bin_ib.id)}

    assert _holds(db, product, [core], span=span, supply_rows={}) == []

    event = SupplyEvent(
        key=f"on_hand:{bin_ib.id}", kind=KIND_ON_HAND, warehouse=bin_ib.warehouse_code,
        at=TODAY, qty=30,
    )
    [kept] = _holds(
        db, product, [core], span=span, supply_rows={str(product.id): [event]}
    )
    assert kept.route is True
    assert kept.qty == 30.0


# --------------------------------------------------------------------------- 7


def _pool_world(db):
    """A project bin (group XX) pointed at a site pool holding 36. Returns
    `(marker, product, project_bin, pool)`."""
    marker = f"ZZTNH{_u()[:6]}".upper()
    project_bin = _warehouse(db, f"ZZTBRW{_u()[:4]}-XX")
    pool = _site_pool(db, project_bin)
    product = _product(db, f"{marker}-A")
    _stock(db, product, pool, on_hand=36)
    return marker, product, project_bin, pool


def test_7_a_brw_reserve_draws_the_site_pool_at_its_own_date(scm_app):
    """On the BOARD walk (STOCKDEBT-NO-PLAN-REACH: the view no longer routes). A project line
    planned `brw` at an active site pool with stock reads covered at its date and not pinned; an
    earlier UNDECIDED project line of the same group still cannot draw the pool."""
    _app, db, *_ = scm_app
    marker, product, project_bin, pool = _pool_world(db)
    _demand(
        db, product, project_bin, qty=36, required_date=TODAY + timedelta(days=10),
        so_number=f"{marker}-EARLY",
    )
    _planned_line(
        db, product, project_bin, qty=36, days=60, so_number=f"{marker}-PLANNED",
        source_type=ALLOC_SOURCE_BRW, plan_at=pool,
    )
    span = {str(project_bin.id): project_bin, str(pool.id): pool}

    rows = _board_walk(db, product, span)
    planned, early = rows[f"{marker}-PLANNED"], rows[f"{marker}-EARLY"]

    assert planned.status == "covered"
    assert [(item.event.key, item.qty, item.pinned) for item in planned.assigned] == [
        (f"on_hand:{pool.id}", 36.0, False)
    ]
    assert early.status == "short"
    assert early.uncovered == pytest.approx(36)


def test_7b_a_brw_reserve_on_a_pool_outside_the_span_still_covers_its_line(scm_app):
    """On the BOARD walk (STOCKDEBT-NO-PLAN-REACH: the view no longer routes). Narrowed to the
    project bin alone (`location=`), the pool is outside the span and the plan is honoured off
    the pool's real stock (stand-in, capped at what it holds)."""
    _app, db, *_ = scm_app
    marker, product, project_bin, pool = _pool_world(db)
    _planned_line(
        db, product, project_bin, qty=50, days=30, so_number=f"{marker}-PLANNED",
        source_type=ALLOC_SOURCE_BRW, plan_at=pool, plan_qty=50,
    )

    row = _board_walk(db, product, {str(project_bin.id): project_bin})[f"{marker}-PLANNED"]

    assert row.status == "short"
    assert row.uncovered == pytest.approx(14)
    assert [(item.event.key, item.qty, item.pinned) for item in row.assigned] == [
        (f"on_hand:{pool.id}", 36.0, False)
    ]


# --------------------------------------------------------------------------- 8


def _reduction(db, product):
    from app.services.scm import reorder_run_service as svc

    return svc._project_supply_reduction_map(db, [{"product_id": str(product.id)}])


def _decided_allocation(db, product, warehouse, qty, source_type):
    """The chain the reduction reads: core line, project line, ACTIVE decision, allocation
    (copied from `test_plan_horizon_review_fixes._project_reserve`, with the source
    stated)."""
    from app.models.project_so import SOSupplyDecision

    marker = f"ZZTNH{_u()[:6]}".upper()
    _order, core = _demand(
        db, product, warehouse, qty=qty, required_date=TODAY + timedelta(days=30),
        so_number=f"{marker}-SO",
    )
    pso, project_line = _project_line_for(db, core)
    db.add(
        SOSupplyDecision(
            id=_u(), company_id=SORENTO_COMPANY_ID, project_sales_order_id=pso.id,
            revision_no=1, state="active", line_snapshots=[],
            confirmed_at=datetime.utcnow(),
        )
    )
    db.flush()
    _alloc(db, project_line, warehouse, qty, source_type)


def test_8_the_project_buy_is_lowered_by_both_a_reserve_and_a_borrow(scm_app):
    """BORROW-NO-HOLD AC-BNH-10, map half: the claim map counts every non-Buy allocation
    (Reserve 30, Borrow 20) and feeds the PROJECT Buy only. That retail's net is lowered by
    neither is proven in `test_reorder_plan_oi_need_in_full.py`."""
    _app, db, *_ = scm_app
    marker = f"ZZTNH{_u()[:6]}".upper()
    bin_ib = _warehouse(db, f"ZZTBRW{_u()[:4]}-IB")
    reserve_product = _product(db, f"{marker}-R")
    borrow_product = _product(db, f"{marker}-B")
    _decided_allocation(db, reserve_product, bin_ib, 30, ALLOC_SOURCE_OWN)
    _decided_allocation(db, borrow_product, bin_ib, 20, BORROW)

    assert _reduction(db, reserve_product) == {(str(reserve_product.id), str(bin_ib.id)): 30.0}
    assert _reduction(db, borrow_product) == {(str(borrow_product.id), str(bin_ib.id)): 20.0}


# --------------------------------------------------------------------------- 9


def test_9_the_confirm_floor_names_neither_a_reserve_nor_a_borrow_holder(scm_app):
    """`_check_reserve_against_on_hand` reads `_holds_by_holder`: another order's confirmed
    Reserve is not a holder at the bin any more, so two orders may both confirm a Reserve
    of one pile; a Borrow is not one either (BORROW-NO-HOLD)."""
    from app.services.project_supply_service import ProjectSupplyService

    _app, db, *_ = scm_app
    marker = f"ZZTNH{_u()[:6]}".upper()
    bin_ib = _warehouse(db, f"ZZTBRW{_u()[:4]}-IB")
    product = _product(db, f"{marker}-A")
    _stock(db, product, bin_ib, on_hand=36)
    _planned_line(db, product, bin_ib, qty=36, days=30, so_number=f"{marker}-R",
                  source_type=ALLOC_SOURCE_OWN)
    key = _key(product, bin_ib)

    assert ProjectSupplyService(db)._holds_by_holder(
        [str(product.id)], exclude_line_ids=[]
    ).get(key, []) == []

    _planned_line(db, product, bin_ib, qty=20, days=40, so_number=f"{marker}-B",
                  source_type=BORROW)
    holders = ProjectSupplyService(db)._holds_by_holder(
        [str(product.id)], exclude_line_ids=[]
    ).get(key, [])

    assert holders == []
