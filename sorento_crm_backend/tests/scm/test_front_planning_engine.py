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
# Ladder v3 (PLAN-scm-cs-planning-uat.md section 1b, captain 25 August 2026)
# ============================================================================

GROUP_CODE = "BB"


# ------------------------------------------------- rung 0: beyond the window, buy it all


def test_a_line_required_after_the_coverage_date_is_bought_in_full_and_no_stock_is_taken():
    """Section 1b rung 0: "a far-future line ... is Buy all. No partial decision" - with a
    pool holding three times what it needs and nothing on the water."""
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
            timely_spo_qty=Decimal("0"),
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

    assert len(proposed) == 1
    assert proposed[0].kind == "reserve"


def test_a_line_beyond_the_lead_time_window_takes_no_stock_but_still_takes_incoming():
    """AC-L1, the captain's own words: "if delivery date exceed lead time, directly buy" -
    and section 1b's rung 1 is UNCHANGED, so the one thing a far line still takes is supply
    already on its way.

    v2 walked the two surplus rungs for such a line and refused it only the borrow rungs.
    v3 walks no STOCK rung at all: the pool, the group and every donor beside it are never
    consulted, however much they hold. But incoming supply is already bought, and buying it
    a second time is a double purchase, not a conservative one.
    """
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("40"),
            required_date=date(2027, 6, 1),
            fulfilment_location=OWN_LOCATION,
            group_code=GROUP_CODE,
            outside_reserve_window=True,
            timely_spo_qty=Decimal("40"),
            pools=[
                {"location": POOL_LOCATION, "free": Decimal("400"), "available": Decimal("400")}
            ],
            group_take_candidates=[{"location": "MWH-BB", "qty": Decimal("400")}],
            cross_group_borrow_candidates=[{"location": "BRW-HP", "qty": Decimal("400")}],
        )
    )

    assert [c.kind for c in proposed] == ["timely_spo"]
    assert [c.rung for c in proposed] == ["incoming"]
    assert proposed[0].qty == Decimal("40")
    assert proposed[0].source_location == OWN_LOCATION


def test_a_line_beyond_the_window_is_bought_whole_when_the_incoming_falls_short():
    """The whole-line rule stands beyond the window too: 40 arriving against 71 owed is not
    "incoming 40, buy 31", it is a Buy of the whole 71 with the window named as the reason.

    A partial incoming beside a Buy would be exactly the mix AC-L5 refuses at confirm, and
    the reason has to name the window rather than the arithmetic - the window is why the
    stock rungs were never walked.
    """
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("71"),
            required_date=date(2027, 6, 1),
            fulfilment_location=OWN_LOCATION,
            group_code=GROUP_CODE,
            outside_reserve_window=True,
            timely_spo_qty=Decimal("40"),
            pools=[
                {"location": POOL_LOCATION, "free": Decimal("400"), "available": Decimal("400")}
            ],
        )
    )

    assert [c.kind for c in proposed] == ["buy"]
    assert proposed[0].qty == Decimal("71")
    assert proposed[0].rung == "buy"
    assert proposed[0].reason == (
        "Delivery date beyond the lead time window; stock kept for nearer orders"
    )


def test_incoming_beyond_the_window_names_the_spo_it_comes_from():
    """Named is the useful form on a far line too: "SPO 202703-S0011 arrives on ..." is
    something CS can look up, and the reason is the one rung 1 always writes."""
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("40"),
            required_date=date(2027, 6, 1),
            fulfilment_location=OWN_LOCATION,
            outside_reserve_window=True,
            timely_spo_qty=Decimal("40"),
            timely_spo_refs=[
                {
                    "spo_number": "202703-S0011",
                    "spo_line_no": 1,
                    "arrival_date": date(2027, 5, 1),
                    "qty": Decimal("40"),
                }
            ],
        )
    )

    assert [c.kind for c in proposed] == ["timely_spo"]
    assert proposed[0].reason == (
        "SPO 202703-S0011 arrives on 2027-05-01, by the required date"
    )


def test_a_line_beyond_purchasings_coverage_date_takes_its_incoming_too():
    """The two bounds share one rule: rung 1 runs for either, and only rung 1."""
    from app.services.scm.front_planning_engine import propose_line

    covered = _components(
        propose_line(
            open_qty=Decimal("358"),
            required_date=date(2029, 1, 1),
            fulfilment_location=OWN_LOCATION,
            reorder_coverage_until=date(2026, 10, 31),
            timely_spo_qty=Decimal("358"),
            pools=[
                {"location": POOL_LOCATION, "free": Decimal("999"), "available": Decimal("999")}
            ],
        )
    )

    assert [c.rung for c in covered] == ["incoming"]
    assert covered[0].qty == Decimal("358")

    short = _components(
        propose_line(
            open_qty=Decimal("358"),
            required_date=date(2029, 1, 1),
            fulfilment_location=OWN_LOCATION,
            reorder_coverage_until=date(2026, 10, 31),
            timely_spo_qty=Decimal("100"),
        )
    )

    assert [c.kind for c in short] == ["buy"]
    assert short[0].qty == Decimal("358")
    assert short[0].reason == "Beyond purchasing's coverage (31 Oct 2026) - buy now"


def test_a_line_inside_its_window_is_untouched_by_the_rule():
    """The near line keeps every rung it has."""
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("40"),
            required_date=date(2026, 9, 1),
            fulfilment_location=OWN_LOCATION,
            group_code=GROUP_CODE,
            outside_reserve_window=False,
            group_take_candidates=[{"location": "MWH-BB", "qty": Decimal("40")}],
        )
    )

    assert [c.rung for c in proposed] == ["group_take"]
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
            group_take_candidates=[{"location": "MWH-BB", "qty": Decimal("40")}],
        )
    )

    assert [c.rung for c in proposed] == ["group_take"]


# ----------------------------------------------------------------- rung 2: the own group


def test_group_take_covers_the_line_from_a_group_location():
    """Section 1b rung 2: "consider the group location first (only available quantity)"."""
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


def test_the_group_rung_draws_its_locations_in_the_order_the_caller_gave_them():
    """The line's OWN location is a group location again under v3, and the caller hands it
    over first (`_group_take_candidates`). The engine never re-sorts: it walks what it is
    given, which is what makes the service the single place the order is decided."""
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("30"),
            required_date=REQUIRED_DATE,
            fulfilment_location="BRW-BB",
            group_code=GROUP_CODE,
            group_take_candidates=[
                {"location": "BRW-BB", "qty": Decimal("10")},
                {"location": "DC1-BB", "qty": Decimal("20")},
            ],
        )
    )

    assert [c.source_location for c in proposed] == ["BRW-BB", "DC1-BB"]
    assert sum((c.qty for c in proposed), Decimal("0")) == Decimal("30")


def test_the_group_is_drawn_before_the_pool():
    """AC-L2, and the whole point of v3's reordering: "if group location don't have then
    consider the pool". 100 owed against 40 at the line's own location, 30 at a sibling and
    1000 in the pool draws 40 + 30 from the group and only the last 30 from the pool.

    Under v2 the pool went first and swallowed the lot, so a group that held the stock sat
    untouched while the shared pile paid for the line.
    """
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("100"),
            required_date=REQUIRED_DATE,
            fulfilment_location="BRW-BB",
            group_code=GROUP_CODE,
            group_take_candidates=[
                {"location": "BRW-BB", "qty": Decimal("40")},
                {"location": "DC1-BB", "qty": Decimal("30")},
            ],
            pools=[
                {"location": "BRW", "free": Decimal("1000"), "available": Decimal("1000")}
            ],
        )
    )

    assert [(c.rung, c.source_location, c.qty) for c in proposed] == [
        ("group_take", "BRW-BB", Decimal("40")),
        ("group_take", "DC1-BB", Decimal("30")),
        ("pool", "BRW", Decimal("30")),
    ]


# ----------------------------------------------------------------- rung 3: the site pools


def test_the_pool_rung_still_runs_when_the_group_holds_nothing():
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("71"),
            required_date=REQUIRED_DATE,
            fulfilment_location="BRW-BB",
            group_code=GROUP_CODE,
            group_take_candidates=[],
            pools=[
                {"location": "BRW", "free": Decimal("71"), "available": Decimal("71")}
            ],
        )
    )

    assert [(c.rung, c.source_location) for c in proposed] == [("pool", "BRW")]


# ----------------------------------------- rung 4: borrowing another location's free stock


def test_cross_group_borrow_completes_the_line_within_the_cap():
    """Section 1b rung 4: "if pool also don't have then consider borrowing from other
    location's available quantity" - the cap is the service's decision; this pins that the
    engine draws whatever candidate list it is handed, after the group and the pool."""
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


def test_borrowing_from_another_sales_order_is_never_proposed_automatically():
    """AC-L3, ruled 25 August 2026: group borrow "stays as a manual pick in Amend /
    BorrowAddDialog". So the engine has no rung for it at all - it takes no donor list, and
    a line the group and the pool cannot cover falls to Buy rather than quietly taking
    another customer's committed quantity and raising an order-back nobody asked for.
    """
    import inspect

    from app.services.scm.front_planning_engine import propose_line

    assert "group_borrow_candidates" not in inspect.signature(propose_line).parameters

    proposed = _components(
        propose_line(
            open_qty=Decimal("100"),
            required_date=REQUIRED_DATE,
            fulfilment_location="BRW-BB",
            group_code=GROUP_CODE,
        )
    )

    assert [c.kind for c in proposed] == ["buy"]
    assert proposed[0].qty == Decimal("100")


# --------------------------------------------------------------- rung 5: whole-line rule


def test_whole_line_rule_covers_the_whole_line_across_every_rung_in_order():
    """Section 1b rung 5: "cover Q entirely in rung order" - a case that needs incoming, the
    group, the pool AND a cross-group borrow together to reach the whole of Q."""
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("100"),
            required_date=REQUIRED_DATE,
            fulfilment_location="BRW-BB",
            group_code=GROUP_CODE,
            timely_spo_qty=Decimal("10"),
            group_take_candidates=[{"location": "MWH-BB", "qty": Decimal("30")}],
            pools=[
                {"location": "BRW", "free": Decimal("20"), "available": Decimal("20")}
            ],
            cross_group_borrow_candidates=[
                {"location": "BRW-HP", "qty": Decimal("40")},
            ],
        )
    )

    assert [c.rung for c in proposed] == [
        "incoming", "group_take", "pool", "cross_group_borrow",
    ]
    assert sum((c.qty for c in proposed), Decimal("0")) == Decimal("100")
    assert not any(c.kind == "buy" for c in proposed)


def test_whole_line_rule_drops_every_partial_component_when_the_line_falls_short():
    """Section 1b rung 5, the other side: 213 of 358 covered is not the whole line, so
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
