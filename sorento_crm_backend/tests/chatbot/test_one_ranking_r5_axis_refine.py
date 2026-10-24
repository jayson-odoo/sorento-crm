"""REPORT-SMART-L R5 a3 (EVAL-BENCH live turn c404da24): a held sales TOTAL frame, "by salesppl" opens the
How many? question, and "by customer" (a refine naming another axis, filling nothing) swaps into the
open ask (filters kept), not the count answer. Real engine seam, the shapes the live parser emitted. Fake codes only."""
from __future__ import annotations

from typing import Any

import pytest

from tests.chatbot.test_engine import _parser_output, stub_access  # noqa: F401
from tests.chatbot.test_report_ask_lane import (  # noqa: F401 - fixtures + helpers
    PRODUCT_CODE,
    TOOL,
    _e,
    _names,
    _say_all,
    console,
)
from tests.chatbot.test_report_smart_step7 import KEEP, _state_on

YEAR_2026 = {"date_filter_start": "2026-01-01", "date_filter_end": "2026-12-31"}
YEAR_2025 = {"date_filter_start": "2025-01-01", "date_filter_end": "2025-12-31"}
SET = [{"op": "set", "axis": None, "position": None}]


def _verdict(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = dict(
        domain_hint="order", intent_hint="check_order", order_status="sales_ranking", ranking_refine=True,
        group_by=None, top_n=None, measure=None, basis=None, entities=[], domain_in_message=False,
        state_changes=list(SET), date_filter_start=None, date_filter_end=None,
    )
    base.update(over)
    return _parser_output(**base)


def _open_how_many(console, monkeypatch) -> None:
    """A total for a product (no group_by) is held, then 'by salesppl' leaves How many? open."""
    _state_on(console)
    text, log = _say_all(
        console, monkeypatch,
        _parser_output(domain_hint="order", intent_hint="check_order", order_status="sales_ranking", ranking_refine=False,
                       group_by=None, top_n=None, measure="qty", basis="delivered", entities=[_e(PRODUCT_CODE, "product")],
                       domain_in_message=True, state_changes=list(KEEP), **YEAR_2026),
        f"total qty of {PRODUCT_CODE} in 2026 delivered")
    print("TOTAL", text, log)
    text, log = _say_all(console, monkeypatch, _verdict(group_by="sales_agent"), "by salesppl")
    print("AGENT", text, log)


def _ran(log):
    return [a for n, a in log if n == TOOL]


@pytest.mark.parametrize("answer", [None, {"mode": "fill"}])
def test_a3_1_a_new_axis_while_how_many_is_open_swaps_into_the_open_ask(console, monkeypatch, answer) -> None:
    _open_how_many(console, monkeypatch)
    text, log = _say_all(console, monkeypatch, _verdict(group_by="customer", open_question_answer=answer), "by customer")
    assert "as a number" not in text, text
    assert _ran(log) == [] and text.count("?") == 1 and "How many?" in text, (text, log)
    text, log = _say_all(console, monkeypatch, _verdict(top_n=5, ranking_refine=False, state_changes=[
        {"op": "answer", "axis": None, "position": None}]), "top 5")
    ran = _ran(log)
    assert len(ran) == 1, (text, log)
    assert ran[0]["group_by"] == "customer" and ran[0]["top_n"] == 5, ran
    assert ran[0]["product_code"] == PRODUCT_CODE and ran[0]["date_from"] == "2026-01-01", ran
    assert ran[0]["basis"] == "delivered" and ran[0]["measure"] == "qty", ran


def test_a3_1b_the_owed_period_question_keeps_the_product_when_the_axis_changes(console, monkeypatch) -> None:
    _state_on(console)
    first = _parser_output(domain_hint="order", intent_hint="check_order", order_status="sales_ranking",
                           ranking_refine=False, group_by="customer", top_n=10, measure="qty", basis="delivered",
                           entities=[_e(PRODUCT_CODE, "product")], domain_in_message=True, state_changes=list(KEEP))
    text, log = _say_all(console, monkeypatch, first, f"top 10 customers for {PRODUCT_CODE} delivered qty")
    assert _ran(log) == [] and "period" in text.lower(), (text, log)
    text, log = _say_all(console, monkeypatch, _verdict(group_by="sales_agent"), "by agent")
    assert _ran(log) == [] and "as a period" not in text and text.lower().count("period") >= 1, (text, log)
    assert "How many" not in text and "quantity" not in text.lower(), text
    text, log = _say_all(console, monkeypatch, _verdict(top_n=5, ranking_refine=False, measure="qty", basis="delivered",
                                                        state_changes=[{"op": "answer", "axis": None, "position": None}],
                                                        **YEAR_2025), "2025 top 5 qty delivered")
    ran = _ran(log)
    assert len(ran) == 1, (text, log)
    assert ran[0]["group_by"] == "sales_agent" and ran[0]["product_code"] == PRODUCT_CODE, ran


def test_a3_2_guard_a_reply_with_the_count_is_the_answer_even_naming_an_axis(console, monkeypatch) -> None:
    for group_by in ("customer", None):
        _open_how_many(console, monkeypatch)
        text, log = _say_all(console, monkeypatch, _verdict(top_n=5, group_by=group_by), "top 5")
        ran = _ran(log)
        assert len(ran) == 1 and ran[0]["top_n"] == 5 and "as a number" not in text, (group_by, text, log)
        # the slot's OWN axis wins (16 Oct noise rule): the parser's axis on an answering turn is ignored
        assert ran[0]["group_by"] == "sales_agent", (group_by, ran)


def test_a3_3_guard_the_held_axis_echoed_with_nothing_else_is_unchanged(console, monkeypatch) -> None:
    _open_how_many(console, monkeypatch)
    text, log = _say_all(console, monkeypatch, _verdict(group_by="sales_agent"), "by salesppl")
    # Today: the held axis echoed fills nothing, so nothing runs and the count is asked again
    # (it still opens with the "I don't know ... as a number" miss line; not pinned here).
    assert _ran(log) == [] and "How many? For example top 5." in text, (text, log)


def test_a3_4_guard_an_item_ranking_with_no_basis_or_measure_gets_one_combined_question(console, monkeypatch) -> None:
    """Row 5: the parse leaves basis and measure null ("Top 30 selling item this year"): one question names both."""
    _state_on(console)
    qf = _verdict(order_status="sales_ranking", ranking_refine=False, group_by="product", top_n=30, basis=None,
                  measure=None, domain_in_message=True, state_changes=list(KEEP), **YEAR_2026)
    text, log = _say_all(console, monkeypatch, qf, "Top 30 selling item this year")
    assert _ran(log) == [], (text, log)
    assert "quantity" in text.lower() and "amount" in text.lower(), text
    assert "delivered" in text.lower() and "ordered" in text.lower(), text


# ------------------------------------------------ review 2: the swap re-derives what the new axis owes


def _slot_args(**args: Any) -> dict[str, Any]:
    return {"args": args, "top_n": None}


ANSWER_OP = [{"op": "answer", "axis": None, "position": None}]


def _first_total(group_by: str | None) -> dict[str, Any]:
    """'total qty of <product> in 2026' (or 'by month'): no basis, so the basis is asked."""
    return _parser_output(
        domain_hint="order", intent_hint="check_order", order_status="sales_ranking", ranking_refine=False,
        group_by=group_by, top_n=None, measure="qty", basis=None, entities=[_e(PRODUCT_CODE, "product")],
        domain_in_message=True, state_changes=list(KEEP), **YEAR_2026)


@pytest.mark.parametrize("answer", [None, {"mode": "fill"}])
@pytest.mark.parametrize("old_axis", [None, "month"], ids=["total", "month"])
def test_a3r2_1_a_new_axis_over_a_total_or_a_month_trend_asks_the_count_it_never_settled(
    console, monkeypatch, old_axis, answer
) -> None:
    _state_on(console)
    text, log = _say_all(console, monkeypatch, _first_total(old_axis), "total qty of x in 2026")
    assert _ran(log) == [] and "Delivered" in text, ("setup", text, log)
    text, log = _say_all(console, monkeypatch, _verdict(group_by="customer", open_question_answer=answer), "by customer")
    assert _ran(log) == [] and "How many?" in text and "Delivered" in text and text.count("?") >= 2, (text, log)
    assert "as a number" not in text, text
    # basis alone must not run the ranking without a count
    text, log = _say_all(console, monkeypatch, _verdict(basis="delivered", ranking_refine=False, state_changes=ANSWER_OP), "delivered")
    assert _ran(log) == [] and "How many?" in text, (text, log)
    text, log = _say_all(console, monkeypatch, _verdict(top_n=5, ranking_refine=False, state_changes=ANSWER_OP), "top 5")
    ran = _ran(log)
    assert len(ran) == 1 and ran[0]["group_by"] == "customer" and ran[0]["top_n"] == 5, (text, log)
    assert ran[0]["product_code"] == PRODUCT_CODE and ran[0]["basis"] == "delivered" and ran[0]["measure"] == "qty", ran


def test_a3r2_2_a_swap_to_month_over_a_comparison_says_a_month_trend_is_not_compared(console, monkeypatch) -> None:
    from app.services.chatbot.lanes.business.report_ask import COMPARE_BY_MONTH_LINE

    _state_on(console)
    first = _parser_output(
        domain_hint="order", intent_hint="check_order", order_status="sales_ranking", ranking_refine=False,
        group_by="customer", top_n=10, measure="qty", basis="delivered", compare_to="last_year",
        entities=[_e(PRODUCT_CODE, "product")], domain_in_message=True, state_changes=list(KEEP))
    text, log = _say_all(console, monkeypatch, first, "top 10 customers x vs last year qty delivered")
    assert _ran(log) == [] and "period" in text.lower(), ("setup", text, log)
    text, log = _say_all(console, monkeypatch, _verdict(group_by="month"), "by month")
    assert COMPARE_BY_MONTH_LINE in text and _ran(log) == [], (text, log)


def test_a3r2_3_the_swap_drops_only_the_new_axis_own_filter() -> None:
    from app.services.chatbot.lanes.business.report_ask import _swap_axis

    held = _slot_args(group_by="customer", product_code=PRODUCT_CODE, product_ids=["p1"], customer_ids=["c1"])
    out = _swap_axis(_verdict(group_by="product"), held)["args"]
    assert "product_code" not in out and "product_ids" not in out and out["customer_ids"] == ["c1"], out
    assert out["group_by"] == "product", out


def test_a3r2_3_a_swap_to_product_ranks_products_across_all(console, monkeypatch) -> None:
    _open_how_many(console, monkeypatch)
    text, log = _say_all(console, monkeypatch, _verdict(group_by="product"), "by product")
    assert _ran(log) == [] and "How many?" in text, (text, log)
    text, log = _say_all(console, monkeypatch, _verdict(top_n=5, ranking_refine=False, state_changes=ANSWER_OP), "top 5")
    ran = _ran(log)
    assert len(ran) == 1 and ran[0]["group_by"] == "product", (text, log)
    assert "product_code" not in ran[0] and "product_ids" not in ran[0], ran


def test_a3r2_4_a_comparison_named_with_the_new_axis_ranks_the_new_axis(console, monkeypatch) -> None:
    _open_how_many(console, monkeypatch)
    text, log = _say_all(console, monkeypatch, _verdict(group_by="customer", compare_to="last_year"), "by customer vs last year")
    assert _ran(log) == [] and "How many?" in text, (text, log)
    text, log = _say_all(console, monkeypatch, _verdict(top_n=5, ranking_refine=False, state_changes=ANSWER_OP), "top 5")
    ran = _ran(log)
    assert len(ran) == 1 and ran[0]["group_by"] == "customer" and ran[0].get("compare_to") == "last_year", (text, log)


def test_a3r2_5_a_dealers_swap_to_an_agent_gets_the_refusal_at_once(console, monkeypatch) -> None:
    from tests.chatbot.test_report_ask_lane import _link_dealer

    _link_dealer(console)
    _state_on(console)
    text, log = _say_all(console, monkeypatch, _first_total(None), "total qty of x in 2026")
    assert _ran(log) == [] and "Delivered" in text, ("setup", text, log)
    text, log = _say_all(console, monkeypatch, _verdict(group_by="sales_agent"), "by agent")
    assert _ran(log) == [] and "not available for your account" in text, (text, log)
