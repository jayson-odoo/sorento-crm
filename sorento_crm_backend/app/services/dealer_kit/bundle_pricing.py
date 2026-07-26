"""Bundle price allocation (AC-F11).

A Bundle carries ONE price, but an order needs a figure per component line. This
splits the former into the latter.

Pure arithmetic on purpose - no session, no models. It is the piece that must be
exactly right, so it is the piece with nothing else in it.

**The invariant:** the allocated lines sum EXACTLY to the bundle price. Not
"within a cent". A pro-rata split of 100.00 across three equal components gives
33.333... each, and rounding each independently yields 99.99. That missing cent
would be invoiced differently from the price the customer agreed to, and the
discrepancy would surface in accounting weeks later with nobody able to explain
it. So the rounding remainder is not dropped: it is assigned to the largest
line, which is both the least noticeable place to put it and a deterministic
one.

Work is done in integer cents. Allocating in Decimal and rounding at the end
reintroduces exactly the float-adjacent error this exists to prevent.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional, Sequence

_CENTS = Decimal("0.01")


@dataclass(frozen=True)
class BundleComponentInput:
    """One component going in. ``key`` is whatever the caller uses to identify a
    line (a product id, a row id); it is echoed back untouched."""

    key: str
    list_price: Optional[Decimal]
    quantity: int = 1


@dataclass(frozen=True)
class AllocatedLine:
    key: str
    allocated: Decimal


def _to_cents(amount: Decimal) -> int:
    return int(amount.quantize(_CENTS, rounding=ROUND_HALF_UP) * 100)


def allocate_bundle_price(
    bundle_price: Decimal, components: Sequence[BundleComponentInput]
) -> list[AllocatedLine]:
    """Split ``bundle_price`` across ``components``, pro-rata by list price.

    Returns one line per component, in input order. The lines always sum to
    ``bundle_price`` exactly.
    """
    if not components:
        raise ValueError("A bundle must have at least one component to allocate across")
    if bundle_price < 0:
        raise ValueError("A bundle price cannot be negative")
    for component in components:
        if component.quantity <= 0:
            raise ValueError(
                f"Component '{component.key}' has quantity {component.quantity}; "
                "a component must have a positive quantity"
            )

    total_cents = _to_cents(bundle_price)

    # Weight is unit price x quantity. Two of the same tap weigh twice one.
    weights = [
        _to_cents(component.list_price or Decimal("0")) * component.quantity
        for component in components
    ]
    total_weight = sum(weights)

    if total_weight == 0:
        # Nothing carries a price, so pro-rata has no signal to work from. An
        # equal split is the only defensible answer - and it must still land on
        # the exact total, so it goes through the same remainder pass below.
        weights = [1] * len(components)
        total_weight = len(components)

    # Floor each share, then hand the leftover cents to the largest line. Doing
    # it this way means the leftover is always non-negative and strictly smaller
    # than the number of lines, so one line can absorb all of it.
    shares = [total_cents * weight // total_weight for weight in weights]
    remainder = total_cents - sum(shares)

    if remainder:
        # max() returns the FIRST maximal element, so a tie resolves by position
        # and the same input always produces the same output.
        largest = max(range(len(weights)), key=lambda i: weights[i])
        shares[largest] += remainder

    return [
        AllocatedLine(key=component.key, allocated=(Decimal(share) / 100).quantize(_CENTS))
        for component, share in zip(components, shares)
    ]
