"""The golden set, asserted against the Stage 1C front-planning engine.

PRINCIPLES.md phase 2: for a deterministic engine "the golden-set expected numbers are
written as failing tests first, and the code is built to satisfy them". These were written
RED, every one `xfail(strict=True)`, so that the day
`app.services.scm.front_planning_engine` landed and satisfied a case it turned into an
XPASS and failed the suite until the marker came off. The engine now exists, the markers
are gone, and these are ordinary passing tests: a silent pass is the one outcome this file
was never allowed to have.

The import is inside each test body rather than at module level for the same reason a
collection error is worse than a failure: a missing module at import time takes the whole
file out of the run, and a file nobody collects proves nothing.

The numbers themselves live in `front_planning_golden.py` and are not repeated here. The
last test in the file checks the golden data against itself, because a golden set whose
components do not add up to the open quantity would have every engine test chasing an
impossible target.
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
    POOL_LOCATION,
    PROJECT_HOT_SELLING_WORKED_CASE,
    PROPOSAL_CASES,
    RESERVE,
    TWO_LINE_ATTRIBUTION_CASE,
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


def test_the_dealer_hot_selling_worked_case_offers_no_pool_and_buys_the_whole_line():
    """AC-B08 and PLAN 3.3a's own worked example, updated for ladder v2 (section E rule 7,
    19 August 2026 follow-up): the own-location Reserve rung this case used to exercise no
    longer exists, so a dealer hot-selling line with no other cover is a straight Buy."""
    from app.services.scm.front_planning_engine import propose_line

    case = HOT_SELLING_WORKED_CASE
    proposed = _components(propose_line(**case.inputs))

    assert tuple(_as_tuple(c) for c in proposed) == tuple(
        _as_tuple(c) for c in case.components
    )


def test_a_dealer_hot_selling_product_offers_no_pool_reserve_at_all():
    """Ladder v2 (section E rule 7): the line's own location is never a Reserve source any
    more, so a dealer hot-selling product's own stock is not touched by this ladder either
    - only the pool rung is gated by hot-selling, and dealer-hot excludes it entirely.
    """
    from app.services.scm.front_planning_engine import propose_line

    case = HOT_SELLING_WORKED_CASE
    proposed = _components(propose_line(**case.inputs))

    assert not any(c.kind == RESERVE for c in proposed)
    pool_reserve = sum(
        (
            Decimal(str(c.qty))
            for c in proposed
            if c.kind == RESERVE and c.source_location == POOL_LOCATION
        ),
        Decimal("0"),
    )
    assert pool_reserve == Decimal("0")


def test_the_project_hot_selling_worked_case_caps_the_pool_at_its_availability():
    """PLAN 3.3a's other worked example: project hot-selling draws the pool only while its
    signed availability stays positive."""
    from app.services.scm.front_planning_engine import propose_line

    case = PROJECT_HOT_SELLING_WORKED_CASE
    proposed = _components(propose_line(**case.inputs))

    assert tuple(_as_tuple(c) for c in proposed) == tuple(
        _as_tuple(c) for c in case.components
    )


# ------------------------------------------------------------------- AC-B12


def test_every_proposed_component_states_its_reason_beside_its_quantity():
    """AC-B14, in the exact words the criterion prints."""
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(propose_line(**BALANCE_INVARIANT_CASE.inputs))

    assert tuple(c.stated for c in proposed) == BALANCE_INVARIANT_STATED


@pytest.mark.parametrize("case", PROPOSAL_CASES, ids=lambda c: c.ac)
def test_a_proposed_line_balances(case):
    """AC-B12: open = timely SPO + Reserve + Borrow + Buy, all terms non-negative."""
    from app.services.scm.front_planning_engine import propose_line

    proposed = _components(propose_line(**case.inputs))

    quantities = [Decimal(str(c.qty)) for c in proposed]
    assert all(q >= Decimal("0") for q in quantities)
    assert sum(quantities, Decimal("0")) == case.open_qty


# ------------------------------------------------------------------- AC-B02


def test_opening_stock_goes_to_the_first_line_and_the_same_day_spo_to_the_second():
    """AC-B02's worked attribution: stock before SPO, lines in line-number order."""
    from app.services.scm.front_planning_engine import attribute_sources

    case = TWO_LINE_ATTRIBUTION_CASE
    result = attribute_sources(**case.inputs)

    for key, expected in case.expected.items():
        assert tuple(_as_tuple(c) for c in _components(result[key])) == tuple(
            _as_tuple(c) for c in expected
        )


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
    """This one proves the TARGET is reachable, not that the engine reaches it.

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
