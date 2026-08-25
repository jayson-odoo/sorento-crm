"""Beyond-golden engine cases for the Stage 1C front-planning engine (PLAN 3.2/3.3/3.5).

`front_planning_golden.py` pins the four cases the PLAN itself states in words; this file
exercises boundaries the golden set does not: an own-then-pool split, the hot-selling floor
at its zero edge, the exact-on-the-required-date SPO boundary, Decimal exactness on numbers
that are not round tens, and a third `attribute_sources` case (two SPOs, three lines) so
"database return order never participates" is proven on more than the one pinned shape.

Not `xfail`: these are plain RED. `app.services.scm.front_planning_engine` does not exist
yet, so every test here fails with `ModuleNotFoundError` until Stage 1C lands, and the
import stays inside each test body so a missing module takes out one test, not the file.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

DEALER_LOCATION = "DLR-KL"
POOL_LOCATION = "BRW"
OWN_LOCATION = "SRT-KL"
REQUIRED_DATE = date(2027, 3, 1)


def _components(result):
    """Same forgiving unwrap as the golden test file: dataclass, dict or list."""
    return tuple(getattr(result, "components", None) or result)


# --------------------------------------------------------------- ladder v2: own location
# is never a Reserve source any more (section E rule 7); only the pool is.


def test_own_location_is_never_a_reserve_source_the_pool_covers_it_instead():
    """Ladder v2 (section E, rule 7): "the own-location Reserve rung is REMOVED". A line
    whose own free stock used to cover it directly now draws the SAME quantity from the
    pool instead - own free stock is never read by the ladder at all.
    """
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("90"),
            line_no=5,
            required_date=REQUIRED_DATE,
            fulfilment_location=OWN_LOCATION,
            is_dealer_hot_selling=False,
            pools=[
                {
                    "location": POOL_LOCATION,
                    "free": Decimal("100"),
                    "available": Decimal("100"),
                }
            ],
            timely_spo_qty=Decimal("0"),
            is_discontinued=False,
        )
    )

    assert not any(c.source_location == OWN_LOCATION for c in proposed)
    reserves = {c.source_location: c for c in proposed if c.kind == "reserve"}
    assert set(reserves) == {POOL_LOCATION}
    assert reserves[POOL_LOCATION].qty == Decimal("90")
    assert reserves[POOL_LOCATION].reason == "Pool BRW has 100 available"
    assert reserves[POOL_LOCATION].rung == "pool"

    # The whole line balances: nothing left over to Buy.
    assert sum((c.qty for c in proposed), Decimal("0")) == Decimal("90")
    assert not any(c.kind == "buy" for c in proposed)


def test_pool_reserve_draws_the_own_site_pool_before_the_other_site_pools():
    """Section E rule 2: "P(S) first, then the other site pools". The own site pool is
    not enough on its own, so the residual comes from the SECOND pool in the ordered list,
    never the reverse."""
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("90"),
            required_date=REQUIRED_DATE,
            fulfilment_location=OWN_LOCATION,
            pools=[
                {"location": "BRW", "free": Decimal("30"), "available": Decimal("30")},
                {"location": "MWH", "free": Decimal("100"), "available": Decimal("100")},
            ],
            timely_spo_qty=Decimal("0"),
        )
    )

    reserves = {c.source_location: c for c in proposed if c.kind == "reserve"}
    assert set(reserves) == {"BRW", "MWH"}
    assert reserves["BRW"].qty == Decimal("30")
    assert reserves["MWH"].qty == Decimal("60")
    assert sum((c.qty for c in proposed), Decimal("0")) == Decimal("90")


def test_every_pool_is_capped_by_its_own_signed_availability_not_only_a_hot_selling_one():
    """Section E rule 2: `capacity = max(min(free, available), 0)` for EVERY pool now,
    whether the product is hot-selling or not - a change from 3.3a's "neither: uncapped",
    because ladder v2 can reach a SECOND pool that was never this line's own."""
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("90"),
            required_date=REQUIRED_DATE,
            fulfilment_location=OWN_LOCATION,
            pools=[
                {"location": POOL_LOCATION, "free": Decimal("100"), "available": Decimal("40")},
            ],
            timely_spo_qty=Decimal("0"),
        )
    )

    # The whole-line rule: 40 of 90 covered is not the whole line, so the WHOLE 90 is
    # bought - never "reserve 40, buy 50" - and no Reserve component survives at all.
    assert len(proposed) == 1
    assert proposed[0].kind == "buy"
    assert proposed[0].qty == Decimal("90")
    assert proposed[0].reason == "Only 40 of 90 can be covered from stock - buy the whole line"


# --------------------------------------------------------------- hot-selling (PLAN 3.3a)
#
# Amended 19 August 2026 (the captain): "reserve can always reserve regardless of dealer
# hot selling or not ... it is the pool BRW that is dependent on dealer hot selling ... if
# it is dealer hot selling, then we shouldn't take from BRW, if it is project hot selling,
# then we can take from BRW (provided the available quantity is positive)".


def test_dealer_hot_selling_offers_no_pool_at_all():
    """The pool is kept for retail on a dealer hot-selling product: not even a capped
    amount is offered, so with nothing else to cover it the whole line is a Buy."""
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("200"),
            line_no=7,
            required_date=REQUIRED_DATE,
            fulfilment_location=DEALER_LOCATION,
            is_dealer_hot_selling=True,
            pools=[
                {
                    "location": POOL_LOCATION,
                    "free": Decimal("150"),
                    "available": Decimal("150"),
                }
            ],
            timely_spo_qty=Decimal("0"),
            is_discontinued=False,
        )
    )

    assert not any(c.source_location == POOL_LOCATION for c in proposed)
    assert len(proposed) == 1
    assert proposed[0].kind == "buy"
    assert proposed[0].qty == Decimal("200")


def test_project_hot_selling_caps_the_pool_at_its_own_signed_availability():
    """PLAN 3.3a, still true for a single pool under ladder v2: `max(min(pool free,
    pool_available), 0)`. The pool's free balance (150) is more than its signed
    availability (40), so the draw stops at 40 - which is not the whole line, so the
    whole-line rule buys all of it rather than leaving a partial Reserve standing.
    """
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("40"),
            line_no=9,
            required_date=REQUIRED_DATE,
            fulfilment_location=OWN_LOCATION,
            is_project_hot_selling=True,
            pools=[
                {
                    "location": POOL_LOCATION,
                    "free": Decimal("150"),
                    "available": Decimal("40"),
                }
            ],
            timely_spo_qty=Decimal("0"),
            is_discontinued=False,
        )
    )

    assert len(proposed) == 1
    assert proposed[0].kind == "reserve"
    assert proposed[0].qty == Decimal("40")
    assert proposed[0].source_location == POOL_LOCATION
    assert proposed[0].reason == "Pool BRW has 40 available"


def test_project_hot_selling_offers_nothing_when_the_pools_availability_is_not_positive():
    """The other side of the same boundary: a pool already oversold (`available`
    negative or zero) offers nothing at all, never a floor read as "some" (PLAN 3.3a)."""
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("40"),
            line_no=11,
            required_date=REQUIRED_DATE,
            fulfilment_location=DEALER_LOCATION,
            is_project_hot_selling=True,
            pools=[
                {
                    "location": POOL_LOCATION,
                    "free": Decimal("50"),
                    "available": Decimal("-12"),
                }
            ],
            timely_spo_qty=Decimal("0"),
            is_discontinued=False,
        )
    )

    assert not any(c.kind == "reserve" for c in proposed)
    assert len(proposed) == 1, "no zero-quantity Reserve should be proposed at all"
    assert proposed[0].kind == "buy"
    assert proposed[0].qty == Decimal("40")


def test_dealer_hot_selling_wins_when_a_product_is_hot_on_both_demand_classes():
    """Precedence (PLAN 3.3a): a product hot on both classes at once is judged dealer-hot,
    so the pool is not offered even though it would have had positive availability under
    the project-hot rule."""
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("40"),
            line_no=13,
            required_date=REQUIRED_DATE,
            fulfilment_location=DEALER_LOCATION,
            is_dealer_hot_selling=True,
            is_project_hot_selling=True,
            pools=[
                {
                    "location": POOL_LOCATION,
                    "free": Decimal("50"),
                    "available": Decimal("50"),
                }
            ],
            timely_spo_qty=Decimal("0"),
            is_discontinued=False,
        )
    )

    assert not any(c.source_location == POOL_LOCATION for c in proposed)
    assert len(proposed) == 1
    assert proposed[0].kind == "buy"
    assert proposed[0].qty == Decimal("40")


# --------------------------------------------------------------- timely vs late SPO


def test_an_spo_arriving_exactly_on_the_required_date_counts_as_timely_coverage():
    """PLAN 3.5: "An SPO arriving on the required date therefore counts at that date"."""
    from app.services.scm.front_planning_engine import attribute_sources

    result = attribute_sources(
        product_code="ZZT-CB0001",
        warehouse_code=OWN_LOCATION,
        opening_stock=Decimal("0"),
        supply_events=[
            {
                "kind": "spo",
                "arrival_date": REQUIRED_DATE,
                "qty": Decimal("15"),
                "spo_number": "202703-S0099",
                "spo_line_no": 1,
            }
        ],
        demand_lines=[
            {
                "so_number": "SO-500",
                "line_no": 10,
                "line_id": "dddddddd-0000-0000-0000-000000000010",
                "open_qty": Decimal("15"),
                "required_date": REQUIRED_DATE,
            }
        ],
    )

    line = _components(result[("SO-500", 10)])
    assert len(line) == 1
    assert line[0].kind == "timely_spo"
    assert line[0].qty == Decimal("15")
    assert line[0].reason == "SPO 202703-S0099 arrives on 2027-03-01, by the required date"


def test_an_spo_arriving_the_day_after_the_required_date_contributes_zero_coverage():
    """The other side of the same boundary: one day later is advisory, not coverage, so
    the line's whole need becomes Buy (PLAN 3.5: "contributes no coverage at that date")."""
    from app.services.scm.front_planning_engine import attribute_sources

    result = attribute_sources(
        product_code="ZZT-CB0001",
        warehouse_code=OWN_LOCATION,
        opening_stock=Decimal("0"),
        supply_events=[
            {
                "kind": "spo",
                "arrival_date": REQUIRED_DATE + timedelta(days=1),
                "qty": Decimal("15"),
                "spo_number": "202703-S0099",
                "spo_line_no": 1,
            }
        ],
        demand_lines=[
            {
                "so_number": "SO-500",
                "line_no": 10,
                "line_id": "dddddddd-0000-0000-0000-000000000010",
                "open_qty": Decimal("15"),
                "required_date": REQUIRED_DATE,
            }
        ],
    )

    line = _components(result[("SO-500", 10)])
    assert not any(c.kind == "timely_spo" for c in line)
    assert len(line) == 1
    assert line[0].kind == "buy"
    assert line[0].qty == Decimal("15")
    assert line[0].reason == "remaining uncovered need"


# --------------------------------------------------------------- Decimal exactness


def test_quantities_stay_exact_decimal_with_fractional_inputs():
    """Every quantity is Decimal, never float (PLAN 3): a fractional split that is not a
    round multiple of ten is where a float implementation would drift by a cent."""
    from app.services.scm.front_planning_engine import propose_line

    open_qty = Decimal("70.255")
    proposed = _components(
        propose_line(
            open_qty=open_qty,
            line_no=11,
            required_date=REQUIRED_DATE,
            fulfilment_location=OWN_LOCATION,
            is_dealer_hot_selling=False,
            pools=[
                {
                    "location": POOL_LOCATION,
                    "free": Decimal("100"),
                    "available": Decimal("100"),
                }
            ],
            timely_spo_qty=Decimal("0"),
            is_discontinued=False,
        )
    )

    quantities = [c.qty for c in proposed]
    assert all(isinstance(q, Decimal) for q in quantities), "no float leaked into a quantity"
    assert sum(quantities, Decimal("0")) == open_qty

    pool_reserve = next(c for c in proposed if c.source_location == POOL_LOCATION)
    assert pool_reserve.qty == Decimal("70.255")


# --------------------------------------------------------------- reversed-input determinism


def test_attribute_sources_gives_the_same_answer_with_three_lines_reversed():
    """A second, independent case from the golden two-line one: two SPOs sharing an
    arrival date (tie-broken by SPO number) and three demand lines, so the ordering
    contract is proven on a shape the golden set does not cover, not just repeated on it.
    """
    from app.services.scm.front_planning_engine import attribute_sources

    inputs = dict(
        product_code="ZZT-CB0002",
        warehouse_code=OWN_LOCATION,
        opening_stock=Decimal("5"),
        supply_events=[
            {
                "kind": "spo",
                "arrival_date": REQUIRED_DATE,
                "qty": Decimal("10"),
                "spo_number": "202703-S0001",
                "spo_line_no": 1,
            },
            {
                "kind": "spo",
                "arrival_date": REQUIRED_DATE,
                "qty": Decimal("8"),
                "spo_number": "202703-S0002",
                "spo_line_no": 1,
            },
        ],
        demand_lines=[
            {
                "so_number": "SO-300",
                "line_no": 10,
                "line_id": "eeeeeeee-0000-0000-0000-000000000010",
                "open_qty": Decimal("5"),
                "required_date": REQUIRED_DATE,
            },
            {
                "so_number": "SO-300",
                "line_no": 20,
                "line_id": "eeeeeeee-0000-0000-0000-000000000020",
                "open_qty": Decimal("10"),
                "required_date": REQUIRED_DATE,
            },
            {
                "so_number": "SO-300",
                "line_no": 30,
                "line_id": "eeeeeeee-0000-0000-0000-000000000030",
                "open_qty": Decimal("8"),
                "required_date": REQUIRED_DATE,
            },
        ],
    )
    reversed_inputs = dict(inputs)
    reversed_inputs["demand_lines"] = list(reversed(inputs["demand_lines"]))
    reversed_inputs["supply_events"] = list(reversed(inputs["supply_events"]))

    forwards = attribute_sources(**inputs)
    backwards = attribute_sources(**reversed_inputs)

    for key in (("SO-300", 10), ("SO-300", 20), ("SO-300", 30)):
        forward_components = tuple(
            (c.kind, c.qty, c.source_location) for c in _components(forwards[key])
        )
        backward_components = tuple(
            (c.kind, c.qty, c.source_location) for c in _components(backwards[key])
        )
        assert backward_components == forward_components, key

    # Line 10 takes the opening stock; line 20 takes the first SPO in full; line 30 takes
    # the second SPO in full. Nothing is left uncovered, so no Buy anywhere.
    line10 = _components(forwards[("SO-300", 10)])
    line20 = _components(forwards[("SO-300", 20)])
    line30 = _components(forwards[("SO-300", 30)])
    assert [c.kind for c in line10] == ["reserve"]
    assert [c.kind for c in line20] == ["timely_spo"]
    assert [c.kind for c in line30] == ["timely_spo"]
    assert line20[0].qty == Decimal("10")
    assert line30[0].qty == Decimal("8")


# ============================================================================
# Ladder v2 (PLAN-demo-followups-19aug-ladder-v2.md section E)
# ============================================================================

GROUP_CODE = "BB"


# --------------------------------------------------------------- rung 0: coverage date


def test_a_line_required_after_the_coverage_date_is_bought_in_full_and_nothing_else_runs():
    """Section E rule 0: "a far-future line ... is Buy all. No partial decision"."""
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("358"),
            required_date=date(2029, 1, 1),
            fulfilment_location=OWN_LOCATION,
            reorder_coverage_until=date(2026, 10, 31),
            pools=[
                {"location": POOL_LOCATION, "free": Decimal("999"), "available": Decimal("999")}
            ],
            timely_spo_qty=Decimal("999"),
        )
    )

    assert len(proposed) == 1
    assert proposed[0].kind == "buy"
    assert proposed[0].qty == Decimal("358")
    assert proposed[0].reason == "Beyond purchasing's coverage (31 Oct 2026) - buy now"
    assert proposed[0].rung == "buy"


def test_a_line_required_on_or_before_the_coverage_date_runs_the_ladder_normally():
    """The boundary: required ON the coverage date is still inside it."""
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("50"),
            required_date=date(2026, 10, 31),
            fulfilment_location=OWN_LOCATION,
            reorder_coverage_until=date(2026, 10, 31),
            pools=[
                {"location": POOL_LOCATION, "free": Decimal("50"), "available": Decimal("50")}
            ],
        )
    )

    assert len(proposed) == 1
    assert proposed[0].kind == "reserve"
    assert proposed[0].qty == Decimal("50")


def test_no_coverage_date_set_never_gates_a_line():
    """`reorder_coverage_until=None` is "no limit set", never a guessed date."""
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("10"),
            required_date=date(2099, 1, 1),
            fulfilment_location=OWN_LOCATION,
            reorder_coverage_until=None,
            pools=[
                {"location": POOL_LOCATION, "free": Decimal("10"), "available": Decimal("10")}
            ],
        )
    )

    assert proposed[0].kind == "reserve"


# ------------------------------------------------- rung 0b: the ATP reserve window


def test_a_line_beyond_its_reserve_window_never_borrows_stock_another_order_holds():
    """A line due long after purchasing could simply buy for it must not take stock a
    nearer-dated order is already holding.

    The borrow rungs are exactly that: rung 4 takes another sales order's committed quantity
    and rung 5 takes free stock outside the group that its own book expects. Neither is
    surplus, so a line outside its window is not offered them at all, and the whole-line rule
    turns what is left into a Buy.
    """
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("40"),
            required_date=date(2027, 6, 1),
            fulfilment_location=OWN_LOCATION,
            group_code=GROUP_CODE,
            outside_reserve_window=True,
            group_borrow_candidates=[
                {"location": "MWH-BB", "qty": Decimal("40"), "donor_so_number": "SO-9"},
            ],
            cross_group_borrow_candidates=[{"location": "BRW-HP", "qty": Decimal("40")}],
        )
    )

    assert [c.kind for c in proposed] == ["buy"]
    assert proposed[0].qty == Decimal("40")
    assert "beyond the lead time window" in proposed[0].reason
    assert "kept for nearer orders" in proposed[0].reason


def test_a_line_beyond_its_window_still_takes_stock_that_is_genuinely_surplus():
    """The pool and group-take rungs are already capped at the location's SIGNED availability
    (`on hand - SO qty + SPO qty`), so what they offer is what nothing else at that location
    is owed. A far line may have that: refusing it would buy stock the business already holds
    and nobody needs."""
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("40"),
            required_date=date(2027, 6, 1),
            fulfilment_location=OWN_LOCATION,
            group_code=GROUP_CODE,
            outside_reserve_window=True,
            pools=[
                {"location": POOL_LOCATION, "free": Decimal("40"), "available": Decimal("40")}
            ],
        )
    )

    assert [c.kind for c in proposed] == ["reserve"]
    assert proposed[0].qty == Decimal("40")


def test_a_line_beyond_its_window_buys_the_whole_of_it_when_the_surplus_falls_short():
    """The whole-line rule, unchanged: 25 of surplus against 40 owed is not "reserve 25, buy
    15", it is a Buy - and the reason names the window rather than the arithmetic, because the
    window is why the other rungs were not tried."""
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("40"),
            required_date=date(2027, 6, 1),
            fulfilment_location=OWN_LOCATION,
            group_code=GROUP_CODE,
            outside_reserve_window=True,
            pools=[
                {"location": POOL_LOCATION, "free": Decimal("25"), "available": Decimal("25")}
            ],
            group_borrow_candidates=[
                {"location": "MWH-BB", "qty": Decimal("15"), "donor_so_number": "SO-9"},
            ],
        )
    )

    assert [c.kind for c in proposed] == ["buy"]
    assert proposed[0].qty == Decimal("40")
    assert "beyond the lead time window" in proposed[0].reason


def test_a_line_inside_its_window_is_untouched_by_the_rule():
    """The near line keeps every rung it always had, borrow included."""
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("40"),
            required_date=date(2026, 9, 1),
            fulfilment_location=OWN_LOCATION,
            group_code=GROUP_CODE,
            outside_reserve_window=False,
            group_borrow_candidates=[
                {"location": "MWH-BB", "qty": Decimal("40"), "donor_so_number": "SO-9"},
            ],
        )
    )

    assert [c.kind for c in proposed] == ["borrow"]
    assert proposed[0].qty == Decimal("40")


def test_the_window_is_the_lead_time_plus_the_buffer_and_the_boundary_is_inside_it():
    """`reserve_window_end` is the one place the arithmetic lives, so the engine, the service
    and the sentence a planner reads cannot disagree about which day the window ends on."""
    from app.services.scm.front_planning_engine import (
        RESERVE_BUFFER_DAYS,
        reserve_window_end,
    )

    assert RESERVE_BUFFER_DAYS == 14
    # 90 days of lead time plus the 14-day buffer, counted from today.
    assert reserve_window_end(date(2026, 8, 25), 90) == date(2026, 12, 7)
    # A line due ON the last day of the window is INSIDE it, the same boundary rule the
    # coverage date above follows.
    assert reserve_window_end(date(2026, 8, 25), 0) == date(2026, 9, 8)


def test_a_line_with_no_date_is_never_outside_its_window():
    """An undated line has no delivery date to be beyond anything: the ladder runs for it as
    it always did, and the caller decides nothing on a date nobody stated."""
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("40"),
            required_date=None,
            fulfilment_location=OWN_LOCATION,
            group_code=GROUP_CODE,
            outside_reserve_window=False,
            group_borrow_candidates=[
                {"location": "MWH-BB", "qty": Decimal("40"), "donor_so_number": "SO-9"},
            ],
        )
    )

    assert [c.kind for c in proposed] == ["borrow"]


# --------------------------------------------------------------- rung 3: group take


def test_group_take_covers_the_line_from_a_sibling_location_never_its_own():
    """Section E rule 3: "sibling locations of G at other sites with POSITIVE Available ->
    take from them. The own location L is never a source"."""
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("50"),
            required_date=REQUIRED_DATE,
            fulfilment_location="BRW-BB",
            group_code=GROUP_CODE,
            group_take_candidates=[{"location": "MWH-BB", "qty": Decimal("50")}],
        )
    )

    assert len(proposed) == 1
    assert proposed[0].kind == "reserve"
    assert proposed[0].rung == "group_take"
    assert proposed[0].source_location == "MWH-BB"
    assert proposed[0].qty == Decimal("50")
    assert proposed[0].reason == "MWH-BB has 50 available in the BB group"


def test_group_take_never_offers_the_lines_own_location_even_if_passed_one():
    """Belt and braces: the CALLER must never include `fulfilment_location` in the
    candidate list, and this pins that a same-code candidate is still consumed - the
    exclusion is the caller's job (`_group_take_candidates`), proven by the service test;
    this only proves the engine draws down whatever it is handed, in order."""
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("30"),
            required_date=REQUIRED_DATE,
            fulfilment_location="BRW-BB",
            group_code=GROUP_CODE,
            group_take_candidates=[
                {"location": "MWH-BB", "qty": Decimal("10")},
                {"location": "DC1-BB", "qty": Decimal("20")},
            ],
        )
    )

    assert [c.source_location for c in proposed] == ["MWH-BB", "DC1-BB"]
    assert sum((c.qty for c in proposed), Decimal("0")) == Decimal("30")


# --------------------------------------------------------------- rung 4: group borrow


def test_group_borrow_from_a_lower_ranked_donor_raises_an_order_back():
    """Section E rule 4: donors ranked lower are proposed automatically, and every borrow
    carries an order-back (equal to what was taken, at the donor's own required date)."""
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("145"),
            required_date=REQUIRED_DATE,
            fulfilment_location="BRW-BB",
            group_code=GROUP_CODE,
            group_borrow_candidates=[
                {
                    "location": "MWH-BB",
                    "qty": Decimal("145"),
                    "donor_so_number": "SO371334",
                    "donor_line_no": 2,
                    "donor_agent_code": "JEREMY",
                    "same_agent": False,
                }
            ],
        )
    )

    assert len(proposed) == 1
    component = proposed[0]
    assert component.kind == "borrow"
    assert component.rung == "group_borrow"
    assert component.qty == Decimal("145")
    assert component.source_location == "MWH-BB"
    assert component.donor_so_number == "SO371334"
    assert component.donor_line_no == 2
    assert component.donor_agent_code == "JEREMY"
    assert component.same_agent is False
    assert component.order_back_qty == Decimal("145")
    assert component.reason == (
        "SO371334 line 2 (agent JEREMY) holds 145 at MWH-BB; it is ranked below this "
        "line; order-back raised"
    )


def test_a_same_agent_donor_is_never_auto_composed_only_offered():
    """Section 8 / E rule 4: "the SAME AGENT's other SOs (even higher ranked)" are
    OFFERED, never auto-proposed - so `propose_line` never sees one unless the caller put
    it in `group_borrow_candidates`, which the service only does for a lower-ranked donor.
    This pins the engine side of that split: the engine composes whatever it is handed and
    has no opinion of its own about rank or agent."""
    from app.services.scm.front_planning_engine import propose_line

    # The caller (the service) decided this same-agent donor is HIGHER ranked and so did
    # not include it here at all - the whole-line rule then falls back to Buy.
    proposed = _components(
        propose_line(
            open_qty=Decimal("100"),
            required_date=REQUIRED_DATE,
            fulfilment_location="BRW-BB",
            group_code=GROUP_CODE,
            group_borrow_candidates=[],
        )
    )

    assert len(proposed) == 1
    assert proposed[0].kind == "buy"
    assert proposed[0].qty == Decimal("100")


# --------------------------------------------------------------- rung 5: cross-group borrow


def test_cross_group_borrow_completes_the_line_within_the_cap():
    """Section E rule 5: free stock outside the group, offered only within the cap - the
    service is the one that decides the cap; this pins that the engine draws whatever
    candidate list it is handed, after the group rungs, before falling back to Buy."""
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("20"),
            required_date=REQUIRED_DATE,
            fulfilment_location="BRW-BB",
            group_code=GROUP_CODE,
            cross_group_borrow_candidates=[{"location": "BRW-HP", "qty": Decimal("20")}],
        )
    )

    assert len(proposed) == 1
    component = proposed[0]
    assert component.kind == "borrow"
    assert component.rung == "cross_group_borrow"
    assert component.source_location == "BRW-HP"
    assert component.qty == Decimal("20")
    assert "BRW-HP" in component.reason
    assert "cross-group borrow limit" in component.reason


# --------------------------------------------------------------- rung 6: whole-line rule


def test_whole_line_rule_covers_the_whole_line_across_every_rung_in_order():
    """Section E rule 6: "cover Q entirely in rung order" - a case that needs incoming,
    pool, group take AND group borrow together to reach the whole of Q."""
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("100"),
            required_date=REQUIRED_DATE,
            fulfilment_location="BRW-BB",
            group_code=GROUP_CODE,
            timely_spo_qty=Decimal("10"),
            pools=[
                {"location": "BRW", "free": Decimal("20"), "available": Decimal("20")}
            ],
            group_take_candidates=[{"location": "MWH-BB", "qty": Decimal("30")}],
            group_borrow_candidates=[
                {
                    "location": "DC1-BB",
                    "qty": Decimal("40"),
                    "donor_so_number": "SO400001",
                    "donor_line_no": 1,
                    "donor_agent_code": "TERA",
                    "same_agent": False,
                }
            ],
        )
    )

    assert [c.rung for c in proposed] == [
        "incoming", "pool", "group_take", "group_borrow",
    ]
    assert sum((c.qty for c in proposed), Decimal("0")) == Decimal("100")
    assert not any(c.kind == "buy" for c in proposed)


def test_whole_line_rule_drops_every_partial_component_when_the_line_falls_short():
    """Section E rule 6, the other side: 213 of 358 covered is not the whole line, so
    NONE of the partial components survive and the whole 358 is bought instead."""
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("358"),
            required_date=REQUIRED_DATE,
            fulfilment_location="BRW-BB",
            group_code=GROUP_CODE,
            pools=[
                {"location": "BRW", "free": Decimal("213"), "available": Decimal("213")}
            ],
        )
    )

    assert len(proposed) == 1
    assert proposed[0].kind == "buy"
    assert proposed[0].qty == Decimal("358")
    assert proposed[0].reason == (
        "Only 213 of 358 can be covered from stock - buy the whole line"
    )


def test_open_qty_of_zero_proposes_nothing_at_all():
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("0"),
            required_date=REQUIRED_DATE,
            fulfilment_location="BRW-BB",
            pools=[
                {"location": "BRW", "free": Decimal("100"), "available": Decimal("100")}
            ],
        )
    )

    assert proposed == ()
