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


# --------------------------------------------------------------- own-then-pool Reserve


def test_reserve_draws_from_the_own_location_before_the_pool_and_states_both_wordings():
    """PLAN 3.2 step 2 / 3.3's non-hot-selling boundary: "own fulfilment location first
    then pool, no floor". Own free stock is not enough on its own, so the residual comes
    from the pool, and the two Reserve components carry the two location-named reason
    wordings the golden fixtures already use elsewhere for these two locations.
    """
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("90"),
            line_no=5,
            required_date=REQUIRED_DATE,
            fulfilment_location=OWN_LOCATION,
            is_dealer_hot_selling=False,
            free_stock={OWN_LOCATION: Decimal("30"), POOL_LOCATION: Decimal("100")},
            pool_location=POOL_LOCATION,
            timely_spo_qty=Decimal("0"),
            is_discontinued=False,
        )
    )

    reserves = {c.source_location: c for c in proposed if c.kind == "reserve"}
    assert set(reserves) == {OWN_LOCATION, POOL_LOCATION}
    assert reserves[OWN_LOCATION].qty == Decimal("30")
    assert reserves[OWN_LOCATION].reason == "free stock at SRT-KL covers the need by the required date"
    assert reserves[POOL_LOCATION].qty == Decimal("60")
    assert reserves[POOL_LOCATION].reason == "free stock at BRW covers the need by the required date"

    # The two components balance the whole line: nothing left over to Buy.
    assert sum((c.qty for c in proposed), Decimal("0")) == Decimal("90")
    assert not any(c.kind == "buy" for c in proposed)


# --------------------------------------------------------------- hot-selling (PLAN 3.3a)
#
# Amended 19 August 2026 (the captain): "reserve can always reserve regardless of dealer
# hot selling or not ... it is the pool BRW that is dependent on dealer hot selling ... if
# it is dealer hot selling, then we shouldn't take from BRW, if it is project hot selling,
# then we can take from BRW (provided the available quantity is positive)".


def test_dealer_hot_selling_reserves_own_location_in_full_and_offers_no_pool():
    """Own-location Reserve is ALWAYS eligible, hot-selling or not - the dealer stock at
    999 is reserved just as it would be for an ordinary item, and the pool contributes
    nothing at all (not even a capped amount): the old reorder-level cap is gone.
    """
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("200"),
            line_no=7,
            required_date=REQUIRED_DATE,
            fulfilment_location=DEALER_LOCATION,
            is_dealer_hot_selling=True,
            free_stock={DEALER_LOCATION: Decimal("999"), POOL_LOCATION: Decimal("150")},
            pool_location=POOL_LOCATION,
            pool_available=Decimal("150"),
            timely_spo_qty=Decimal("0"),
            is_discontinued=False,
        )
    )

    assert not any(c.source_location == POOL_LOCATION for c in proposed)

    reserve = next(c for c in proposed if c.kind == "reserve")
    assert reserve.qty == Decimal("200")
    assert reserve.source_location == DEALER_LOCATION
    assert reserve.reason == "free stock at DLR-KL covers the need by the required date"
    assert not any(c.kind == "buy" for c in proposed)


def test_project_hot_selling_caps_the_pool_at_its_own_signed_availability():
    """PLAN 3.3a: `max(min(pool free, pool_available), 0)`. The pool's free balance (150)
    is more than its signed availability (40), so the draw stops at 40 - the residual
    still buys, rather than reaching further into a pool that is already thin.
    """
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("200"),
            line_no=9,
            required_date=REQUIRED_DATE,
            fulfilment_location=OWN_LOCATION,
            is_project_hot_selling=True,
            free_stock={OWN_LOCATION: Decimal("0"), POOL_LOCATION: Decimal("150")},
            pool_location=POOL_LOCATION,
            pool_available=Decimal("40"),
            timely_spo_qty=Decimal("0"),
            is_discontinued=False,
        )
    )

    reserve = next(c for c in proposed if c.kind == "reserve")
    assert reserve.qty == Decimal("40")
    assert reserve.source_location == POOL_LOCATION
    assert reserve.reason == (
        "free stock in the shared BRW pool covers the need by the required date, drawn "
        "while its availability stays positive (40 available)"
    )

    buy = next(c for c in proposed if c.kind == "buy")
    assert buy.qty == Decimal("160")
    assert buy.reason == "remaining uncovered need"


def test_project_hot_selling_offers_nothing_when_the_pools_availability_is_not_positive():
    """The other side of the same boundary: a pool already oversold (`pool_available`
    negative or zero) offers nothing at all, never a floor read as "some" (PLAN 3.3a)."""
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("40"),
            line_no=11,
            required_date=REQUIRED_DATE,
            fulfilment_location=DEALER_LOCATION,
            is_project_hot_selling=True,
            free_stock={DEALER_LOCATION: Decimal("0"), POOL_LOCATION: Decimal("50")},
            pool_location=POOL_LOCATION,
            pool_available=Decimal("-12"),
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
            free_stock={DEALER_LOCATION: Decimal("10"), POOL_LOCATION: Decimal("50")},
            pool_location=POOL_LOCATION,
            pool_available=Decimal("50"),
            timely_spo_qty=Decimal("0"),
            is_discontinued=False,
        )
    )

    assert not any(c.source_location == POOL_LOCATION for c in proposed)
    reserve = next(c for c in proposed if c.kind == "reserve")
    assert reserve.qty == Decimal("10")
    assert reserve.source_location == DEALER_LOCATION
    buy = next(c for c in proposed if c.kind == "buy")
    assert buy.qty == Decimal("30")


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
            free_stock={OWN_LOCATION: Decimal("20.125"), POOL_LOCATION: Decimal("100")},
            pool_location=POOL_LOCATION,
            timely_spo_qty=Decimal("0"),
            is_discontinued=False,
        )
    )

    quantities = [c.qty for c in proposed]
    assert all(isinstance(q, Decimal) for q in quantities), "no float leaked into a quantity"
    assert sum(quantities, Decimal("0")) == open_qty

    own_reserve = next(c for c in proposed if c.source_location == OWN_LOCATION)
    assert own_reserve.qty == Decimal("20.125")


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
