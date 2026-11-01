"""DEALER-PLANNING PR 2, a line at its own pool (UAC R7 to R11; R12 is the front end's).

PR 1 lets a line at a dealer-segment pool be planned. It still nets the line's own demand
against the stock it stands on, so 10 on hand and 10 ordered read a net of zero and propose
Buy 10. PR 2 adds back the line's OWN demand (R7), counts only what the pool's book counted
(R8), takes the dealers' half off retail lines at their own pool (R9), makes the pools one
running net from the walk to the confirm (R10) and stops a Reserve taking stock the book
owes or has reserved (R11).

Written test-first from the UAC. The seed shapes come from the reviewer's scenario files for
PR #2062, ported to assertions. Those assumed the 50 percent share for every line, so a
share is asserted here for PROJECT-class lines only; a retail line at its own pool is R9's,
and reads no share.

Derivations (the UAC gives some figures, the rest follow from its rules):

* the dealers' share is half of what is Available (`available_for_project`), 50 percent;
* a retail line at its own pool takes the whole of Available, and Available there is
  `on_hand - (book - own demand)`, the book being every open, transferable, uncovered line at
  an active pool;
* a project line at BRW keeps the share (UAC R9).

Postgres only (`blank_session`), every test seeds its own chain.
"""
from __future__ import annotations

import os
import random
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.inventory import Warehouse
from app.models.project_so import OrderInquiryRow
from app.schemas.project_supply import ConfirmLine, ConfirmSupplyBody
from app.services.project_fulfilment_board_service import FulfilmentBoardService
from app.services.project_supply_service import ProjectSupplyService, SupplyLinesRefused

from .._pg_fixture import blank_session
from ..test_so_supply_confirmation import _core_line, _project_line, _stock, _uid, _warehouse
from .test_project_supply_service_ladder import REQUIRED_DATE, _components, _seed_line, _world

TODAY = date.today()


def _far(days):
    return TODAY + timedelta(days=days)


# --------------------------------------------------------------------------- seeds


def _pool(db, on_hand=0, product=None, *, segment="dealer", active=True):
    pool = _warehouse(
        db, f"ZZD{_uid()[:6]}", segment=segment, active=active, fulfilment_planning=False,
    )
    db.flush()
    pool.pool_warehouse_id = pool.id
    if product is not None and on_hand:
        _stock(db, product, pool, on_hand=on_hand)
    db.commit()
    return pool


def _project_bin(db, pool):
    own = _warehouse(
        db, f"ZZP{_uid()[:6]}-BB", segment="project", pool_warehouse_id=pool.id,
        fulfilment_planning=True,
    )
    db.commit()
    return own


def _line(db, world, where, qty, *, klass="project", line_no=10, when=REQUIRED_DATE):
    company_id, _actor, project, product = world
    order, line, core_so, core_line = _seed_line(
        db, company_id, project, product, where, qty_ordered=str(qty), line_no=line_no,
        required_date=when,
    )
    core_so.demand_class = klass
    db.commit()
    return order, line, core_so, core_line


def _totals(components):
    return {
        kind: sum(Decimal(str(c["qty"])) for c in components if c["kind"] == kind)
        for kind in {c["kind"] for c in components}
    }


def _sheet(db, order):
    return _totals(_components(ProjectSupplyService(db).proposal_for(order)))


def _board(db, *cores):
    return FulfilmentBoardService(db).build(
        [core.so_number for core in cores], granularity="week", as_of=TODAY,
    )


def _board_row(board, core):
    return next(
        row
        for cell in board["cells"]
        for row in cell["contributions"]
        if row["so_number"] == core.so_number
    )


def _sources(row):
    return _totals(row["sources"])


def _short(service):
    return sum(
        (entry["short"] for entries in service._stock_short.values() for entry in entries),
        Decimal("0"),
    )


# --------------------------------------------------------------------------- R7


@pytest.mark.parametrize(
    "klass, expected",
    [
        ("project", {"reserve": Decimal("10")}),
        ("retail", {"reserve": Decimal("10")}),
    ],
)
def test_r7_a_line_does_not_net_its_own_demand_against_its_own_pool(klass, expected):
    """20 on hand, 10 ordered, nobody else. Available is 20, so the share of 20 is 10 for a
    project line and the whole 10 is free for a retail one: Reserve 10 either way."""
    with blank_session() as db:
        world = _world(db)
        pool = _pool(db, 20, world[3])
        order, _l, _so, _c = _line(db, world, pool, 10, klass=klass)

        got = _sheet(db, order)

    assert got == expected


def test_r7_every_other_lines_demand_at_the_pool_stays_netted():
    """Retail, 15 on hand, 10 ordered here and 10 by another order. Available is 15 - 10 = 5
    (the other line's), so Reserve 5 and Buy 5. A project line reads the share of 5: 2 + 8."""
    with blank_session() as db:
        world = _world(db)
        pool = _pool(db, 15, world[3])
        _line(db, world, pool, 10, klass="project", line_no=20)
        order, _l, _so, _c = _line(db, world, pool, 10, klass="retail")
        retail = _sheet(db, order)

    assert retail == {"reserve": Decimal("5"), "buy": Decimal("5")}


def test_r7_a_project_line_keeps_the_share_of_what_is_left():
    with blank_session() as db:
        world = _world(db)
        pool = _pool(db, 15, world[3])
        _line(db, world, pool, 10, klass="project", line_no=20)
        order, _l, _so, _c = _line(db, world, pool, 10, klass="project")
        got = _sheet(db, order)

    assert got == {"reserve": Decimal("2"), "buy": Decimal("8")}


def test_r7_the_same_answer_on_the_sheet_on_the_board_alone_and_with_other_lines():
    """Retail, 10 on hand and 10 ordered at the pool. Another product line of a project bin
    sits on the board beside it and must not move the answer."""
    with blank_session() as db:
        world = _world(db)
        pool = _pool(db, 10, world[3])
        own = _project_bin(db, pool)
        order, _l, core, _c = _line(db, world, pool, 10, klass="retail")
        _o, _l2, bin_core, _c2 = _line(
            db, world, own, 5, klass="project", line_no=20, when=REQUIRED_DATE - timedelta(days=14),
        )
        sheet = _sheet(db, order)
        alone = _sources(_board_row(_board(db, core), core))
        beside = _sources(_board_row(_board(db, core, bin_core), core))

    assert sheet == alone == beside == {"reserve": Decimal("10")}


def test_r7_two_lines_of_one_order_and_date_each_get_their_own_demand_back():
    """Retail, 20 on hand, 10 and 10 on one order and date: Available 20, nothing to buy."""
    with blank_session() as db:
        world = _world(db)
        company_id, _actor, project, product = world
        pool = _pool(db, 20, product)
        order, _l, core_so, _c = _line(db, world, pool, 10, klass="retail")
        second = _core_line(db, core_so, product, pool, qty_ordered="10", required_date=REQUIRED_DATE)
        _project_line(db, order, line_no=20, product=product, core_line=second)
        db.commit()
        proposal = ProjectSupplyService(db).proposal_for(order)
        got = _totals([c for line in proposal["lines"] for c in line["components"]])

    assert got == {"reserve": Decimal("20")}


# --------------------------------------------------------------------------- R8


def _retail_beside_a_full_book(mutate=None, *, delivered=None):
    """10 on hand, another line owes all 10, so Available is 0 unless this line's demand is
    added back. `mutate(core_so, core_line)` changes what this line is."""
    with blank_session() as db:
        world = _world(db)
        pool = _pool(db, 10, world[3])
        _line(db, world, pool, 10, klass="retail", line_no=20)
        order, _l, core_so, core_line = _line(db, world, pool, 10, klass="retail")
        if delivered is not None:
            core_line.qty_delivered = Decimal(delivered)
        if mutate:
            mutate(core_so, core_line)
        db.commit()
        return _sheet(db, order)


def test_r8_a_closed_order_adds_nothing_back():
    got = _retail_beside_a_full_book(lambda so, _line: setattr(so, "status", "closed"))
    assert "reserve" not in got, got


def test_r8_a_non_transferable_order_adds_nothing_back():
    got = _retail_beside_a_full_book(lambda so, _line: setattr(so, "is_transferable", False))
    assert "reserve" not in got, got


def test_r8_a_covered_line_adds_nothing_back():
    got = _retail_beside_a_full_book(lambda _so, line: setattr(line, "purchasing_status", "covered"))
    assert "reserve" not in got, got


def test_r8_a_line_at_a_retired_pool_adds_nothing_back():
    """A retired pool is in nobody's book and cannot be drawn on."""
    with blank_session() as db:
        world = _world(db)
        _pool(db, 10, world[3])
        other = _pool(db, 0, world[3])
        _line(db, world, other, 10, klass="retail", line_no=20)
        retired = _pool(db, 0, world[3], active=False)
        order, _l, _so, _c = _line(db, world, retired, 10, klass="retail")
        got = _sheet(db, order)

    assert "reserve" not in got, got


def test_r8_a_part_delivered_line_adds_back_what_it_still_owes():
    """10 ordered, 3 delivered, 10 on hand, nobody else: it owes 7, so Reserve 7."""
    with blank_session() as db:
        world = _world(db)
        pool = _pool(db, 10, world[3])
        order, _l, _so, core_line = _line(db, world, pool, 10, klass="retail")
        core_line.qty_delivered = Decimal("3")
        db.commit()
        got = _sheet(db, order)

    assert got == {"reserve": Decimal("7")}


def test_r8_another_line_never_reads_this_lines_add_back():
    """30 at another pool against 100 owed at this one: a net of -70. The retail line at the
    pool walks first and buys whole; the project line behind it must still read -70."""
    with blank_session() as db:
        world = _world(db)
        product = world[3]
        pool = _pool(db, 0, product)
        _pool(db, 30, product)
        own = _project_bin(db, pool)
        _o, _l, at_pool, _c = _line(db, world, pool, 100, klass="retail", when=_far(40))
        _o, _l, at_bin, _c = _line(db, world, own, 5, klass="project", line_no=20, when=_far(47))
        row = _board_row(_board(db, at_pool, at_bin), at_bin)

    assert _sources(row) == {"buy": Decimal("5")}


# --------------------------------------------------------------------------- R9


def test_r9_a_retail_line_with_stock_to_spare_reserves_it_all():
    """7 on hand, 5 ordered, nobody else: Reserve 5."""
    with blank_session() as db:
        world = _world(db)
        pool = _pool(db, 7, world[3])
        order, _l, _so, _c = _line(db, world, pool, 5, klass="retail")
        got = _sheet(db, order)

    assert got == {"reserve": Decimal("5")}


def test_r9_a_retail_line_on_just_enough_stock_reserves_it_all():
    """10 on hand, 10 ordered: Reserve 10 (the PR 1 known limit pinned Buy 10)."""
    with blank_session() as db:
        world = _world(db)
        pool = _pool(db, 10, world[3])
        order, _l, _so, _c = _line(db, world, pool, 10, klass="retail")
        got = _sheet(db, order)

    assert got == {"reserve": Decimal("10")}


def test_r9_a_project_line_at_the_dealer_pool_keeps_the_share():
    """10 on hand, 10 ordered: Reserve 5 + Buy 5."""
    with blank_session() as db:
        world = _world(db)
        pool = _pool(db, 10, world[3])
        order, _l, _so, _c = _line(db, world, pool, 10, klass="project")
        got = _sheet(db, order)

    assert got == {"reserve": Decimal("5"), "buy": Decimal("5")}


@pytest.mark.parametrize("klass", ["project", "retail"])
def test_r9_other_locations_keep_the_share_for_both_classes(klass):
    """A dealer-segment bin that is NOT its own pool draws on another bin's pool: 10 at the
    pool, 10 ordered at the bin, so the share of 10 is 5 and the rest is bought."""
    with blank_session() as db:
        world = _world(db)
        pool = _pool(db, 10, world[3])
        elsewhere = _warehouse(
            db, f"ZZE{_uid()[:6]}", segment="dealer", pool_warehouse_id=pool.id,
            fulfilment_planning=False,
        )
        db.commit()
        order, _l, _so, _c = _line(db, world, elsewhere, 10, klass=klass)
        got = _sheet(db, order)

    assert got == {"reserve": Decimal("5"), "buy": Decimal("5")}


@pytest.mark.parametrize("klass", ["retail", "other"])
def test_r9_other_counts_as_retail(klass):
    with blank_session() as db:
        world = _world(db)
        pool = _pool(db, 10, world[3])
        order, _l, _so, _c = _line(db, world, pool, 10, klass=klass)
        got = _sheet(db, order)

    assert got == {"reserve": Decimal("10")}


# --------------------------------------------------------------------------- R10


def _confirm_the_proposal(db, order, actor):
    """Confirm the engine's own proposal, line by line. Returns (reserved, bought, short)."""
    proposal = ProjectSupplyService(db).proposal_for(order)
    lines, wanted_reserve, wanted_buy = [], Decimal("0"), Decimal("0")
    for line in proposal["lines"]:
        reserve, buy = [], Decimal("0")
        for component in line["components"]:
            qty = Decimal(str(component["qty"]))
            if component["kind"] == "reserve":
                warehouse = (
                    db.query(Warehouse)
                    .filter(Warehouse.warehouse_code == component["source_location"])
                    .one()
                )
                reserve.append({"warehouse_id": str(warehouse.id), "qty": qty})
                wanted_reserve += qty
            elif component["kind"] == "buy":
                buy += qty
                wanted_buy += qty
        lines.append(ConfirmLine(project_line_id=line["project_line_id"], reserve=reserve, buy_qty=buy))
    fresh = ProjectSupplyService(db)
    fresh.confirm(order, ConfirmSupplyBody(lines=lines), actor_user_id=actor)
    db.commit()
    rows = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id.in_([line.project_line_id for line in lines]))
        .all()
    )
    bought = sum((Decimal(str(row.qty)) for row in rows), Decimal("0"))
    return wanted_reserve, wanted_buy, bought, _short(fresh)


@pytest.mark.parametrize("klass", ["project", "retail"])
@pytest.mark.parametrize(
    "here, elsewhere, qty",
    [
        (10, (40,), 30),
        (10, (30, 30), 40),
        (0, (30, 30), 50),
    ],
    ids=["10-here-40-there-line-30", "10-here-30-30-line-40", "0-here-30-30-line-50"],
)
def test_r10_confirming_the_engines_own_proposal_comes_up_short_by_nothing(
    klass, here, elsewhere, qty
):
    with blank_session() as db:
        world = _world(db)
        actor, product = world[1], world[3]
        pool = _pool(db, here, product)
        for hand in elsewhere:
            _pool(db, hand, product)
        order, _l, _so, _c = _line(db, world, pool, qty, klass=klass, when=_far(10))
        reserved, buy, bought, short = _confirm_the_proposal(db, order, actor)

    assert short == Decimal("0")
    assert reserved + buy == Decimal(qty)
    assert bought == buy


def test_r10_two_dates_at_one_pool_take_what_was_proposed():
    """Retail, 40 on hand, nobody else, 10 then 30: Available covers both, so Reserve 40 and
    nothing to buy, and the second date is not told it is 10 short."""
    with blank_session() as db:
        world = _world(db)
        actor, product = world[1], world[3]
        pool = _pool(db, 40, product)
        order, _l, core_so, _c = _line(db, world, pool, 10, klass="retail", when=_far(10))
        second = _core_line(db, core_so, product, pool, qty_ordered="30", required_date=_far(17))
        _project_line(db, order, line_no=20, product=product, core_line=second)
        db.commit()
        reserved, buy, bought, short = _confirm_the_proposal(db, order, actor)

    assert (reserved, buy, bought, short) == (Decimal("40"), Decimal("0"), Decimal("0"), Decimal("0"))


def test_r10_a_project_lines_sheet_is_unchanged():
    """A project bin line drawing the pool: 10 at the pool lends 5, as before."""
    with blank_session() as db:
        world = _world(db)
        pool = _pool(db, 10, world[3])
        own = _project_bin(db, pool)
        order, _l, _so, _c = _line(db, world, own, 10, klass="project")
        got = _sheet(db, order)

    assert got == {"reserve": Decimal("5"), "buy": Decimal("5")}


def test_r10_on_the_board_a_project_line_moves_only_for_a_real_draw():
    """20 on hand, 10 owed by a retail line at the pool. The retail line takes its own 10,
    which is paid for by its own demand and so costs the net nothing: the project bin line
    behind it still reads the pool's share (half of the true net of 10, which is 5)."""
    with blank_session() as db:
        world = _world(db)
        pool = _pool(db, 20, world[3])
        own = _project_bin(db, pool)
        _o, _l, at_pool, _c = _line(db, world, pool, 10, klass="retail")
        _o, _l, at_bin, _c = _line(
            db, world, own, 5, klass="project", line_no=20, when=REQUIRED_DATE + timedelta(days=1),
        )
        board = _board(db, at_pool, at_bin)

    assert _sources(_board_row(board, at_pool)) == {"reserve": Decimal("10")}
    assert _sources(_board_row(board, at_bin)) == {"reserve": Decimal("5")}


# --------------------------------------------------------------------------- R10, random worlds

SEEDS = range(int(os.environ.get("RND_FROM", "0")), int(os.environ.get("RND_TO", "8")))


def _random_world(db, rng, n_pools):
    """`n_pools` dealer pools (the first is the one lines sit at), one project bin on the
    first, and 2 to 4 orders of retail or project lines, one or two lines each, every line due
    inside the reserve window. Returns what the invariants need."""
    world = _world(db)
    company_id, actor, project, product = world
    hands = [rng.choice([0, 5, 10, 20, 30, 60]) for _ in range(n_pools)]
    pools = [_pool(db, hand, product) for hand in hands]
    sites = [("pool", pools[0])]
    sites += [("pool", pool) for pool in pools[1:]]
    orders, book = [], {str(pool.id): 0 for pool in pools}

    for number in range(rng.randint(2, 4)):
        klass = rng.choice(["retail", "project"])
        _kind, loc = rng.choice(sites)
        qty = rng.choice([5, 10, 20, 30])
        when = _far(rng.choice([5, 12, 19, 26]))
        order, line, core_so, _c = _line(db, world, loc, qty, klass=klass, line_no=10, when=when)
        book[str(loc.id)] += qty
        lines = [(str(loc.id), qty)]
        if rng.random() < 0.4:
            _kind2, loc2 = rng.choice(sites)
            qty2 = rng.choice([5, 10, 20])
            second = _core_line(db, core_so, product, loc2, qty_ordered=str(qty2), required_date=when)
            _project_line(db, order, line_no=20, product=product, core_line=second)
            book[str(loc2.id)] += qty2
            lines.append((str(loc2.id), qty2))
        db.commit()
        orders.append({"order": order, "core": core_so, "klass": klass, "lines": lines})
    return world, pools, hands, book, orders


def _check_random_world(seed, n_pools):
    """One world per case, on one blank schema: a loop of schemas in one test runs the
    database out of lock memory."""
    rng = random.Random(seed * 10 + n_pools)
    problems = []
    with blank_session() as db:
        world, pools, hands, book, orders = _random_world(db, rng, n_pools)
        actor = world[1]
        label = f"seed {seed} pools {n_pools} hands {hands} book {list(book.values())}"
        by_id = {str(pool.id): index for index, pool in enumerate(pools)}

        for entry in orders:
            sheet = _sheet(db, entry["order"])
            alone_board = _board(db, entry["core"])
            seen, distinct = set(), []
            for cell in alone_board["cells"]:
                for c in cell["contributions"]:
                    if c["key"] not in seen:
                        seen.add(c["key"])
                        distinct.append(c)
            alone = _totals([s for c in distinct for s in c["sources"]])
            if sheet != alone:
                problems.append(f"{label}: sheet {sheet} != board alone {alone}")
            # A single retail line whose pool covers the book: it must read it all, no share.
            if entry["klass"] == "retail" and len(entry["lines"]) == 1:
                where, qty = entry["lines"][0]
                if hands[by_id[where]] >= book[where] and sheet != {"reserve": Decimal(qty)}:
                    problems.append(f"{label}: retail line {qty} covered by its pool read {sheet}")

        for entry in orders:
            service = ProjectSupplyService(db)
            proposal = service.proposal_for(entry["order"])
            lines, ok = [], True
            for line in proposal["lines"]:
                reserve, buy = [], Decimal("0")
                for c in line["components"]:
                    qty = Decimal(str(c["qty"]))
                    if c["kind"] == "reserve":
                        warehouse = (
                            db.query(Warehouse)
                            .filter(Warehouse.warehouse_code == c["source_location"])
                            .one()
                        )
                        reserve.append({"warehouse_id": str(warehouse.id), "qty": qty})
                    elif c["kind"] == "buy":
                        buy += qty
                    else:
                        ok = False
                lines.append(
                    ConfirmLine(project_line_id=line["project_line_id"], reserve=reserve, buy_qty=buy)
                )
            if not ok:
                continue
            fresh = ProjectSupplyService(db)
            try:
                fresh.confirm(entry["order"], ConfirmSupplyBody(lines=lines), actor_user_id=actor)
            except SupplyLinesRefused as exc:
                problems.append(f"{label}: refused {exc.detail.get('failing_lines')}")
                db.rollback()
                continue
            db.commit()
            if _short(fresh) != 0:
                problems.append(f"{label}: confirm short {_short(fresh)}")
    return problems


@pytest.mark.parametrize("seed", list(SEEDS))
@pytest.mark.parametrize("n_pools", [2, 3])
def test_r10_random_worlds_over_two_and_three_pools_confirm_their_own_proposal(n_pools, seed):
    """One seeded world of two or three pools per case (16 cases, about a second each). For each: the engine's own proposal confirms with
    0 short and 0 refused, the sheet equals the board alone, and a single retail line whose
    pool covers its book reads Reserve all of it. Three pools are required: the shape a
    previous attempt got wrong while two looked fine. Sized for under a minute."""
    problems = _check_random_world(seed, n_pools)

    assert not problems, "\n".join(problems[:12])


# --------------------------------------------------------------------------- R11


def _confirm_reserve(db, order, line, pool, actor, qty):
    service = ProjectSupplyService(db)
    service.confirm(
        order,
        ConfirmSupplyBody(
            lines=[
                ConfirmLine(
                    project_line_id=str(line.id),
                    reserve=[{"warehouse_id": str(pool.id), "qty": Decimal(qty)}],
                )
            ]
        ),
        actor_user_id=actor,
    )
    db.commit()
    return _short(service)


@pytest.mark.parametrize("klass", ["project", "retail"])
def test_r11_a_reserve_cannot_take_stock_the_book_owes_to_another_order(klass):
    """10 on hand, 50 owed to another order, Reserve 10: short 10."""
    with blank_session() as db:
        world = _world(db)
        actor, product = world[1], world[3]
        pool = _pool(db, 10, product)
        _line(db, world, pool, 50, klass="project", line_no=30)
        order, line, _so, _c = _line(db, world, pool, 10, klass=klass)
        short = _confirm_reserve(db, order, line, pool, actor, "10")

    assert short == Decimal("10")


@pytest.mark.parametrize("klass", ["project", "retail"])
def test_r11_a_reserve_cannot_take_stock_the_book_has_reserved(klass):
    """10 on hand, 8 reserved: Reserve 10 is short 8."""
    with blank_session() as db:
        world = _world(db)
        actor, product = world[1], world[3]
        pool = _pool(db, 0, product)
        _stock(db, product, pool, on_hand=10, reserved=8)
        db.commit()
        order, line, _so, _c = _line(db, world, pool, 10, klass=klass)
        short = _confirm_reserve(db, order, line, pool, actor, "10")

    assert short == Decimal("8")


@pytest.mark.parametrize("klass", ["project", "retail"])
def test_r11_two_orders_pressed_separately_cannot_both_hold_the_same_10(klass):
    """10 on hand, two orders of 10, Reserve 10 on each in its own press. Together they come
    up at least 10 short, because only 10 exist."""
    with blank_session() as db:
        world = _world(db)
        actor, product = world[1], world[3]
        pool = _pool(db, 10, product)
        order_x, line_x, _so, _c = _line(db, world, pool, 10, klass=klass, line_no=10)
        order_y, line_y, _so, _c = _line(db, world, pool, 10, klass=klass, line_no=20)
        first = _confirm_reserve(db, order_x, line_x, pool, actor, "10")
        second = _confirm_reserve(db, order_y, line_y, pool, actor, "10")

    assert first + second >= Decimal("10"), (first, second)
