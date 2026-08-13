"""Ordered cost against incoming cost. Pure, no database.

The two figures are `purchase_order_lines.unit_cost` with its currency (what we agreed to
pay, AC-C3.1) and `inbound_shipment_lines.unit_cost` with its currency (what the packing
list says is actually arriving, AC-C3.2). The difference between them is the point: a
supplier whose incoming cost sits above its ordered cost has repriced AFTER we committed,
and that is a fact about the supplier, not a data-entry problem.

**The variance is derived here and stored nowhere** (AC-C3.3). A third column holding it
would go stale the moment either side is corrected, and would then disagree with the two
columns it was computed from, with nothing to say which is right.

**A variance is not always a number, and the honest answer is then not a number.** Two
costs in different currencies do not subtract: 70.00 CNY against 10.00 USD is not a 60.00
anything, and reporting one would invent a saving out of the units being ignored. The same
applies when either cost is missing (an absent cost is not zero; zero reads as free goods)
and when either currency is unknown (two figures cannot be shown to be in the same unit if
one of them does not state its unit). In every one of those cases the result is
`comparable: False` with a `reason` saying which, rather than a figure.

Both figures are ex-works in the supplier's currency. Neither is a landed cost: freight and
duty are not in the purchase order, so nothing here may be presented as one (AC-C3.4).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional


def _normalise_currency(value: Optional[str]) -> Optional[str]:
    """A 3-letter code, or None. Blank and whitespace are absence, not a currency."""
    if value is None:
        return None
    text = str(value).strip().upper()
    return text or None


def _to_decimal(value: Any) -> Optional[Decimal]:
    """Decimal, or None. Via str so a float never carries binary error into money."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def cost_variance(
    ordered_cost: Any,
    ordered_currency: Optional[str],
    incoming_cost: Any,
    incoming_currency: Optional[str],
) -> dict:
    """Compare an ordered cost with an incoming cost.

    Returns a dict with:

    * ``variance``   - ``incoming - ordered`` as a Decimal, so a POSITIVE number means the
      supplier repriced upward after we committed. ``None`` whenever the comparison is not
      computable.
    * ``currency``   - the unit the variance is expressed in. Where the two sides disagree
      there is no such unit, so it is ``None``; where only one side states a currency it is
      reported as context for whichever figure is present.
    * ``comparable`` - whether ``variance`` is a real number.
    * ``reason``     - why not, when it is not. ``None`` when the variance is comparable.
    """
    ordered = _to_decimal(ordered_cost)
    incoming = _to_decimal(incoming_cost)
    ordered_ccy = _normalise_currency(ordered_currency)
    incoming_ccy = _normalise_currency(incoming_currency)

    def _not_comparable(currency: Optional[str], reason: str) -> dict:
        return {
            "variance": None,
            "currency": currency,
            "comparable": False,
            "reason": reason,
        }

    # A missing cost is the more fundamental absence, so it is reported before any currency
    # question: there is nothing to state a unit for in the first place.
    if ordered is None and incoming is None:
        return _not_comparable(
            ordered_ccy or incoming_ccy,
            "neither an ordered cost nor an incoming cost is recorded, so there is "
            "nothing to compare",
        )
    if ordered is None:
        return _not_comparable(
            incoming_ccy,
            "no ordered cost is recorded for this line, so the incoming cost has "
            "nothing to be compared against",
        )
    if incoming is None:
        return _not_comparable(
            ordered_ccy,
            "no incoming cost is recorded on the packing-list line, so there is nothing "
            "to compare with the ordered cost",
        )

    if ordered_ccy and incoming_ccy and ordered_ccy != incoming_ccy:
        return _not_comparable(
            None,
            f"the ordered cost is in {ordered_ccy} and the incoming cost is in "
            f"{incoming_ccy}; two currencies do not subtract, so no variance exists "
            "until one is converted",
        )
    if ordered_ccy is None or incoming_ccy is None:
        # Deliberately strict. Assuming the unknown side matches the known one is the same
        # act as inventing a currency, and it is what makes a variance meaningful, so it is
        # refused rather than assumed.
        missing = "ordered" if ordered_ccy is None else "incoming"
        return _not_comparable(
            ordered_ccy or incoming_ccy,
            f"the {missing} cost states no currency, so it cannot be shown to be in the "
            "same unit as the other figure",
        )

    return {
        "variance": incoming - ordered,
        "currency": ordered_ccy,
        "comparable": True,
        "reason": None,
    }
