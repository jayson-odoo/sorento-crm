"""One currency to compare in, and an honest silence when we cannot.

The purchase-order book prices in four currencies: 8438 lines in USD, 4186 in MYR, 304 in
CNY, 11 in EUR. 892 of the 1051 SKUs with more than one priced supplier have those suppliers
priced in DIFFERENT currencies. So "pick the cheapest" was comparing 45 against 190 and
calling the 45 cheaper without asking 45 of what, and `cash_impact` was adding those numbers
into a single ringgit budget.

Conversion is the fix, but a fabricated rate is worse than no rate: it turns "we do not know"
into a confident wrong number that a buyer commits money against. So every function here
returns the converted amount AND the rate it used, and returns None rather than guess.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.services.scm.money import BASE_CURRENCY, Rate, to_base


def _rates(**kw) -> dict[str, Rate]:
    return {c: Rate(currency=c, rate_to_base=r, as_of=date(2026, 8, 1))
            for c, r in kw.items()}


def test_the_base_currency_needs_no_rate_and_is_never_scaled():
    """MYR is what the budget is written in, so it converts to itself."""
    got = to_base(100, BASE_CURRENCY, {})

    assert got.amount == 100
    assert got.rate == 1
    assert got.currency == BASE_CURRENCY


def test_a_foreign_price_is_converted_at_the_stated_rate():
    got = to_base(45, "USD", _rates(USD=4.4))

    assert got.amount == pytest.approx(198.0)
    assert got.rate == 4.4
    assert got.as_of == date(2026, 8, 1)


def test_a_currency_with_no_rate_converts_to_nothing_rather_than_to_itself():
    """Treating an unconvertible 45 USD as 45 MYR is the exact bug this module exists to
    stop: it is a 4x understatement that looks like a bargain."""
    got = to_base(45, "USD", {})

    assert got.amount is None
    assert got.rate is None
    assert got.missing_currency == "USD"


def test_an_unknown_currency_is_named_so_the_buyer_knows_which_rate_to_add():
    got = to_base(10, "JPY", _rates(USD=4.4))

    assert got.amount is None
    assert got.missing_currency == "JPY"


def test_no_price_converts_to_no_price_and_blames_no_currency():
    """A missing cost is a different problem from a missing rate, and the buyer fixes them
    in different places."""
    got = to_base(None, "USD", _rates(USD=4.4))

    assert got.amount is None
    assert got.missing_currency is None


def test_a_missing_currency_on_a_priced_line_is_read_as_the_base_currency():
    """Old rows carry a price and no currency code. Reading that as base keeps them
    comparable, and it is what the figure already meant when everything was ringgit."""
    got = to_base(80, None, _rates(USD=4.4))

    assert got.amount == 80
    assert got.rate == 1


def test_a_recorded_zero_converts_to_zero_rather_than_to_unknown():
    """Free is a price. It has survived the cascade this far and must survive conversion."""
    got = to_base(0, "USD", _rates(USD=4.4))

    assert got.amount == 0
    assert got.rate == 4.4


def test_case_and_padding_do_not_hide_a_rate():
    got = to_base(45, " usd ", _rates(USD=4.4))

    assert got.amount == pytest.approx(198.0)


def test_a_nonsense_rate_is_refused_rather_than_multiplied_by():
    """A zero or negative rate would silently zero out a real cost, or invert it."""
    for bad in (0, -1):
        got = to_base(45, "USD", _rates(USD=bad))
        assert got.amount is None, f"rate {bad} must not be used"
        assert got.missing_currency == "USD"
