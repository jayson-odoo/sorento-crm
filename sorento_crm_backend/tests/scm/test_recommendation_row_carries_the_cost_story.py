"""The plan row has to carry enough to answer "why this supplier, and in what money".

Two separate omissions, both invisible from the service side:

* The run FROZE `supplier_reason` onto every recommendation and the read serializer never
  emitted it, so the popup that was built to say "chosen because it is cheaper than X"
  rendered nothing at all. The service tests all passed.
* The price and the cash figure are now in two different currencies on purpose - the
  supplier's, and the base one the budget is in - so a row that names neither is unreadable.

`_row` is asserted directly rather than over HTTP: it needs no principal and no seeded run,
and it fails for the one reason that matters, which is a field not reaching the client.
"""
from __future__ import annotations

from app.api.v1.scm.reorder_runs import _row
from app.services.scm.money import BASE_CURRENCY


def _rec(**over):
    row = {
        "id": "rec-1", "rec_type": "buy", "product_id": "p1", "warehouse_id": "w1",
        "net_position": -5, "reorder_point": 0, "days_of_cover": None,
        "rounded_qty": 10, "recommended_qty": 10, "confidence_band": "low",
        "allocation": None, "rank": 1, "rank_score": 1.0,
        "unit_cost": 45, "cash_impact": 1980, "funding_status": "funded",
        "product_code": "SKU-1", "product_name": "SKU-1",
        "warehouse_code": "WH", "warehouse_name": "WH",
        "supplier_code": "S1", "supplier_name": "S1",
        "currency": "USD", "rate_to_base": 4.4, "rate_as_of": None,
        "inputs": {
            "supplier_reason": {"basis": "lowest_cost", "runner_up": "S2",
                                "runner_up_cost": 200.0, "runner_up_cost_base": 200.0,
                                "compared_in": BASE_CURRENCY, "saving_per_unit": 2.0,
                                "missing_rates": []},
        },
    }
    row.update(over)
    return row


def test_the_frozen_supplier_reason_reaches_the_client():
    """Without this the "why this supplier" popup has nothing to render, which is exactly
    how it shipped: frozen correctly, dropped on the way out."""
    got = _row(_rec())

    assert got["supplier_reason"]["basis"] == "lowest_cost"
    assert got["supplier_reason"]["runner_up"] == "S2"
    assert got["supplier_reason"]["saving_per_unit"] == 2.0


def test_the_price_names_its_own_currency():
    """45 rendered as "RM 45" when the supplier charges 45 USD is a 4x understatement
    printed as a fact."""
    got = _row(_rec())

    assert got["unit_cost"] == 45.0
    assert got["currency"] == "USD"


def test_the_cash_figure_names_the_currency_the_budget_is_in():
    """`unit_cost` and `cash_impact` are deliberately in DIFFERENT money: what the supplier
    charges, and what it draws from a ringgit budget. A row that labels only one of them
    invites the reader to assume they match."""
    got = _row(_rec())

    assert got["cash_impact"] == 1980.0
    assert got["base_currency"] == BASE_CURRENCY
    assert got["rate_to_base"] == 4.4


def test_a_missing_rate_is_reported_as_a_missing_rate_not_a_missing_price():
    """The buyer fixes these in two different places, so the row has to say which it is."""
    got = _row(_rec(cash_impact=None, inputs={
        "supplier_reason": {"basis": "lowest_cost", "missing_rates": ["CNY"]},
    }))

    assert got["cost_status"] == "no_rate"
    assert got["missing_rate_currencies"] == ["CNY"]
    assert got["funding_status"] == "needs_cost"      # it still lands in front of a human


def test_an_unpriced_buy_still_reads_as_an_unpriced_buy():
    got = _row(_rec(unit_cost=None, cash_impact=None, currency=None, rate_to_base=None,
                    inputs={}))

    assert got["cost_status"] == "no_cost"
    assert got["missing_rate_currencies"] == []


def test_a_costed_buy_says_nothing_is_wrong_with_its_cost():
    assert _row(_rec())["cost_status"] == "ok"


def test_a_free_buy_is_costed_rather_than_flagged():
    """> "yes it is free but we should buy enough to cover our demand also"

    Zero is a price. It funds at zero and must not be swept into a needs-attention pile.
    """
    got = _row(_rec(unit_cost=0, cash_impact=0))

    assert got["cost_status"] == "ok"
    assert got["cash_impact"] == 0.0


def test_a_disposition_row_carries_no_cost_story_at_all():
    """Nothing is being bought, so a cost status would be an answer to a question nobody
    asked."""
    got = _row(_rec(rec_type="disposition", unit_cost=None, cash_impact=None))

    assert got["cost_status"] is None
    assert got["currency"] is None
