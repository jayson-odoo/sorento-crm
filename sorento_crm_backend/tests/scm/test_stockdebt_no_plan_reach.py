"""STOCKDEBT-NO-PLAN-REACH (owner rulings 28 Oct 2026 ~09:00-09:15 MYT).

"I don't want to take from BRW even if the plan says 'Reserve from BRW'", "the one that it
can draw should be faithful to what's mentioned in the Supply tab, be it PO, SPO or on hand",
and the key rule (~09:40): "I need it to be same behaviour as now, except it is independent
of the planning; even if plan says reserve from BRW, it doesn't care, and how it draws is
the same as other lines that don't have a decision".

In the Stock Debt VIEW (`_assignments(view=True)`) a line WITH a board decision (Reserve
own / BRW / group take, Borrow, Buy) draws exactly as the same line WITHOUT one (section 5,
the equivalence). Everything an undecided line reads today is kept: on hand in its group's
pile, OI placement links, the book's S/O on a PO / SPO line, and the received-SPO pin (once
an SPO is received its goods leave supply and the on hand stays with the linked SO).

The board and the ladder (`assignments_for`, view=False) are unchanged: their walk still
takes a plan as a route (owner condition kept from #1919).

Plan: documentation/plans/scm/PLAN-stockdebt-no-plan-reach-28oct.md. Postgres only, every row
seeded here under a ZZT marker in `scm_app`'s rolled-back savepoint.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.models.project_so import (
    ALLOC_SOURCE_BRW,
    ALLOC_SOURCE_GROUP_TAKE,
    ALLOC_SOURCE_ORDER,
    ALLOC_SOURCE_OTHER_LOCATION,
    ALLOC_SOURCE_OWN,
    SOLineAllocation,
)
from app.services.scm.supply_assignment import KIND_ON_HAND, STATUS_SHORT
from tests.scm.conftest import requires_pg
from tests.scm.test_board_no_hold import _planned_line, _walk
from tests.scm.test_stock_debt_locations import _site_pool
from tests.scm.test_stock_debt_routes import (
    TODAY,
    _demand,
    _order_back_link_on_spo,
    _product,
    _project_line_for,
    _spo,
    _u,
    _warehouse,
)
from tests.scm.test_stock_debt_stale_pin import _stock

pytestmark = requires_pg

BORROW = ALLOC_SOURCE_OTHER_LOCATION


def _marker():
    return f"ZZTNR{_u()[:6]}".upper()


def _board_walk(db, product, span):
    """The BOARD / ladder reading of the same walk (`assignments_for`, view=False)."""
    from app.services.scm.stock_debt_service import StockDebtService

    result = StockDebtService(db).assignments_for([str(product.id)], span)
    return {row.line.so_number: row for row in result[str(product.id)].lines}


def _cb4702(db):
    """CB4702 Dec 26, project book: a project bin (-IR) pointed at a site pool (BRW) holding
    477; three open lines at the project bin, none with stock of their own; the last one
    planned "Reserve from BRW" for its 36."""
    marker = _marker()
    project_bin = _warehouse(db, f"ZZTBRW{_u()[:4]}-IR")
    pool = _site_pool(db, project_bin)
    product = _product(db, f"{marker}-CB")
    _stock(db, product, pool, on_hand=477)
    _demand(
        db, product, project_bin, qty=364, required_date=TODAY + timedelta(days=34),
        so_number=f"{marker}-A",
    )
    _demand(
        db, product, project_bin, qty=256, required_date=TODAY + timedelta(days=61),
        so_number=f"{marker}-B",
    )
    _planned_line(
        db, product, project_bin, qty=36, days=61, so_number=f"{marker}-C",
        source_type=ALLOC_SOURCE_BRW, plan_at=pool,
    )
    db.flush()
    return marker, product, project_bin, pool


# --------------------------------------------------------------------------- 1. CB4702


def test_1_cb4702_a_reserve_from_brw_gives_no_reach_in_the_project_book(scm_app):
    """Project book span (the project bin alone, the pool outside it): the planned line
    reads Short 36 like its two neighbours, and nothing is taken from BRW."""
    _app, db, *_ = scm_app
    marker, product, project_bin, _pool = _cb4702(db)

    rows = _walk(db, product, {str(project_bin.id): project_bin})

    planned = rows[f"{marker}-C"]
    assert planned.assigned == ()
    assert planned.status == STATUS_SHORT
    assert planned.uncovered == pytest.approx(36)
    assert sum(row.uncovered for row in rows.values()) == pytest.approx(364 + 256 + 36)


def test_1b_cb4702_the_whole_book_still_keeps_brw_for_its_own_group(scm_app):
    """Whole book (pool in the span): the pool's 477 stays free in the pool's own group and
    the planned project line is still Short 36."""
    _app, db, *_ = scm_app
    marker, product, project_bin, pool = _cb4702(db)

    rows = _walk(db, product, {str(project_bin.id): project_bin, str(pool.id): pool})

    planned = rows[f"{marker}-C"]
    assert planned.assigned == ()
    assert planned.uncovered == pytest.approx(36)


def test_1c_cb4702_the_month_reads_minus_656_and_the_supply_tab_agrees(scm_app):
    """Through the drill itself, project book: the month owes 656 and no demand row's
    Covered by names a source the Supply tab does not list."""
    from app.services.scm.stock_debt_service import StockDebtService
    from app.services.scm.supply_assignment import month_key

    _app, db, *_ = scm_app
    marker, product, project_bin, _pool = _cb4702(db)
    service = StockDebtService(db)
    service._warehouses = lambda group, book="all": {str(project_bin.id): project_bin}

    month = month_key(TODAY + timedelta(days=61))
    cell = service.cell(str(product.id), month, book="project")

    ours = [row for row in cell["demand"] if row["so_number"].startswith(marker)]
    in_month = sum(row["short_qty"] for row in ours)
    assert {row["so_number"]: row["short_qty"] for row in ours}[f"{marker}-C"] == 36
    listed = {row["warehouse_code"] for row in cell["supply"]}
    for row in ours:
        for source in row["assigned_from"]:
            assert source["kind"] != KIND_ON_HAND or source["ref"].removeprefix(
                "On hand "
            ) in listed
    early = TODAY + timedelta(days=34)
    if month_key(early) == month:
        assert in_month == 656
    else:
        assert in_month == 256 + 36


def test_1d_the_board_walk_still_takes_the_reserve_from_brw(scm_app):
    """Owner condition (#1919): the board's own walk is unchanged, its Reserve still routes
    to the pool and covers the planned line."""
    _app, db, *_ = scm_app
    marker, product, project_bin, pool = _cb4702(db)

    rows = _board_walk(db, product, {str(project_bin.id): project_bin, str(pool.id): pool})

    planned = rows[f"{marker}-C"]
    assert planned.uncovered == pytest.approx(0)
    assert [(item.event.key, item.qty) for item in planned.assigned] == [
        (f"on_hand:{pool.id}", 36.0)
    ]


# --------------------------------------------------------------------------- 2. Borrow


def test_2_a_cross_group_borrow_gives_no_reach_in_the_view(scm_app):
    """A Borrow from another group's bin (IB, 36 on hand) does not cover the XX line in the
    view; the IB stock stays IB's."""
    _app, db, *_ = scm_app
    marker = _marker()
    bin_ib = _warehouse(db, f"ZZTBRW{_u()[:4]}-IB")
    bin_xx = _warehouse(db, f"ZZTBRW{_u()[:4]}-XX")
    product = _product(db, f"{marker}-A")
    _stock(db, product, bin_ib, on_hand=36)
    _planned_line(
        db, product, bin_xx, qty=36, days=30, so_number=f"{marker}-BORROWER",
        source_type=BORROW, plan_at=bin_ib,
    )
    span = {str(bin_ib.id): bin_ib, str(bin_xx.id): bin_xx}

    borrower = _walk(db, product, span)[f"{marker}-BORROWER"]
    assert borrower.assigned == ()
    assert borrower.status == STATUS_SHORT

    board = _board_walk(db, product, span)[f"{marker}-BORROWER"]
    assert board.uncovered == pytest.approx(0)


def test_2b_a_plan_at_its_own_bin_still_draws_its_own_bin_in_date_order(scm_app):
    """Guard: the own bin is the line's supply with or without a plan. An undecided earlier
    line is served first, the planned later line takes what is left."""
    _app, db, *_ = scm_app
    marker = _marker()
    bin_ib = _warehouse(db, f"ZZTBRW{_u()[:4]}-IB")
    product = _product(db, f"{marker}-A")
    _stock(db, product, bin_ib, on_hand=50)
    _demand(
        db, product, bin_ib, qty=36, required_date=TODAY + timedelta(days=10),
        so_number=f"{marker}-EARLY",
    )
    _planned_line(
        db, product, bin_ib, qty=36, days=60, so_number=f"{marker}-LATE",
        source_type=ALLOC_SOURCE_BRW,
    )

    rows = _walk(db, product, {str(bin_ib.id): bin_ib})
    assert rows[f"{marker}-EARLY"].uncovered == pytest.approx(0)
    late = rows[f"{marker}-LATE"]
    assert [(item.event.key, item.qty) for item in late.assigned] == [
        (f"on_hand:{bin_ib.id}", 14.0)
    ]
    assert late.uncovered == pytest.approx(22)


# --------------------------------------------------------------------------- 3. OI links


def _linked_spo_world(db, *, auto, received=0, receipt_status="pending"):
    """One bin, an SPO of 50 at it (incoming unless `received`), SO1 placed on it by an OI
    link (`auto` = written by the AutoCount linkage), SO2 due first with no link."""
    marker = _marker()
    warehouse = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    product = _product(db, f"{marker}-A")
    if received:
        _stock(db, product, warehouse, on_hand=received)
    _demand(
        db, product, warehouse, qty=50, required_date=TODAY + timedelta(days=20),
        so_number=f"{marker}-SO2",
    )
    _order, core = _demand(
        db, product, warehouse, qty=50, required_date=TODAY + timedelta(days=40),
        so_number=f"{marker}-SO1",
    )
    project_order, project_line = _project_line_for(db, core)
    arrives = TODAY - timedelta(days=5) if received else TODAY + timedelta(days=15)
    allocation = _spo(
        db, product, warehouse, qty=50, arrives=arrives, received=received,
        receipt_status=receipt_status,
    )
    _inquiry, _row, link = _order_back_link_on_spo(
        db, project_order, project_line, allocation=allocation, qty=50
    )
    link.auto = auto
    db.flush()
    return marker, warehouse, product, allocation


@pytest.mark.parametrize("auto", [True, False])
def test_3_an_oi_link_on_an_incoming_spo_still_pins_its_so(scm_app, auto):
    """Unchanged (owner 09:40, "same behaviour as now"): a placement link on an incoming
    SPO, AutoCount's own copy or hand-made, keeps the SPO with SO1."""
    _app, db, *_ = scm_app
    marker, warehouse, product, allocation = _linked_spo_world(db, auto=auto)

    so1 = _walk(db, product, {str(warehouse.id): warehouse})[f"{marker}-SO1"]
    assert [(item.event.key, item.qty, item.pinned) for item in so1.assigned] == [
        (f"spo:{allocation.id}", 50.0, True)
    ]


# --------------------------------------------------------------------------- 4. received SPO


@pytest.mark.parametrize("auto", [True, False])
def test_4_a_received_spo_stays_with_its_linked_so_and_is_not_supply(scm_app, auto):
    """Owner 09:15, kept rule: received, the SPO leaves supply (no double count with the on
    hand), and the landed on hand stays with SO1 rather than going to SO2 due first."""
    _app, db, *_ = scm_app
    marker, warehouse, product, allocation = _linked_spo_world(
        db, auto=auto, received=50, receipt_status="received"
    )
    from app.services.scm.stock_debt_service import StockDebtService

    service = StockDebtService(db)
    result = service._assignments(
        [(str(product.id), product.product_code, None)],
        {str(warehouse.id): warehouse},
        keep_events=True,
        view=True,
    )[str(product.id)]
    rows = {row.line.so_number: row for row in result.lines}

    assert f"spo:{allocation.id}" not in {event.key for event in result.supply}
    so1, so2 = rows[f"{marker}-SO1"], rows[f"{marker}-SO2"]
    assert [(item.event.key, item.qty, item.pinned) for item in so1.assigned] == [
        (f"on_hand:{warehouse.id}", 50.0, True)
    ]
    assert so2.assigned == ()
    assert so2.uncovered == pytest.approx(50)


# --------------------------------------------------------------------------- 5. equivalence


def _shape(rows, marker):
    """What a reader of the view sees per line, ours only."""
    return {
        so_number: (
            row.status,
            round(row.uncovered, 4),
            tuple(sorted((item.event.key, round(item.qty, 4), item.pinned)
                         for item in row.assigned)),
        )
        for so_number, row in rows.items()
        if so_number.startswith(marker)
    }


@pytest.mark.parametrize(
    "source_type, plan_at",
    [
        (ALLOC_SOURCE_OWN, "own"),
        (ALLOC_SOURCE_BRW, "pool"),
        (ALLOC_SOURCE_BRW, "own"),
        (ALLOC_SOURCE_GROUP_TAKE, "sibling"),
        (BORROW, "other_group"),
        (BORROW, "sibling"),
        (BORROW, "pool"),
        (ALLOC_SOURCE_ORDER, "own"),
    ],
)
@pytest.mark.parametrize("span_kind", ["project", "all"])
def test_5_a_decided_line_draws_exactly_as_the_same_line_undecided(
    scm_app, source_type, plan_at, span_kind
):
    """For every plan shape: the view's answer with the decision == its answer with the
    decision removed, for EVERY line of the product (the decided one and its neighbours)."""
    _app, db, *_ = scm_app
    marker = _marker()
    own = _warehouse(db, f"ZZTBRW{_u()[:4]}-IR")
    sibling = _warehouse(db, f"ZZTBRX{_u()[:4]}-IR")
    other = _warehouse(db, f"ZZTBRW{_u()[:4]}-IB")
    pool = _site_pool(db, own, sibling)
    product = _product(db, f"{marker}-EQ")
    for warehouse, qty in ((own, 20), (sibling, 30), (other, 40), (pool, 477)):
        _stock(db, product, warehouse, on_hand=qty)
    _demand(
        db, product, own, qty=25, required_date=TODAY + timedelta(days=10),
        so_number=f"{marker}-EARLY",
    )
    _demand(
        db, product, other, qty=15, required_date=TODAY + timedelta(days=20),
        so_number=f"{marker}-OTHER",
    )
    target = {"own": own, "sibling": sibling, "other_group": other, "pool": pool}[plan_at]
    _core, project_line = _planned_line(
        db, product, own, qty=36, days=40, so_number=f"{marker}-DECIDED",
        source_type=source_type, plan_at=target,
    )
    span = {str(w.id): w for w in (own, sibling, other)}
    if span_kind == "all":
        span[str(pool.id)] = pool

    decided = _shape(_walk(db, product, span), marker)
    db.query(SOLineAllocation).filter(SOLineAllocation.so_line_id == project_line.id).delete()
    db.flush()
    undecided = _shape(_walk(db, product, span), marker)

    assert decided == undecided
