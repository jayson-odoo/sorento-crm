"""Cheapest means cheapest, not "smallest number".

> "our cost should come from PO history, and we should pick the cheapest one if got
> multiple suppliers ... in the popup, should show the alternative supplier with its cost
> and why we chosen what we have chose because it is cheaper"

The book prices in four currencies. 892 of the 1051 SKUs with more than one priced supplier
have those suppliers priced in DIFFERENT ones, so on the great majority of the comparisons
this feature exists to make, ranking the raw figures picks the wrong supplier and then tells
the buyer, in writing, that it is cheaper.

These pin the three outcomes: both convertible (compare properly), one not (rank it last and
say why), neither (fall back to a basis we can defend).
"""
from __future__ import annotations

from datetime import date

from app.services.scm.money import BASE_CURRENCY, Rate
from app.services.scm.reorder_engine import price_in_base, select_supplier

RATES = {"USD": Rate(currency="USD", rate_to_base=4.4, as_of=date(2026, 8, 1))}


def _s(sid, cost, currency, **kw):
    row = {"supplier_id": sid, "supplier_name": sid, "unit_cost": cost,
           "currency": currency, "composite_score": None, "is_primary": False,
           "lead_time_days": 30.0}
    row.update(kw)
    return price_in_base(row, RATES)


# --------------------------------------------------------------------------- #
# comparison
# --------------------------------------------------------------------------- #

def test_the_cheaper_supplier_wins_after_conversion_not_before():
    """45 USD is 198 ringgit, so the 190-ringgit supplier is the cheap one. Ranking the raw
    figures picks the USD supplier and calls a 4% overpay a saving."""
    usd = _s("USD-CO", 45, "USD")
    myr = _s("MYR-CO", 190, BASE_CURRENCY)

    got = select_supplier([usd, myr], selection="lowest_cost")

    assert got["chosen"]["supplier_id"] == "MYR-CO"
    assert got["reason"]["basis"] == "lowest_cost"
    assert got["reason"]["runner_up"] == "USD-CO"


def test_the_saving_is_quoted_in_the_currency_it_was_compared_in():
    """A saving of "8" is meaningless when the two prices were in different money."""
    got = select_supplier([_s("USD-CO", 45, "USD"), _s("MYR-CO", 190, BASE_CURRENCY)],
                          selection="lowest_cost")

    reason = got["reason"]
    assert reason["saving_per_unit"] == 8.0            # 198.00 - 190.00
    assert reason["compared_in"] == BASE_CURRENCY
    assert reason["runner_up_cost_base"] == 198.0


def test_the_suppliers_own_price_is_kept_beside_the_converted_one():
    """The PO will be written in the supplier's currency and the buyer will pay that
    figure, so the conversion must not overwrite it."""
    chosen = select_supplier([_s("USD-CO", 45, "USD")], selection="lowest_cost")["chosen"]

    assert chosen["unit_cost"] == 45
    assert chosen["currency"] == "USD"
    assert chosen["unit_cost_base"] == 198.0
    assert chosen["rate_to_base"] == 4.4
    assert chosen["rate_as_of"] == date(2026, 8, 1)


# --------------------------------------------------------------------------- #
# what happens when we cannot compare
# --------------------------------------------------------------------------- #

def test_an_unconvertible_price_never_outranks_one_we_can_read():
    """A 10 CNY price with no CNY rate is not "the cheapest at 10". It is unknown, and an
    unknown must not win a comparison by looking small."""
    cny = _s("CNY-CO", 10, "CNY")
    myr = _s("MYR-CO", 190, BASE_CURRENCY)

    got = select_supplier([cny, myr], selection="lowest_cost")

    assert got["chosen"]["supplier_id"] == "MYR-CO"
    assert cny["unit_cost_base"] is None
    assert cny["missing_rate_currency"] == "CNY"


def test_the_missing_rate_is_named_on_the_choice_so_the_buyer_can_fix_it():
    got = select_supplier([_s("CNY-CO", 10, "CNY"), _s("MYR-CO", 190, BASE_CURRENCY)],
                          selection="lowest_cost")

    assert got["reason"]["missing_rates"] == ["CNY"]


def test_no_saving_is_claimed_against_a_price_we_could_not_convert():
    """The gap to an unreadable price is unknowable, and a number here would be invented."""
    got = select_supplier([_s("MYR-CO", 190, BASE_CURRENCY), _s("CNY-CO", 10, "CNY")],
                          selection="lowest_cost")

    assert got["reason"]["saving_per_unit"] is None


def test_when_nothing_can_be_converted_the_basis_says_so_rather_than_lying():
    """Two prices in two currencies we hold no rates for cannot be ranked by cost at all.
    Saying "lowest cost" here would be a claim we cannot support."""
    got = select_supplier([_s("CNY-CO", 10, "CNY"), _s("EUR-CO", 9, "EUR")],
                          selection="lowest_cost")

    assert got["reason"]["basis"] == "no_comparable_cost"
    assert got["reason"]["saving_per_unit"] is None
    assert sorted(got["reason"]["missing_rates"]) == ["CNY", "EUR"]


def test_the_choice_is_still_made_rather_than_the_sku_being_dropped():
    """> "we shouldn't skip the planning just because it is free"

    The same holds for a price we cannot read: the demand is real either way, so the plan
    keeps the line and tells the buyer what is missing.
    """
    got = select_supplier([_s("CNY-CO", 10, "CNY"), _s("EUR-CO", 9, "EUR")],
                          selection="lowest_cost")

    assert got["chosen"] is not None
    assert got["exception"] is None


def test_a_free_item_is_still_the_cheapest_and_still_converts():
    """Zero is a price, and it survives the conversion as zero."""
    got = select_supplier([_s("FREE-CO", 0, "USD"), _s("MYR-CO", 190, BASE_CURRENCY)],
                          selection="lowest_cost")

    assert got["chosen"]["supplier_id"] == "FREE-CO"
    assert got["chosen"]["unit_cost_base"] == 0.0


def test_a_supplier_with_no_price_at_all_still_ranks_last():
    """Unpriced was already last, and conversion must not promote it."""
    got = select_supplier([_s("NOCOST", None, "USD"), _s("MYR-CO", 190, BASE_CURRENCY)],
                          selection="lowest_cost")

    assert got["chosen"]["supplier_id"] == "MYR-CO"
    assert got["reason"]["missing_rates"] == []       # no price is not a missing rate


# --------------------------------------------------------------------------- #
# the other selection modes still rank on what they rank on
# --------------------------------------------------------------------------- #

def test_the_primary_supplier_still_wins_under_the_primary_mode():
    got = select_supplier(
        [_s("USD-CO", 45, "USD"), _s("MYR-CO", 190, BASE_CURRENCY, is_primary=True)],
        selection="primary")

    assert got["chosen"]["supplier_id"] == "MYR-CO"


def test_cost_breaks_a_score_tie_in_base_currency():
    got = select_supplier(
        [_s("USD-CO", 45, "USD", composite_score=0.8),
         _s("MYR-CO", 190, BASE_CURRENCY, composite_score=0.8)],
        selection="best_score")

    assert got["chosen"]["supplier_id"] == "MYR-CO"
