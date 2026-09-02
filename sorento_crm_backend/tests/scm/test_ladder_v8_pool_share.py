"""LADDER v8: the site pool is asked FIRST, for its share, and a unit's lines walk one by one.

`PLAN-scm-fulfilment-feedback-2sep.md` S2, rulings R-A to R-E and R-K; the criteria are
AC-2.1 to AC-2.10 in `scm-fulfilment-feedback-2sep-acceptance-criteria.md`.

What changed, and why each test here exists:

* **R-A / R-B** the site pool of the asking bin is step 0 rather than step 4, and it may
  answer with PART of a line - its allowance is `available x (100 - pool_share_pct) / 100`,
  floored to whole units and capped by the five-pool net. Inside `immediate_window_days` a
  line takes `min(line, allowance)` and the remainder walks the rest of the ladder; beyond
  it the line is taken whole or not at all, because there is time to buy;
* **R-C** split, never mix: the share is its own sub-unit and the REMAINDER still obeys
  R10/R33 whole-or-nothing, over own locations, the two borrows and Buy - with NO second
  pool step, because the pile has already answered;
* **R-D** the five-pool net is still the bound, so 3,034 free with the pools netting 1
  spares 1;
* **R-E** a planning unit's contributing lines walk one at a time, smallest first, each
  fed the piles the previous one left. Supersedes ladder v6's "one date, one quantity";
* **R-K** the allowance a walk used is the number the lightbox prints as "Available for
  Project", so the two can never disagree.

The walk cases are DATA (`front_planning_golden.py`, `V8_WALK_CASES`) and the assertions
are here, the same split the Stage 1C golden set has: expected numbers that live beside the
code that produces them stop being expectations.

The board case at the bottom needs Postgres (`blank_session`) and seeds its own chain -
CI's database has no data.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from tests.scm.front_planning_golden import (
    AS_OF,
    AVAILABLE_FOR_PROJECT_CASES,
    V8_WALK_CASES,
)


def _as_tuple(component):
    return (
        component.kind,
        Decimal(str(component.qty)),
        component.source_location,
        component.reason,
    )


# --------------------------------------------------------------------------- AC-2.1 to 2.7


@pytest.mark.parametrize("case", V8_WALK_CASES, ids=lambda c: c.ac)
def test_the_v8_walk_proposes_exactly_the_golden_composition(case):
    """Component for component, reason for reason: the share, and what the remainder did."""
    from app.services.scm.front_planning_engine import walk_line

    walked = walk_line(**case.inputs)

    assert tuple(_as_tuple(c) for c in walked.components) == tuple(
        _as_tuple(c) for c in case.components
    ), case.title


@pytest.mark.parametrize("case", V8_WALK_CASES, ids=lambda c: c.ac)
def test_the_v8_walk_balances(case):
    """Every walk still sums to the open quantity - the share plus what walked after it."""
    from app.services.scm.front_planning_engine import walk_line

    quantities = [Decimal(str(c.qty)) for c in walk_line(**case.inputs).components]

    assert all(q >= Decimal("0") for q in quantities), case.ac
    assert sum(quantities, Decimal("0")) == case.open_qty, case.ac


@pytest.mark.parametrize("case", V8_WALK_CASES, ids=lambda c: c.ac)
def test_the_v8_options_table_reads_as_the_uac_writes_it(case):
    """AC-2.1 / AC-2.4 / AC-2.8: five rows in the v8 walk order, the site pool first, each
    stating what it can give - and `pool_share` stating WHY when the number alone does not
    say it ("600 is more than the 450 BRW can spare")."""
    from app.services.scm.front_planning_engine import walk_line

    options = walk_line(**case.inputs).options

    assert [option.step for option in options] == [
        row.step for row in case.options
    ], "five rows, in walk order, the site pool first (R-A)"
    for option, expected in zip(options, case.options):
        assert option.whole is expected.whole, (case.ac, option.step)
        assert Decimal(str(option.gives_qty or 0)) == expected.gives_qty, (
            case.ac,
            option.step,
        )
        assert option.reason == expected.reason, (case.ac, option.step)
        assert option.chosen is expected.chosen, (case.ac, option.step)
    assert sum(1 for option in options if option.chosen) == 1


@pytest.mark.parametrize("case", V8_WALK_CASES, ids=lambda c: c.ac)
def test_every_v8_option_still_carries_its_fulfil_date_and_days_late(case):
    """AC-2.8 (R36 stands): `fulfil_date` and `days_late` are null TOGETHER and exactly
    when the step offered nothing whole, and `days_late` is never negative."""
    from app.services.scm.front_planning_engine import walk_line

    for option in walk_line(**case.inputs).options:
        assert (option.fulfil_date is None) == (option.days_late is None), option
        if option.days_late is not None:
            assert option.days_late >= 0, option


def test_the_pool_share_step_is_first_and_named_after_the_pool_it_asks():
    """AC-2.1 / R-A: "Use BRW stock", first, because it is the pool of the ASKING bin - the
    label names the pool rather than reading "Take from the pool" for whichever site."""
    from app.services.scm.front_planning_engine import (
        OPTION_STEPS,
        STEP_POOL_SHARE,
        walk_line,
    )

    assert OPTION_STEPS[0] == STEP_POOL_SHARE
    walked = walk_line(
        open_qty=Decimal("3"),
        as_of=AS_OF,
        required_date=AS_OF + timedelta(days=2),
        pools=[
            {"location": "MWH", "free": Decimal("47"), "available": Decimal("47")}
        ],
        pools_net=Decimal("47"),
        pool_share_pct=50,
        immediate_window_days=30,
    )

    assert walked.options[0].label == "Use MWH stock"


def test_the_remainder_walks_without_a_second_pool_step():
    """R-C: the pile answered once. What is left of the line walks own locations, the two
    borrows and Buy - and never comes back to the pool for the rest, which would be the
    "half a promise from here, half from there" R10 exists to refuse."""
    from app.services.scm.front_planning_engine import RUNG_POOL, walk_line

    walked = walk_line(
        open_qty=Decimal("650"),
        as_of=AS_OF,
        required_date=AS_OF + timedelta(days=10),
        pools=[
            {"location": "BRW", "free": Decimal("900"), "available": Decimal("900")}
        ],
        pools_net=Decimal("900"),
        pool_share_pct=50,
        immediate_window_days=30,
    )

    pooled = [c for c in walked.components if c.rung == RUNG_POOL]
    assert [c.qty for c in pooled] == [Decimal("450")], (
        "one pool draw, the share, and nothing more"
    )


# --------------------------------------------------------------------------- AC-2.6b


@pytest.mark.parametrize(
    "available,net,share_pct,expected", AVAILABLE_FOR_PROJECT_CASES
)
def test_available_for_project_is_the_floor_of_the_share_capped_by_the_net(
    available, net, share_pct, expected
):
    """AC-2.6b / R-K: the number the lightbox prints IS the allowance the walk used -
    `min(floor(available x (100 - share) / 100), max(net, 0))`, whole units, never blank."""
    from app.services.scm.front_planning_engine import available_for_project

    assert available_for_project(available, net, share_pct) == expected


def test_the_walk_and_the_lightbox_read_one_allowance():
    """R-K said as an equality rather than as two formulas: what the pool_share option can
    give a line big enough to want all of it is exactly what the row would print."""
    from app.services.scm.front_planning_engine import available_for_project, walk_line

    walked = walk_line(
        open_qty=Decimal("100000"),
        as_of=AS_OF,
        required_date=AS_OF + timedelta(days=3),
        pools=[
            {"location": "BRW", "free": Decimal("590"), "available": Decimal("590")}
        ],
        pools_net=Decimal("900"),
        pool_share_pct=50,
        immediate_window_days=30,
    )

    assert Decimal(str(walked.options[0].gives_qty)) == available_for_project(
        Decimal("590"), Decimal("900"), 50
    )


# --------------------------------------------------------------------------- AC-2.6


def test_the_queue_at_a_pile_serves_the_smaller_line_first_within_one_date():
    """AC-2.6's ordering half: inside one date and one order, the SMALLER line is served
    first, so the Stock tab's running Available reads 135 then 1305 - the same order the
    walk fills the unit's lines in (R-E)."""
    from app.services.project_supply_service import _pile_order

    when = date(2026, 9, 14)
    rows = [
        {
            "rank_score": 0.0,
            "required_date": when,
            "so_number": "SO419208",
            "line_no": 2,
            "line_id": "line-1305",
            "open_qty": Decimal("1305"),
        },
        {
            "rank_score": 0.0,
            "required_date": when,
            "so_number": "SO419208",
            "line_no": 3,
            "line_id": "line-135",
            "open_qty": Decimal("135"),
        },
    ]

    assert [row["line_no"] for row in sorted(rows, key=_pile_order)] == [3, 2]


def test_a_units_lines_walk_one_at_a_time_smallest_first():
    """AC-2.6, the captain's own SO419208 case (R-E).

    CSK14A-NL at BRW-BB, 14 September, lines of 1,305 and 135, with 145 on hand and a
    nearer line already taking 10. Ladder v6 planned the unit as ONE quantity of 1,440,
    could not cover it whole, and read Buy 1440 while 135 sat on the floor. Under v8 the
    unit's lines walk one at a time, smallest first, each fed the piles the previous one
    left: the 135 is covered from BRW-BB and the 1,305 buys. The cell still reads 1,440.
    """
    from app.services.project_supply_service import ProjectSupplyService
    from app.services.scm.front_planning_engine import qty_text

    from tests._pg_fixture import blank_session
    from tests.scm.test_ladder_v6_order_unit import _seed_order, _sheet
    from tests.scm.test_project_supply_service_ladder import _group_sites, _seed_line, _world
    from tests.test_so_supply_confirmation import _stock

    when = date.today() + timedelta(days=12)
    nearer = date.today() + timedelta(days=2)
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        _stock(db, product, own, on_hand=145)
        # The nearer line takes its 10 off the pile before this order is reached.
        _seed_line(
            db, company_id, project, product, own,
            qty_ordered=10, required_date=nearer, line_no=10,
        )
        _core_so, order, _mirrors = _seed_order(
            db, company_id, project, product,
            lines=[(2, "1305", own, when), (3, "135", own, when)],
        )
        lines = _sheet(db, order)
        service = ProjectSupplyService(db)
        mirror_lines = service.lines_of(str(order.id))
        facts = service._facts_for(order, mirror_lines)
        composed = service.compose_lines(
            [
                (line.line_no, facts[str(line.id)], ("unit",))
                for line in mirror_lines
            ]
        )

    stated = {
        line_no: [
            (c["kind"], c["qty"], c["source_location"]) for c in line["components"]
        ]
        for line_no, line in lines.items()
    }
    assert stated[3] == [("reserve", "135", own.warehouse_code)], (
        "the smaller line walks first and takes what the pile actually holds"
    )
    assert stated[2] == [("buy", "1305", None)], (
        "the bigger line is fed what the smaller one left, which is nothing"
    )
    assert [lines[2]["unit_qty"], lines[3]["unit_qty"]] == ["1440", "1440"], (
        "the unit is still one cell of 1,440 (R-E keeps the unit, changes the walk)"
    )
    assert qty_text(
        sum(
            (Decimal(c["qty"]) for line in lines.values() for c in line["components"]),
            Decimal("0"),
        )
    ) == "1440"
    # The walk order itself: ascending quantity, then line number.
    assert [key for key in composed] == [3, 2]
