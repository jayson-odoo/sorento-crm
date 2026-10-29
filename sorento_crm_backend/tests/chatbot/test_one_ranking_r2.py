"""REPORT-SMART-L one ranking, round R2 (AC-OR2): follow-ups on an item ranking refine it.

After an item ranking ("top 10 selling items this year by qty delivered", run on `crm_report_ask`
since R1), "by amount", "ordered", "top 20", "2025" and "sorento only" refine it and keep the rest;
"by customer" runs across all and keeps what is on screen (period, count, measure, basis, a brand
filter on screen), header "Across all products". Each follow-up is parsed both as the parser labels
it today (`top_selling` with rank_by / rank_group fields) and as sales_ranking + ranking_refine.
The State shows the sales ranking frame, never a top_selling line. Fake names and codes only.
"""
from __future__ import annotations

from typing import Any

import pytest

from tests.chatbot.test_engine import _parser_output, stub_access  # noqa: F401
from tests.chatbot.test_report_ask_lane import (  # noqa: F401 - fixtures + helpers
    TOOL,
    _hit,
    _names,
    _rank,
    _say_all,
    console,
)
from tests.chatbot.test_report_smart_s3_period import _record_state
from tests.chatbot.test_report_smart_step7 import KEEP, THIS_YEAR, _state_on

OLD_TOOL = "crm_top_selling_report"
YEAR_2026 = {"date_filter_start": "2026-01-01", "date_filter_end": "2026-12-31"}
LABELS = ["top_selling", "sales_ranking"]
SET_SORT = [{"op": "set", "axis": "sort", "position": None}]


def _item_ranking(*entities: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = dict(
        domain_hint="order", intent_hint="check_order", order_status="top_selling", group_by="product", rank_group="item",
        rank_direction="top", top_n=10, measure="qty", basis="delivered", rank_by="quantity", entities=list(entities),
        domain_in_message=True, state_changes=list(KEEP), **YEAR_2026,
    )
    base.update(overrides)
    return _parser_output(**base)


def _on_screen(console, monkeypatch, *, brand: bool = False) -> None:
    _state_on(console)
    entities = [_hit("sorento", "brand")] if brand else []
    text, log = _say_all(console, monkeypatch, _item_ranking(*entities), "top 10 selling items this year by qty delivered")
    ran = [a for n, a in log if n == TOOL]
    assert OLD_TOOL not in _names(log) and len(ran) == 1, ("setup: the item ranking did not run", text, log)
    assert ran[0]["group_by"] == "product" and ran[0]["top_n"] == 10, ran


def _follow(label: str, **fields: Any) -> dict[str, Any]:
    """A follow-up naming only what changed, under either label."""
    base: dict[str, Any] = dict(
        domain_hint="order", intent_hint="check_order", entities=[], group_by=None, top_n=None, measure=None, basis=None,
        rank_by=None, rank_group=None, domain_in_message=False, state_changes=list(SET_SORT),
        date_filter_start=None, date_filter_end=None,
    )
    if label == "top_selling":
        base.update(order_status="top_selling")
    else:
        base.update(order_status="sales_ranking", ranking_refine=True)
    base.update(fields)
    return _parser_output(**base)


def _run(console, monkeypatch, qf: dict[str, Any], body: str) -> tuple[str, dict[str, Any]]:
    text, log = _say_all(console, monkeypatch, qf, body)
    assert OLD_TOOL not in _names(log), _names(log)
    ran = [a for n, a in log if n == TOOL]
    assert len(ran) == 1, (text, log)  # one run, never a question
    return text, ran[0]


def _held(args: dict[str, Any], **changed: Any) -> None:
    want = {"group_by": "product", "top_n": 10, "measure": "qty", "basis": "delivered",
            "date_from": "2026-01-01", "date_to": "2026-12-31", **changed}
    for key, value in want.items():
        assert args.get(key) == value, (key, args)


# ---------------------------------------------------------------- 1. refines


@pytest.mark.parametrize("label", LABELS)
def test_r2_1_by_amount_changes_only_the_measure(console, monkeypatch, label) -> None:
    _on_screen(console, monkeypatch)
    qf = _follow(label, rank_by="amount") if label == "top_selling" else _follow(label, measure="amount")
    _text, args = _run(console, monkeypatch, qf, "by amount")
    _held(args, measure="amount")


@pytest.mark.parametrize("label", LABELS)
def test_r2_1_ordered_changes_only_the_basis(console, monkeypatch, label) -> None:
    _on_screen(console, monkeypatch)
    _text, args = _run(console, monkeypatch, _follow(label, basis="ordered"), "ordered")
    _held(args, basis="ordered")


@pytest.mark.parametrize("label", LABELS)
def test_r2_1_top_20_changes_only_the_count(console, monkeypatch, label) -> None:
    _on_screen(console, monkeypatch)
    _text, args = _run(console, monkeypatch, _follow(label, top_n=20), "top 20")
    _held(args, top_n=20)


@pytest.mark.parametrize("label", LABELS)
def test_r2_1_2025_changes_only_the_period(console, monkeypatch, label) -> None:
    _on_screen(console, monkeypatch)
    qf = _follow(label, date_filter_start="2025-01-01", date_filter_end="2025-12-31")
    _text, args = _run(console, monkeypatch, qf, "2025")
    _held(args, date_from="2025-01-01", date_to="2025-12-31")


@pytest.mark.parametrize("label", LABELS)
def test_r2_1_sorento_only_adds_the_brand_filter(console, monkeypatch, label) -> None:
    _on_screen(console, monkeypatch)
    _text, args = _run(console, monkeypatch, _follow(label, entities=[_hit("sorento", "brand")]), "sorento only")
    _held(args)
    assert args.get("brand_ids") == [console.ids["brand"]], args


# ---------------------------------------------------------------- 2. by customer: across all


@pytest.mark.parametrize("brand", [False, True])
@pytest.mark.parametrize("label", LABELS)
def test_r2_2_by_customer_runs_across_all_products_and_keeps_what_is_on_screen(console, monkeypatch, label, brand) -> None:
    _on_screen(console, monkeypatch, brand=brand)
    qf = _follow(label, group_by="customer", ranking_drill=None)
    if label == "sales_ranking":
        qf["ranking_refine"] = False
    text, args = _run(console, monkeypatch, qf, "by customer")
    _held(args, group_by="customer")
    assert "Across all products" in text, text
    if brand:
        assert args.get("brand_ids") == [console.ids["brand"]], args  # the brand filter on screen is held


# ---------------------------------------------------------------- 3. State


def test_r2_3_the_state_shows_the_sales_ranking_frame_and_no_top_selling_line(console, monkeypatch) -> None:
    _state_on(console)
    shown = _record_state(console)
    _say_all(console, monkeypatch, _item_ranking(), "top 10 selling items this year by qty delivered")
    _say_all(console, monkeypatch, _follow("top_selling", rank_by="amount"), "by amount")
    state_text = shown[-1]
    assert "sales_ranking_frame" in state_text, state_text
    assert "top_selling" not in state_text, state_text
    assert not (console.session_vars.get("focus") or {}).get("top_selling"), console.session_vars.get("focus")


# ---------------------------------------------------------------- 4. after a non-product ranking


def test_r2_4_a_top_selling_labelled_by_amount_refines_the_agent_ranking_never_a_product_axis(console, monkeypatch) -> None:
    _state_on(console)
    text, calls = console.say(
        _rank(top_n=5, measure="qty", basis="delivered", state_changes=list(KEEP), **THIS_YEAR), "top 5 salesman this year")
    assert len(calls) == 1 and calls[0]["group_by"] == "sales_agent", ("setup", text, calls)
    text, args = _run(console, monkeypatch, _follow("top_selling", rank_by="amount"), "by amount")
    assert args["group_by"] == "sales_agent" and args["measure"] == "amount" and args["top_n"] == 5, args
    assert args["basis"] == "delivered" and args["date_from"] == "2026-01-01", args


# ---------------------------------------------------------------- 5. guards


def test_r2_5_guard_a_fresh_top_5_salesman_is_unchanged(console) -> None:
    text, calls = console.say(
        _rank(top_n=5, measure="qty", basis="delivered", state_changes=list(KEEP), **THIS_YEAR), "top 5 salesman this year")
    assert len(calls) == 1 and calls[0]["group_by"] == "sales_agent" and calls[0]["top_n"] == 5, (text, calls)


def test_r2_5_guard_total_sales_this_month_is_the_report_ask_not_the_sales_report_tool(console, monkeypatch) -> None:
    from tests.chatbot.test_report_ask_lane import SEP

    # REPORT-UNIFY (Q1): a sales total is `crm_report_ask` too (no axis, both measures, the basis named).
    text, log = _say_all(
        console, monkeypatch,
        _parser_output(domain_hint="order", intent_hint="check_order", order_status="sales_report", group_by=None,
                       top_n=None, measure=None, basis="delivered", entities=[], domain_in_message=True, **SEP),
        "total sales this month")
    assert TOOL in _names(log) and "crm_sales_report" not in _names(log), (text, log)


# ---------------------------------------------------------------- review: a bare top-selling ask and an unusable frame

BARE_ASK = dict(group_by=None, rank_group=None, top_n=10, rank_by="quantity", measure=None, basis="delivered",
                entities=[], domain_in_message=True, **YEAR_2026)


def _bare_top_selling() -> dict[str, Any]:
    return _parser_output(domain_hint="order", intent_hint="check_order", order_status="top_selling",
                          rank_direction="top", state_changes=list(KEEP), **BARE_ASK)


def _hold_agent_ranking(console) -> None:
    """Top 5 sales agents for a product, dealer sales, 2026: a ranking with a product and a channel."""
    from tests.chatbot.test_report_ask_lane import PRODUCT_CODE, _e

    text, calls = console.say(
        _rank(_e(PRODUCT_CODE, "product"), top_n=5, measure="qty", basis="delivered", sales_channel="dealer",
              state_changes=list(KEEP), **THIS_YEAR),
        f"top 5 salesppl in 2026 for {PRODUCT_CODE}, dealer sales")
    assert len(calls) == 1, ("setup: the agent ranking did not run", text, calls)


def _fresh_product_ranking(console, monkeypatch) -> None:
    text, log = _say_all(console, monkeypatch, _bare_top_selling(), "top 10 selling this year")
    ran = [a for n, a in log if n == TOOL]
    assert OLD_TOOL not in _names(log) and len(ran) == 1, (text, log)
    args = ran[0]
    assert args["group_by"] == "product" and args["top_n"] == 10, args
    assert not args.get("product_code") and not args.get("channel"), args  # the old ranking's choices are not held


def test_r2_review_a_bare_top_selling_ask_after_a_stale_frame_is_a_fresh_product_ranking(console, monkeypatch) -> None:
    from tests.chatbot.test_report_smart_owner_1022 import FAILED_ASKS

    _state_on(console)
    _hold_agent_ranking(console)
    text, calls = console.say(FAILED_ASKS["unknown_axis"](), "top 5 for zzt")
    assert calls == [], ("setup: the failing ask ran", text, calls)
    _fresh_product_ranking(console, monkeypatch)


def test_r2_review_a_bare_top_selling_ask_after_a_ranking_with_no_rows_is_a_fresh_product_ranking(console, monkeypatch) -> None:
    from tests.chatbot import test_report_ask_lane as lane_tests

    _state_on(console)
    real = lane_tests._fake_body
    monkeypatch.setattr(lane_tests, "_fake_body", lambda args: {**real(args), "rows": [], "total_count": 0})
    _hold_agent_ranking(console)
    monkeypatch.setattr(lane_tests, "_fake_body", real)
    _fresh_product_ranking(console, monkeypatch)


def test_r2_review_guard_a_bare_top_selling_ask_with_nothing_held_is_a_fresh_product_ranking(console, monkeypatch) -> None:
    _state_on(console)
    _fresh_product_ranking(console, monkeypatch)


def test_r2_review_guard_a_bare_top_selling_ask_refines_a_shown_agent_ranking(console, monkeypatch) -> None:
    from tests.chatbot.test_report_ask_lane import PRODUCT_CODE

    _state_on(console)
    _hold_agent_ranking(console)
    text, log = _say_all(console, monkeypatch, _bare_top_selling(), "top 10 selling this year")
    ran = [a for n, a in log if n == TOOL]
    assert len(ran) == 1, (text, log)
    assert ran[0]["group_by"] == "sales_agent" and ran[0]["top_n"] == 10, ran
    assert ran[0].get("product_code") == PRODUCT_CODE and ran[0].get("channel") == "dealer", ran
