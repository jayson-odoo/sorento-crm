"""BORROW-NO-HOLD (owner ruling 28 Oct 2026): a confirmed Borrow is a plan, not a stock hold.

UAC: documentation/plans/scm/borrow-no-hold-acceptance-criteria.md (AC-BNH-1..10). Precedent:
BOARD-NO-HOLD made a Reserve planning-only (`test_board_no_hold.py`, whose Borrow halves now
carry AC-BNH-1, 6 and 10 too). Here: the SO402757 shape, cross-group reach, site pool, the
unchanged binders and the unchanged donor-side guards.

Postgres only; every row is seeded here under a ZZT marker inside `scm_app`'s rolled-back
savepoint (helpers are those of the sibling Stock Debt tests). AC-BNH-7 (confirm writes the
allocation rows, transfer proposal and ORDER_BACK row) is not restated: it is proven end to end
by `test_project_supply_service_ladder.py`
(`test_group_borrow_is_offered_not_proposed_and_a_manual_pick_raises_the_order_back` and
neighbours) and stays in the coder's run of those files.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from app.models.project_so import (
    ALLOC_SOURCE_OTHER_LOCATION,
    DECISION_ACTIVE,
    SOLineAllocation,
    SOSupplyDecision,
)
from app.services.scm.supply_assignment import (
    KIND_ON_HAND,
    KIND_SPO,
    STATUS_PINNED,
    STATUS_SHORT,
    DemandLine,
    Hold,
    SupplyEvent,
    assign,
)
from tests.scm.conftest import SORENTO_COMPANY_ID, requires_pg
from tests.scm.test_board_no_hold import _alloc, _planned_line, _walk
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


def _marker():
    return f"ZZTBH{_u()[:6]}".upper()


# --------------------------------------------------------------------------- AC-BNH-2


def test_ac_bnh_2_one_line_with_three_borrows_at_one_bin_reads_covered_and_nothing_pinned(
    scm_app,
):
    """SO402757 shape: the earliest line needs 100, three Borrow rows 42 + 42 + 16 at one bin
    (each naming a later donor line in `donor_impact_snapshot`), bin on hand 787. The
    borrower reads covered by the bin; no row reads `pinned`."""
    _app, db, *_ = scm_app
    marker = _marker()
    bin_ib = _warehouse(db, f"ZZTBRW{_u()[:4]}-IB")
    product = _product(db, f"{marker}-A")
    _stock(db, product, bin_ib, on_hand=787)
    _order, borrower_core = _demand(
        db, product, bin_ib, qty=100, required_date=TODAY + timedelta(days=10),
        so_number=f"{marker}-BORROWER",
    )
    _pso, borrower_line = _project_line_for(db, borrower_core)
    for index, qty in enumerate((42, 42, 16)):
        _order, donor_core = _demand(
            db, product, bin_ib, qty=qty, required_date=TODAY + timedelta(days=60 + index),
            so_number=f"{marker}-DONOR{index}",
        )
        row = _alloc(db, borrower_line, bin_ib, qty, BORROW)
        row.donor_impact_snapshot = {"donor_core_line_id": str(donor_core.id)}
    db.flush()

    rows = _walk(db, product, {str(bin_ib.id): bin_ib})
    borrower = rows[f"{marker}-BORROWER"]

    assert borrower.status == "covered"
    assert borrower.uncovered == 0
    assert sum(item.qty for item in borrower.assigned) == pytest.approx(100)
    assert not any(item.pinned for row in rows.values() for item in row.assigned)
    assert all(row.status != STATUS_PINNED for row in rows.values())


# --------------------------------------------------------------------------- AC-BNH-3


def test_ac_bnh_3_a_cross_group_borrow_still_reaches_its_bin_at_its_own_date(scm_app):
    """The borrowing line sits at a bin of another group (-XX) and its Borrow names the IB
    bin (36 on hand). It draws the bin at its own date and is not pinned; an undecided XX
    line due earlier still cannot draw the IB bin."""
    _app, db, *_ = scm_app
    marker = _marker()
    bin_ib = _warehouse(db, f"ZZTBRW{_u()[:4]}-IB")
    bin_xx = _warehouse(db, f"ZZTBRW{_u()[:4]}-XX")
    product = _product(db, f"{marker}-A")
    _stock(db, product, bin_ib, on_hand=36)
    _demand(
        db, product, bin_xx, qty=36, required_date=TODAY + timedelta(days=5),
        so_number=f"{marker}-OPEN",
    )
    _planned_line(
        db, product, bin_xx, qty=36, days=30, so_number=f"{marker}-BORROWER",
        source_type=BORROW, plan_at=bin_ib,
    )

    rows = _walk(db, product, {str(bin_ib.id): bin_ib, str(bin_xx.id): bin_xx})
    borrower, undecided = rows[f"{marker}-BORROWER"], rows[f"{marker}-OPEN"]

    assert borrower.status == "covered"
    assert [(item.event.key, item.qty, item.pinned) for item in borrower.assigned] == [
        (f"on_hand:{bin_ib.id}", 36.0, False)
    ]
    assert undecided.assigned == ()
    assert undecided.status == STATUS_SHORT


# --------------------------------------------------------------------------- AC-BNH-4


def test_ac_bnh_4_a_borrow_at_a_site_pool_draws_it_at_its_own_date(scm_app):
    """A project line's Borrow names the site pool (36). A dealer line on the pool due
    first (30) is served first; the borrower takes the 6 left, short 30, never pinned."""
    _app, db, *_ = scm_app
    marker = _marker()
    project_bin = _warehouse(db, f"ZZTBRW{_u()[:4]}-XX")
    pool = _site_pool(db, project_bin)
    product = _product(db, f"{marker}-A")
    _stock(db, product, pool, on_hand=36)
    _demand(
        db, product, pool, qty=30, required_date=TODAY + timedelta(days=5),
        so_number=f"{marker}-DEALER",
    )
    _planned_line(
        db, product, project_bin, qty=36, days=60, so_number=f"{marker}-BORROWER",
        source_type=BORROW, plan_at=pool,
    )

    rows = _walk(db, product, {str(project_bin.id): project_bin, str(pool.id): pool})
    dealer, borrower = rows[f"{marker}-DEALER"], rows[f"{marker}-BORROWER"]

    assert dealer.status == "covered"
    assert sum(item.qty for item in dealer.assigned) == pytest.approx(30)
    assert [(item.qty, item.pinned) for item in borrower.assigned] == [(6.0, False)]
    assert borrower.status == STATUS_SHORT
    assert borrower.uncovered == pytest.approx(30)


# --------------------------------------------------------------------------- AC-BNH-5

AS_OF = date(2026, 10, 28)


def test_ac_bnh_5_a_pinned_spo_placement_still_binds_first_at_any_date():
    """Guard (pure walk, green before and after): a placement-style pinned hold on an SPO
    (what an OI placement, incl. a step-3 Borrow's ORDER_BACK link, becomes) beats a line
    due earlier."""
    spo = SupplyEvent(
        key="spo:1", kind=KIND_SPO, warehouse="BRW-IB", at=AS_OF + timedelta(days=30),
        qty=10, ref="SPO 1",
    )

    def line(key, so, due):
        return DemandLine(
            key=key, so_number=so, line_no=1, warehouse="BRW-IB", agent_code="A",
            required_date=AS_OF + timedelta(days=due), open_qty=10,
        )

    result = assign(
        "P", as_of=AS_OF, tba_from=date(2029, 1, 1), lead_days=90, supply=[spo],
        demand=[line("early", "SO1", 40), line("late", "SO2", 60)],
        pinned=[Hold(line_key="late", supply_key="spo:1", qty=10, kind=KIND_SPO,
                     warehouse="BRW-IB")],
        overdue_grace_days=0, overdue_dead_days=0,
    )
    rows = {row.line.key: row for row in result.lines}

    assert rows["late"].assigned[0].pinned is True
    assert rows["early"].assigned == ()
    assert rows["early"].status == STATUS_SHORT


def test_ac_bnh_5_a_stock_pin_still_binds_first_but_a_borrow_route_does_not():
    """Guard + contrast (pure walk): `Hold(route=False)` (landed goods, book S/O pin) binds
    first; the same hold as a route is date-ordered. Proves the walk distinction the
    Borrow now relies on."""
    bin_event = SupplyEvent(key="on_hand:b", kind=KIND_ON_HAND, warehouse="BRW-IB",
                            at=AS_OF, qty=36)

    def demand():
        return [
            DemandLine(key="early", so_number="SO1", line_no=1, warehouse="BRW-IB",
                       agent_code="A", required_date=AS_OF + timedelta(days=10), open_qty=36),
            DemandLine(key="late", so_number="SO2", line_no=1, warehouse="BRW-IB",
                       agent_code="A", required_date=AS_OF + timedelta(days=60), open_qty=36),
        ]

    def run(route):
        hold = Hold(line_key="late", supply_key="on_hand:b", qty=36, kind=KIND_ON_HAND,
                    warehouse="BRW-IB", route=route)
        out = assign("P", as_of=AS_OF, tba_from=date(2029, 1, 1), lead_days=90,
                     supply=[bin_event], demand=demand(), pinned=[hold],
                     overdue_grace_days=0, overdue_dead_days=0)
        return {row.line.key: row for row in out.lines}

    pinned = run(False)
    assert pinned["late"].status == STATUS_PINNED
    assert pinned["early"].status == STATUS_SHORT
    routed = run(True)
    assert routed["early"].status == "covered"
    assert routed["late"].status == STATUS_SHORT


# --------------------------------------------------------------------------- AC-BNH-6


def test_ac_bnh_6_location_stock_and_the_hold_query_ignore_a_borrow(scm_app):
    """On hand 40, AutoCount reserved 4, a Borrow of 20: location stock reads free 36 and
    held 0; the shared hold predicate (`_hold_query`, which the Allocation panel and the
    confirm floor read) returns no row."""
    from app.services.project_supply_service import ProjectSupplyService
    from app.services.scm.location_stock_service import location_stock_for_product

    _app, db, *_ = scm_app
    marker = _marker()
    bin_ib = _warehouse(db, f"ZZTBRW{_u()[:4]}-IB")
    product = _product(db, f"{marker}-A")
    _stock(db, product, bin_ib, on_hand=40, reserved=4)
    _planned_line(db, product, bin_ib, qty=20, days=40, so_number=f"{marker}-B",
                  source_type=BORROW)

    body = location_stock_for_product(db, str(product.id))
    [row] = [r for r in body["locations"] if r["warehouse_id"] == str(bin_ib.id)]
    assert row["on_hand"] == 40
    assert row["held_by_decisions"] == 0
    assert row["free"] == 36
    assert ProjectSupplyService(db)._hold_query(
        [str(product.id)], exclude_line_ids=None
    ).count() == 0


# --------------------------------------------------------------------------- AC-BNH-8


def test_ac_bnh_8_a_donor_lines_active_borrows_are_still_netted_for_the_second_confirm(
    scm_app,
):
    """Guard (green before and after): `_group_borrow_held_qty` still sums the ACTIVE
    Borrow rows that name one donor line, so a second Borrow beyond open qty less those is
    refused (the refusal itself is `test_a_second_confirmation_cannot_borrow_what_an_
    earlier_one_already_holds`)."""
    from app.services.project_supply_service import ProjectSupplyService

    _app, db, *_ = scm_app
    marker = _marker()
    bin_ib = _warehouse(db, f"ZZTBRW{_u()[:4]}-IB")
    product = _product(db, f"{marker}-A")
    _stock(db, product, bin_ib, on_hand=100)
    _order, donor_core = _demand(
        db, product, bin_ib, qty=90, required_date=TODAY + timedelta(days=60),
        so_number=f"{marker}-DONOR",
    )
    lines = []
    for index, qty in enumerate((42, 16)):
        _order, core = _demand(
            db, product, bin_ib, qty=qty, required_date=TODAY + timedelta(days=10),
            so_number=f"{marker}-B{index}",
        )
        _pso, project_line = _project_line_for(db, core)
        row = _alloc(db, project_line, bin_ib, qty, BORROW)
        row.donor_impact_snapshot = {"donor_core_line_id": str(donor_core.id)}
        lines.append(project_line)
    db.flush()
    supply = ProjectSupplyService(db)

    assert supply._group_borrow_held_qty(str(donor_core.id)) == Decimal("58")
    assert supply._group_borrow_held_qty(
        str(donor_core.id), exclude_line_ids={str(lines[0].id)}
    ) == Decimal("16")


# --------------------------------------------------------------------------- AC-BNH-9


def test_ac_bnh_9_the_donor_cell_still_lists_what_was_lent(scm_app):
    """Guard (green before and after): the board's `_lent_from` reads the active decision's
    frozen Borrow component and names the borrower ("71 lent to SO..")."""
    from app.services.project_fulfilment_board_service import FulfilmentBoardService

    _app, db, *_ = scm_app
    marker = _marker()
    bin_ib = _warehouse(db, f"ZZTBRW{_u()[:4]}-IB")
    product = _product(db, f"{marker}-A")
    _order, donor_core = _demand(
        db, product, bin_ib, qty=100, required_date=TODAY + timedelta(days=60),
        so_number=f"{marker}-DONOR",
    )
    _order, borrower_core = _demand(
        db, product, bin_ib, qty=71, required_date=TODAY + timedelta(days=10),
        so_number=f"{marker}-BORROWER",
    )
    pso, _project_line = _project_line_for(db, borrower_core)
    db.add(
        SOSupplyDecision(
            id=_u(), company_id=SORENTO_COMPANY_ID, project_sales_order_id=pso.id,
            revision_no=1, state=DECISION_ACTIVE, confirmed_at=datetime.utcnow(),
            line_snapshots=[
                {
                    "line_no": 1,
                    "components": [
                        {"kind": "borrow", "qty": "71",
                         "donor_core_line_id": str(donor_core.id)}
                    ],
                }
            ],
        )
    )
    db.flush()

    lent = FulfilmentBoardService(db)._lent_from([str(donor_core.id)])

    assert [(row["qty"], row["line_no"]) for row in lent[str(donor_core.id)]] == [("71", 1)]
