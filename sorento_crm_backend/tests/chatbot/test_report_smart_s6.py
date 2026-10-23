"""REPORT-SMART-L round S6 (owner ruling B, 23 Oct): after a ranking a new axis runs across all.

With "Top N of M sales agents by delivered sales" on screen, a message ranking a new axis with
`ranking_drill` null, unsure or global runs across all and its header says "Across all sales
agents"; `scoped` narrows to the rows on screen as before. Fake names and codes only.
"""
from __future__ import annotations

from typing import Any

import pytest

from tests.chatbot import test_report_ask_lane as lane_tests
from tests.chatbot.test_engine import _parser_output, stub_access  # noqa: F401
from tests.chatbot.test_report_ask_lane import PRODUCT_CODE, _e, _rank, _refine, console  # noqa: F401
from tests.chatbot.test_report_drilldown_lane import AG1, AG2, _body, _drill
from tests.chatbot.test_report_smart_step7 import KEEP, THIS_YEAR

ACROSS_ALL = "Across all sales agents"
SCOPE_QUESTION_BITS = ("of the 3 sales agents above", "or across all")
KEYS = [AG1, AG2, "none"]


@pytest.fixture(autouse=True)
def _route_body(monkeypatch):
    monkeypatch.setattr(lane_tests, "_fake_body", _body)


def _ranking(console) -> None:
    """'Top 5 sales agents for the product, dealer sales, 2026': the ranking on screen."""
    text, calls = console.say(
        _rank(_e(PRODUCT_CODE, "product"), top_n=5, measure="qty", basis="delivered", sales_channel="dealer",
              state_changes=list(KEEP), **THIS_YEAR),
        f"top 5 salesppl in 2026 for {PRODUCT_CODE}, dealer sales",
    )
    assert len(calls) == 1, ("setup: the ranking did not run", text, calls)


def _by_customer(**overrides: Any) -> dict[str, Any]:
    """'by customer' with its own count, measure, basis and period, so only the scope is in question."""
    base: dict[str, Any] = dict(
        group_by="customer", top_n=10, measure="qty", basis="delivered", state_changes=list(KEEP),
        ranking_drill=None, **THIS_YEAR,
    )
    base.update(overrides)
    return _drill(**base)


def _runs_across_all(text: str, calls: list[dict[str, Any]]) -> None:
    assert len(calls) == 1, (text, calls)
    args = calls[0]
    assert args["group_by"] == "customer", args
    assert not args.get("sales_agent_ids") and not args.get("customer_agent_ids"), args  # not narrowed to the 5 agents
    assert ACROSS_ALL in text, text
    assert not any(bit in text for bit in SCOPE_QUESTION_BITS), text


def test_s6_1_a_new_axis_with_no_drill_reading_runs_across_all_and_says_so(console) -> None:
    _ranking(console)
    text, calls = console.say(_by_customer(ranking_drill=None), "by customer")
    _runs_across_all(text, calls)


def test_s6_2_a_new_axis_read_as_unsure_runs_across_all_and_says_so(console) -> None:
    _ranking(console)
    text, calls = console.say(_by_customer(ranking_drill="unsure"), "by customer")
    _runs_across_all(text, calls)


def test_s6_3_a_new_axis_read_as_global_runs_across_all_and_says_so(console) -> None:
    _ranking(console)
    text, calls = console.say(_by_customer(ranking_drill="global"), "top 10 customers overall")
    _runs_across_all(text, calls)


def test_s6_4_guard_scoped_narrows_to_the_agents_on_screen_with_no_across_all_line(console) -> None:
    _ranking(console)
    text, calls = console.say(_by_customer(ranking_drill="scoped"), "their customers")
    (args,) = calls
    assert args["group_by"] == "customer" and args["customer_agent_ids"] == KEYS, args
    assert ACROSS_ALL not in text, text


def test_s6_5_guard_a_same_axis_refine_carries_no_across_all_line(console) -> None:
    _ranking(console)
    text, calls = console.say(_refine(sales_channel="dealer", group_by="sales_agent", top_n=5,
                                      state_changes=list(KEEP)), "Dealer sales only")
    assert len(calls) == 1 and calls[0]["group_by"] == "sales_agent", (text, calls)
    assert ACROSS_ALL not in text, text


def test_s6_5_guard_a_fresh_ask_with_no_ranking_shown_carries_no_across_all_line(console) -> None:
    text, calls = console.say(_by_customer(ranking_drill=None), "top 10 customers this year by qty")
    assert len(calls) == 1 and calls[0]["group_by"] == "customer", (text, calls)
    assert ACROSS_ALL not in text, text


def test_s6_5_guard_a_scope_slot_already_held_is_still_answered(console) -> None:
    _ranking(console)
    period = {"value": {"from": "2026-01-01", "to": "2026-12-31"}, "label": "2026"}
    base = {"group_by": "customer", "sort": "desc", "basis": "delivered", "measure": "qty"}
    slot = {"ask": "sales_ranking", "values": {}, "asking": "scope", "options": [], "misses": 0, "extras": {"scope": {
        "question": "Top 10 customers of the 3 sales agents above, or across all customers?",
        "source": "sales_agent",
        "scoped": {"args": {**base, "customer_agent_ids": KEYS, "product_code": PRODUCT_CODE}, "top_n": 10,
                   "period": period, "held": True},
        "global": {"args": dict(base), "top_n": 10, "period": period, "held": False},
    }}}
    console.session_vars["focus"]["required_ask"] = slot
    text, calls = console.say(_by_customer(ranking_drill="scoped"), "the agents above")
    (args,) = calls
    assert args["group_by"] == "customer" and args["customer_agent_ids"] == KEYS, args


# ---------------------------------------------------------------- S6b: across all keeps product, channel and year


def _bare_new_axis(reading: Any, **overrides: Any) -> dict[str, Any]:
    """'by customer': the parse names no period, product or channel (the held ones are not retyped)."""
    base: dict[str, Any] = dict(
        group_by="customer", top_n=5, measure="qty", basis="delivered", state_changes=list(KEEP),
        ranking_drill=reading, date_filter_start=None, date_filter_end=None,
    )
    base.update(overrides)
    return _drill(**base)


@pytest.mark.parametrize("reading", [None, "unsure", "global"])
def test_s6b_1_across_all_keeps_the_product_channel_and_year_on_screen_and_asks_nothing(console, reading) -> None:
    _ranking(console)
    text, calls = console.say(_bare_new_axis(reading), "by customer")
    assert len(calls) == 1, (text, calls)  # no "Which period?" or any other question
    args = calls[0]
    assert args["group_by"] == "customer", args
    assert args.get("product_code") == PRODUCT_CODE and args.get("channel") == "dealer", args
    assert args["date_from"] == "2026-01-01" and args["date_to"] == "2026-12-31", args
    assert not args.get("sales_agent_ids") and not args.get("customer_agent_ids"), args
    assert ACROSS_ALL in text and "Which period" not in text, text


def test_s6b_2_a_period_the_message_names_replaces_the_held_one_product_and_channel_kept(console) -> None:
    _ranking(console)
    text, calls = console.say(
        _bare_new_axis(None, date_filter_start="2025-01-01", date_filter_end="2025-12-31"), "by customer last year")
    assert len(calls) == 1, (text, calls)
    args = calls[0]
    assert args["date_from"] == "2025-01-01" and args["date_to"] == "2025-12-31", args
    assert args.get("product_code") == PRODUCT_CODE and args.get("channel") == "dealer", args
    assert ACROSS_ALL in text, text


def test_s6b_4_guard_scoped_still_narrows_to_the_agents_on_screen(console) -> None:
    _ranking(console)
    text, calls = console.say(_bare_new_axis("scoped"), "their customers")
    (args,) = calls
    assert args["customer_agent_ids"] == KEYS and args.get("product_code") == PRODUCT_CODE, args
    assert ACROSS_ALL not in text, text
