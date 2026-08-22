"""Golden set for Bundle price allocation (AC-F11).

Written BEFORE the implementation, on purpose. A bundle's price is allocated
across its components pro-rata by list price, and the ONE property that must
never break is that the allocated lines sum EXACTLY to the bundle price - not
"within a cent". Anything else means a customer is invoiced a different total
than the one they agreed to, and the discrepancy surfaces in accounting weeks
later.

Pure arithmetic, no database. The rules being pinned:

  * weight of a component = list_price x quantity
  * each line gets round(bundle_price x weight / total_weight, 2)
  * whatever the rounding leaves over is assigned to the LARGEST line, ties
    broken by position, so the result is deterministic
  * every component gets a line, including a zero-priced one
  * if no component carries a price, the split is equal
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.dealer_kit.bundle_pricing import (
    BundleComponentInput,
    allocate_bundle_price,
)


def _c(price, qty=1, key=None):
    return BundleComponentInput(
        key=key or f"p{price}-{qty}",
        list_price=None if price is None else Decimal(str(price)),
        quantity=qty,
    )


def _total(lines) -> Decimal:
    return sum((line.allocated for line in lines), Decimal("0"))


# --------------------------------------------------------------------------
# The property that matters
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bundle_price,components",
    [
        ("100.00", [_c(50), _c(50)]),
        ("100.00", [_c(1), _c(1), _c(1)]),           # the 1/3 remainder case
        ("0.03", [_c(1), _c(1), _c(1)]),             # a remainder bigger than the shares
        ("999.99", [_c(3), _c(7), _c(11)]),
        ("1234.56", [_c(19.99), _c(0.01), _c(500)]),
        ("10.00", [_c(1, qty=3), _c(1, qty=1)]),     # quantity is part of the weight
        ("0.01", [_c(5), _c(5)]),                    # a cent that cannot be split
        ("100.00", [_c(0), _c(100)]),                # a free component still gets a line
        ("100.00", [_c(0), _c(0)]),                  # nothing priced -> equal split
        ("50.00", [_c(7)]),                          # one component takes it all
        ("100.00", [_c(1)] * 7),                     # 7 does not divide 10000 cents
    ],
)
def test_allocated_lines_sum_exactly_to_the_bundle_price(bundle_price, components):
    lines = allocate_bundle_price(Decimal(bundle_price), components)
    assert _total(lines) == Decimal(bundle_price)


@pytest.mark.parametrize("bundle_price", ["0.01", "0.02", "7.77", "1000000.00"])
def test_the_sum_holds_across_magnitudes(bundle_price):
    components = [_c(3), _c(5), _c(7), _c(11), _c(13)]
    lines = allocate_bundle_price(Decimal(bundle_price), components)
    assert _total(lines) == Decimal(bundle_price)


# --------------------------------------------------------------------------
# Where the remainder goes
# --------------------------------------------------------------------------


def test_the_remainder_lands_on_the_largest_line():
    # 100.00 over weights 1/1/1 is 33.333... each. Two cents are left over and
    # both go to one line, so the result is deterministic rather than "spread
    # somewhere".
    lines = allocate_bundle_price(Decimal("100.00"), [_c(1, key="a"), _c(1, key="b"), _c(2, key="c")])
    by_key = {line.key: line.allocated for line in lines}
    assert by_key["c"] > by_key["a"]
    assert _total(lines) == Decimal("100.00")


def test_a_tie_for_largest_is_broken_by_position_not_by_chance():
    first = allocate_bundle_price(
        Decimal("10.00"), [_c(1, key="a"), _c(1, key="b"), _c(1, key="c")]
    )
    again = allocate_bundle_price(
        Decimal("10.00"), [_c(1, key="a"), _c(1, key="b"), _c(1, key="c")]
    )
    assert [(x.key, x.allocated) for x in first] == [(x.key, x.allocated) for x in again]
    # 10.00 / 3 = 3.33 each, one cent over, and it goes to the first of the tie.
    assert first[0].allocated == Decimal("3.34")
    assert first[1].allocated == Decimal("3.33")
    assert first[2].allocated == Decimal("3.33")


# --------------------------------------------------------------------------
# Shape and ordering
# --------------------------------------------------------------------------


def test_every_component_gets_exactly_one_line_in_input_order():
    components = [_c(5, key="a"), _c(0, key="b"), _c(15, key="c")]
    lines = allocate_bundle_price(Decimal("40.00"), components)
    assert [line.key for line in lines] == ["a", "b", "c"]


def test_a_zero_priced_component_is_allocated_nothing_but_still_appears():
    lines = allocate_bundle_price(Decimal("100.00"), [_c(0, key="free"), _c(100, key="paid")])
    by_key = {line.key: line.allocated for line in lines}
    assert by_key["free"] == Decimal("0.00")
    assert by_key["paid"] == Decimal("100.00")


def test_unpriced_components_split_equally():
    # No component carries a price, so pro-rata has nothing to work from. An
    # equal split is the only defensible answer, and it still sums exactly.
    lines = allocate_bundle_price(Decimal("100.00"), [_c(None, key="a"), _c(None, key="b")])
    assert [line.allocated for line in lines] == [Decimal("50.00"), Decimal("50.00")]
    assert _total(lines) == Decimal("100.00")


def test_quantity_scales_the_weight():
    # Same unit price, three times the quantity: the line takes three quarters.
    lines = allocate_bundle_price(
        Decimal("100.00"), [_c(10, qty=3, key="many"), _c(10, qty=1, key="one")]
    )
    by_key = {line.key: line.allocated for line in lines}
    assert by_key["many"] == Decimal("75.00")
    assert by_key["one"] == Decimal("25.00")


def test_allocation_is_rounded_to_cents_never_fractions_of_one():
    lines = allocate_bundle_price(Decimal("100.00"), [_c(1), _c(1), _c(1)])
    for line in lines:
        assert line.allocated == line.allocated.quantize(Decimal("0.01"))


# --------------------------------------------------------------------------
# Refusals
# --------------------------------------------------------------------------


def test_a_bundle_with_no_components_is_refused():
    with pytest.raises(ValueError):
        allocate_bundle_price(Decimal("100.00"), [])


def test_a_negative_bundle_price_is_refused():
    with pytest.raises(ValueError):
        allocate_bundle_price(Decimal("-1.00"), [_c(10)])


def test_a_non_positive_quantity_is_refused():
    # A zero-quantity component is a data error, not a free line: silently
    # dropping it would change the bundle without anyone deciding to.
    with pytest.raises(ValueError):
        allocate_bundle_price(Decimal("100.00"), [_c(10, qty=0)])


def test_a_zero_priced_bundle_allocates_zero_to_everything():
    lines = allocate_bundle_price(Decimal("0.00"), [_c(10), _c(20)])
    assert [line.allocated for line in lines] == [Decimal("0.00"), Decimal("0.00")]
    assert _total(lines) == Decimal("0.00")
