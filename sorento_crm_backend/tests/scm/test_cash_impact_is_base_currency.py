"""The budget is one pot of ringgit, so every buy has to be priced into it.

`cash_impact` fed a single budget figure while `unit_cost` came from a book that is 8438
lines USD, 4186 MYR, 304 CNY and 11 EUR. A 45 USD buy therefore consumed 45 of a ringgit
budget: an understatement of roughly four times, on the currency that dominates the book.
The buyer would have "funded" a plan they could not pay for.

So `cash_impact` is now always in the base currency, and a buy whose price cannot be
converted has NO cash figure rather than a wrong one - which drops it into the same
needs-attention bucket an unpriced buy already lands in, where a human looks at it.
"""
from __future__ import annotations

from datetime import date

from app.services.scm.money import BASE_CURRENCY
from app.services.scm.reorder_run_service import _cash_impact_in_base


def test_a_ringgit_buy_costs_what_it_says():
    got = _cash_impact_in_base(rounded=10, unit_cost=19, currency=BASE_CURRENCY,
                               rate=1.0, rate_as_of=None)

    assert got == 190.0


def test_a_dollar_buy_costs_what_it_converts_to():
    """10 x 45 USD is not 450 ringgit. It is 1980, and the budget has to know that."""
    got = _cash_impact_in_base(rounded=10, unit_cost=45, currency="USD",
                               rate=4.4, rate_as_of=date(2026, 8, 1))

    assert got == 1980.0


def test_a_buy_we_cannot_convert_has_no_cash_figure_rather_than_a_wrong_one():
    """None routes it to needs-attention. A face-value number would route it to "funded"
    at a quarter of its real cost, which is the failure this whole change is about."""
    got = _cash_impact_in_base(rounded=10, unit_cost=45, currency="USD",
                               rate=None, rate_as_of=None)

    assert got is None


def test_an_unpriced_buy_still_has_no_cash_figure():
    assert _cash_impact_in_base(rounded=10, unit_cost=None, currency="USD",
                                rate=None, rate_as_of=None) is None


def test_a_free_buy_costs_zero_rather_than_becoming_unknown():
    """> "if 0 unit cost right, it can mean we haven't purchased before, or it is genuinely
    > free ... we shouldn't skip the planning just because it is free"

    A zero cash impact is a fact, and it funds at zero. Turning it into None would send a
    known-free buy to the needs-attention pile.
    """
    got = _cash_impact_in_base(rounded=10, unit_cost=0, currency="USD",
                               rate=4.4, rate_as_of=None)

    assert got == 0.0


def test_no_quantity_means_no_cash():
    assert _cash_impact_in_base(rounded=None, unit_cost=45, currency="USD",
                                rate=4.4, rate_as_of=None) is None


def test_the_figure_is_rounded_to_money_not_left_as_float_noise():
    """45.1 x 4.4 x 3 is 595.3200000000001 in binary floating point, and the column it lands
    in holds two decimals anyway."""
    got = _cash_impact_in_base(rounded=3, unit_cost=45.1, currency="USD",
                               rate=4.4, rate_as_of=None)

    assert got == 595.32
