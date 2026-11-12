"""The costing arithmetic, pure and in Decimal at full precision (contract section 1).

Nothing here rounds except `display2`, which the page and the Excel use for what the eye sees.
Landing is `unit_cost * rate * sst`, THEN the transport (`+ value` or `* value`): adding before
SST would tax the freight.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Optional, Union

Number = Union[Decimal, int, float, str]

ZERO = Decimal(0)
HUNDRED = Decimal(100)
_TWO_PLACES = Decimal("0.01")


def to_decimal(value: Number) -> Decimal:
    """A Decimal from anything a caller holds. A float goes through `str`, so 0.1 stays 0.1."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def landing(
    unit_cost: Number,
    rate_to_base: Number,
    sst_factor: Number,
    transport_mode: Optional[str],
    transport_value: Optional[Number],
) -> Decimal:
    """MYR landing cost of one unit. No transport rule (mode or value None) adds 0."""
    base = to_decimal(unit_cost) * to_decimal(rate_to_base) * to_decimal(sst_factor)
    if transport_mode is None or transport_value is None:
        return base
    value = to_decimal(transport_value)
    if transport_mode == "add":
        return base + value
    if transport_mode == "multiply":
        return base * value
    raise ValueError(f"unknown transport mode {transport_mode!r}")


def party_final(landing_cost: Number, markup_pct: Number) -> Decimal:
    """What a party pays: landing plus its mark-up."""
    return to_decimal(landing_cost) * (1 + to_decimal(markup_pct) / HUNDRED)


def achieved_markup(list_price: Number, landing_cost: Number) -> Decimal:
    """The mark-up the AutoCount list price achieves over landing, in percent."""
    cost = to_decimal(landing_cost)
    return (to_decimal(list_price) - cost) / cost * HUNDRED


def margin(list_price: Number, final: Number) -> Decimal:
    """How far the list price sits above a party's final price, in percent of that price."""
    price = to_decimal(final)
    return (to_decimal(list_price) - price) / price * HUNDRED


def display2(value: Number) -> Decimal:
    """Two decimal places, half up: what the page and the Excel show."""
    return to_decimal(value).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
