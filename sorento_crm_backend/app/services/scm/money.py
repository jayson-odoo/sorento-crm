"""One currency to compare in.

The purchase-order book prices in four currencies, and most SKUs with more than one priced
supplier have those suppliers priced in different ones. Every figure the plan RANKS or SUMS -
which supplier is cheaper, what a buy costs, whether it fits the budget - has to be in a
single currency or it means nothing.

That currency is `BASE_CURRENCY`. The supplier's own price and its currency are kept
alongside, because that is what the buyer will actually pay and what the PO will say; the
converted figure exists to make two prices comparable, not to replace either of them.

The one rule everything else here follows: **a rate we do not have is not a rate of 1.**
Reading an unconvertible 45 USD as 45 MYR understates it fourfold and reads as a bargain, so
`to_base` returns None and names the currency whose rate is missing. The caller then has
something to tell the buyer ("no rate for USD") instead of a wrong number.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

#: What the budget, the cash figures and every ranked comparison are written in. A constant
#: rather than a setting: there is one company, its books are in ringgit, and a configurable
#: base with no second reader is a knob that can only be turned wrong.
BASE_CURRENCY = "MYR"


@dataclass(frozen=True)
class Rate:
    """What one unit of `currency` is worth in `BASE_CURRENCY`, and when that was true."""

    currency: str
    rate_to_base: float
    as_of: Optional[date] = None


@dataclass(frozen=True)
class Converted:
    """A figure in base currency, or an honest account of why there isn't one.

    `amount is None` has two distinct causes and the caller must be able to tell them apart:
    there was no price to convert (`missing_currency is None`), or there was a price in a
    currency we hold no rate for (`missing_currency == "USD"`). The first is fixed by buying
    the item once; the second by entering a rate. Collapsing them into "no cost" sends the
    buyer looking in the wrong place.
    """

    amount: Optional[float]
    currency: str = BASE_CURRENCY
    rate: Optional[float] = None
    as_of: Optional[date] = None
    missing_currency: Optional[str] = None


def normalize_currency(currency: Optional[str]) -> str:
    """Upper-case, trimmed, and empty means base.

    A priced row with no currency code predates the book having more than one currency, so
    the figure already meant ringgit. Reading it as base keeps it comparable instead of
    quarantining it.
    """
    code = (currency or "").strip().upper()
    return code or BASE_CURRENCY


def to_base(amount: Optional[float], currency: Optional[str],
            rates: dict[str, Rate]) -> Converted:
    """Convert `amount` into `BASE_CURRENCY`, or explain why it cannot be."""
    if amount is None:
        return Converted(amount=None)

    code = normalize_currency(currency)
    if code == BASE_CURRENCY:
        return Converted(amount=float(amount), rate=1.0)

    rate = rates.get(code)
    # A zero or negative rate is not a rate: it would zero out a real cost or invert it.
    # Refusing it lands the row in the same "no rate for USD" bucket a missing row does,
    # which is where a buyer can actually act on it.
    if rate is None or not rate.rate_to_base or float(rate.rate_to_base) <= 0:
        return Converted(amount=None, missing_currency=code)

    # Rounded because 45 * 4.4 is 198.00000000000003 in binary floating point, and that
    # noise reaches the screen ("RM 198.00000000000003") and the ranking, where two prices
    # that are equal in money would order by their rounding error.
    return Converted(amount=round(float(amount) * float(rate.rate_to_base), 6),
                     rate=float(rate.rate_to_base), as_of=rate.as_of)


def load_rates(db: Session) -> dict[str, Rate]:
    """Every rate on file, keyed by currency code.

    The base currency is not stored (it is 1 by definition), so a table nobody has filled in
    yet leaves this empty and every foreign price lands in "no rate" rather than silently
    converting at 1.
    """
    rows = db.execute(text(
        "SELECT currency, rate_to_base, as_of FROM scm.currency_rate"
    )).mappings().all()
    out: dict[str, Rate] = {}
    for r in rows:
        code = normalize_currency(r["currency"])
        if code == BASE_CURRENCY:
            continue
        out[code] = Rate(currency=code, rate_to_base=float(r["rate_to_base"]),
                         as_of=r["as_of"])
    return out
