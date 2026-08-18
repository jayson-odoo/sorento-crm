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
            reorder_levels={},
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


# --------------------------------------------------------------- hot-selling / BRW cap


def test_hot_selling_reserve_never_draws_dealer_stock_even_when_the_pool_falls_short():
    """AC-B06, with different numbers than the pinned worked case: the pool cap (50) is
    smaller than open quantity (200), and 999 units are sitting at the dealer location.
    Reserve must still stop at the cap rather than reaching for the dealer pile.
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
            reorder_levels={POOL_LOCATION: Decimal("100")},
            timely_spo_qty=Decimal("0"),
            is_discontinued=False,
        )
    )

    assert not any(c.source_location == DEALER_LOCATION for c in proposed)

    reserve = next(c for c in proposed if c.kind == "reserve")
    assert reserve.qty == Decimal("50")  # max(150 - 100, 0)
    assert reserve.source_location == POOL_LOCATION
    assert reserve.reason == (
        "free stock in the shared BRW pool above its reorder level of 100 covers "
        "the need by the required date"
    )

    buy = next(c for c in proposed if c.kind == "buy")
    assert buy.qty == Decimal("150")
    assert buy.reason == "remaining uncovered need"


def test_the_brw_cap_floors_at_zero_when_pool_free_stock_is_below_its_reorder_level():
    """PLAN 3.3: `MAX(BRW free unclaimed stock - level, 0)`. Free stock 50 against a level
    of 80 is a negative gap, and the rule is explicit that it floors at zero rather than
    going negative -- Reserve must not be proposed at all, and the whole line is Buy.
    """
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(
        propose_line(
            open_qty=Decimal("40"),
            line_no=9,
            required_date=REQUIRED_DATE,
            fulfilment_location=DEALER_LOCATION,
            is_dealer_hot_selling=True,
            free_stock={DEALER_LOCATION: Decimal("500"), POOL_LOCATION: Decimal("50")},
            pool_location=POOL_LOCATION,
            reorder_levels={POOL_LOCATION: Decimal("80")},
            timely_spo_qty=Decimal("0"),
            is_discontinued=False,
        )
    )

    assert not any(c.kind == "reserve" for c in proposed)
    assert len(proposed) == 1, "no zero-quantity Reserve should be proposed at all"
    assert proposed[0].kind == "buy"
    assert proposed[0].qty == Decimal("40")
    assert proposed[0].reason == "remaining uncovered need"


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
            reorder_levels={},
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
