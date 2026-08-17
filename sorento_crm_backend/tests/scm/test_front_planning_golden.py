"""The golden set, asserted against an engine that does not exist yet (Stage 1C).

PRINCIPLES.md phase 2: for a deterministic engine "the golden-set expected numbers are
written as failing tests first, and the code is built to satisfy them". So these run RED
today, on purpose, and they say so: every one is `xfail(strict=True)`, which means the day
`app.services.scm.front_planning_engine` lands and satisfies a case, that case turns into an
XPASS and FAILS the suite until the marker comes off. A silent pass is the one outcome this
file must not allow.

The import is inside each test body rather than at module level for the same reason a
collection error is worse than a failure: a missing module at import time takes the whole
file out of the run, and a file nobody collects proves nothing.

The numbers themselves live in `front_planning_golden.py` and are not repeated here. The
last test in the file is NOT xfail: it checks the golden data against itself, because a
golden set whose components do not add up to the open quantity would have every engine test
chasing an impossible target.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from tests.scm.front_planning_golden import (
    ATTRIBUTION_CASES,
    BALANCE_INVARIANT_CASE,
    BALANCE_INVARIANT_STATED,
    BUY,
    CONFIRMED_COVER_CASE,
    CONFIRMED_COVER_RETAIL_KEY,
    CONFIRMED_COVER_RETAIL_NEED,
    DEALER_LOCATION,
    HOT_SELLING_WORKED_CASE,
    PROPOSAL_CASES,
    RESERVE,
    TWO_LINE_ATTRIBUTION_CASE,
)

STAGE_1C = (
    "Stage 1C: front planning engine not implemented yet "
    "(PLAN-scm-front-planning.md 3.2/3.3/3.5)"
)


def _components(result):
    """The engine's proposed components, however it ends up wrapping them.

    Deliberately forgiving about the container and strict about the contents: Stage 1C may
    return a dataclass, a dict or a list, but each component has to carry a kind, a
    quantity, a source location and its reason.
    """
    return tuple(getattr(result, "components", None) or result)


def _as_tuple(component):
    return (
        component.kind,
        Decimal(str(component.qty)),
        component.source_location,
        component.reason,
    )


# ------------------------------------------------------------------- AC-B08


@pytest.mark.xfail(strict=True, reason=STAGE_1C)
def test_the_hot_selling_worked_case_reserves_only_above_the_brw_floor():
    """AC-B08 and PLAN section 3.3's own worked example, to the unit."""
    from app.services.scm.front_planning_engine import propose_line

    case = HOT_SELLING_WORKED_CASE
    proposed = _components(propose_line(**case.inputs))

    assert tuple(_as_tuple(c) for c in proposed) == tuple(
        _as_tuple(c) for c in case.components
    )


@pytest.mark.xfail(strict=True, reason=STAGE_1C)
def test_a_hot_selling_product_reserves_no_dealer_facing_stock():
    """AC-B06. The 50 dealer units are visible and untouchable, not merely unpreferred."""
    from app.services.scm.front_planning_engine import propose_line

    case = HOT_SELLING_WORKED_CASE
    proposed = _components(propose_line(**case.inputs))

    dealer_reserve = sum(
        (
            Decimal(str(c.qty))
            for c in proposed
            if c.kind == RESERVE and c.source_location == DEALER_LOCATION
        ),
        Decimal("0"),
    )
    assert dealer_reserve == Decimal("0")
    assert case.qty_from(DEALER_LOCATION) == Decimal("0")


# ------------------------------------------------------------------- AC-B12


@pytest.mark.xfail(strict=True, reason=STAGE_1C)
def test_every_proposed_component_states_its_reason_beside_its_quantity():
    """AC-B14, in the exact words the criterion prints."""
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(propose_line(**BALANCE_INVARIANT_CASE.inputs))

    assert tuple(c.stated for c in proposed) == BALANCE_INVARIANT_STATED


@pytest.mark.xfail(strict=True, reason=STAGE_1C)
@pytest.mark.parametrize("case", PROPOSAL_CASES, ids=lambda c: c.ac)
def test_a_proposed_line_balances(case):
    """AC-B12: open = timely SPO + Reserve + Borrow + Buy, all terms non-negative."""
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(propose_line(**case.inputs))

    quantities = [Decimal(str(c.qty)) for c in proposed]
    assert all(q >= Decimal("0") for q in quantities)
    assert sum(quantities, Decimal("0")) == case.open_qty


# ------------------------------------------------------------------- AC-B02


@pytest.mark.xfail(strict=True, reason=STAGE_1C)
def test_opening_stock_goes_to_the_first_line_and_the_same_day_spo_to_the_second():
    """AC-B02's worked attribution: stock before SPO, lines in line-number order."""
    from app.services.scm.front_planning_engine import attribute_sources

    case = TWO_LINE_ATTRIBUTION_CASE
    result = attribute_sources(**case.inputs)

    for key, expected in case.expected.items():
        assert tuple(_as_tuple(c) for c in _components(result[key])) == tuple(
            _as_tuple(c) for c in expected
        )


@pytest.mark.xfail(strict=True, reason=STAGE_1C)
def test_reversing_the_database_row_order_changes_nothing():
    """AC-B02 and AC-B04: "database return order never participates"."""
    from app.services.scm.front_planning_engine import attribute_sources

    case = TWO_LINE_ATTRIBUTION_CASE
    forwards = attribute_sources(**case.inputs)
    backwards = attribute_sources(**case.reversed_inputs)

    for key in case.expected:
        assert tuple(_as_tuple(c) for c in _components(backwards[key])) == tuple(
            _as_tuple(c) for c in _components(forwards[key])
        )


# ------------------------------------------------------------------- AC-B13


@pytest.mark.xfail(strict=True, reason=STAGE_1C)
def test_cover_promised_to_a_confirmed_line_is_not_offered_to_the_next_one():
    """AC-B13: project open 10 covered by SPO 10, retail outstanding 10, stock 0.

    Retail need is 10, not 0. The failure this prevents is the same incoming quantity being
    counted as free twice, which reads on screen as demand that mysteriously needs nothing
    bought for it.
    """
    from app.services.scm.front_planning_engine import attribute_sources

    case = CONFIRMED_COVER_CASE
    result = attribute_sources(**case.inputs)

    retail = _components(result[CONFIRMED_COVER_RETAIL_KEY])
    assert tuple(_as_tuple(c) for c in retail) == tuple(
        _as_tuple(c) for c in case.expected[CONFIRMED_COVER_RETAIL_KEY]
    )
    uncovered = sum(
        (Decimal(str(c.qty)) for c in retail if c.kind == BUY), Decimal("0")
    )
    assert uncovered == CONFIRMED_COVER_RETAIL_NEED


# ---------------------------------------------------- the golden set itself


def test_every_golden_case_is_internally_consistent():
    """Not xfail: this one proves the TARGET is reachable, not that the engine reaches it.

    A case whose components do not add up to its open quantity would make the balance
    invariant unsatisfiable, and Stage 1C would spend its time arguing with the fixture
    instead of with the rule.
    """
    for case in PROPOSAL_CASES:
        quantities = [c.qty for c in case.components]
        assert all(q >= Decimal("0") for q in quantities), case.ac
        assert sum(quantities, Decimal("0")) == case.open_qty, case.ac

    for case in ATTRIBUTION_CASES:
        for key, components in case.expected.items():
            quantities = [c.qty for c in components]
            assert all(q >= Decimal("0") for q in quantities), (case.ac, key)
            assert sum(quantities, Decimal("0")) == case.open_qty_of(key), (case.ac, key)
