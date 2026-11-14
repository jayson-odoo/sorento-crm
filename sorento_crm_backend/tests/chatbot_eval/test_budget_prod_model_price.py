"""CHATBOT-SPEED: the eval meter prices the prod parser model, so a capped live replay on it is metered.

Prod's parser runs on gemini-3.5-flash-lite since 4 Nov (crew stage timings, 12 Nov). `budget.PRICES` priced only
gpt-5.4-mini, so `replay.py live` counted every call at US$0 and stopped after the first item (`unpriced_model`).
The price is the owner-approved row `app/services/analytics_connector/prices.py` seeds; the meter reads it from there.
"""
import pytest

from app.services.analytics_connector.prices import SEED_PRICES
from scripts.chatbot_eval.budget import PRICES, cost_usd


def test_prod_parser_model_is_priced():
    assert "gemini-3.5-flash-lite" in PRICES


def test_price_matches_the_owner_approved_seed():
    inp, cached, out, _source = SEED_PRICES["gemini-3.5-flash-lite"]
    assert PRICES["gemini-3.5-flash-lite"] == (float(inp), float(cached), float(out))
    tokens = {"prompt": 1_000_000, "cached": 0, "output": 0}
    assert cost_usd(tokens, "gemini-3.5-flash-lite") == pytest.approx(float(inp))


def test_existing_eval_prices_are_kept():
    assert PRICES["gpt-5.4-mini"] == (0.75, 0.075, 4.50)
