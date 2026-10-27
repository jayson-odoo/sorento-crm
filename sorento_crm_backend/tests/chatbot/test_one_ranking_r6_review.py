"""REPORT-SMART-L R6 review (AC-OR6): the null-axis reader at every place the parser's `group_by` guess is read.
Fake codes only; the tester's file `test_one_ranking_r6_by_words.py` is untouched."""
from __future__ import annotations

from typing import Any

import pytest

from tests.chatbot.test_engine import _parser_output, stub_access  # noqa: F401
from tests.chatbot.test_report_ask_lane import PRODUCT_CODE, TOOL, _e, _say_all, console  # noqa: F401
from tests.chatbot.test_report_smart_step7 import KEEP, _state_on

YEAR_2026 = {"date_filter_start": "2026-01-01", "date_filter_end": "2026-12-31"}
ANSWER = [{"op": "answer", "axis": None, "position": None}]


def _ran(log):
    return [a for n, a in log if n == TOOL]


def test_r6b_1_names_its_own_ask_ignores_a_guessed_axis_when_by_words_is_null() -> None:
    from app.services.chatbot.lanes.business import report_ask

    slot = {"extras": {"args": {"group_by": "sales_agent"}}, "values": {}}
    reply = _parser_output(
        order_status="sales_ranking", ranking_refine=False, group_by="customer", by_words=None,
        entities=[], state_changes=list(ANSWER), **{"date_filter_start": "2025-01-01", "date_filter_end": "2025-12-31"})
    assert report_ask.names_its_own_ask(reply, slot) is False  # the period is an answer; the guessed axis is not a new ask
    typed = {**reply, "by_words": "by customer"}
    assert report_ask.names_its_own_ask(typed, slot) is True  # a typed axis with the period is a new ask (R5 review round 8)


def _verdict(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = dict(
        domain_hint="order", intent_hint="check_order", order_status="sales_ranking", ranking_refine=False,
        group_by="product", top_n=10, measure="qty", basis="delivered", entities=[], domain_in_message=True,
        state_changes=list(KEEP), **YEAR_2026)
    base.update(over)
    return _parser_output(**base)


@pytest.mark.parametrize("words", ["paling laris", "best selling", "畅销"])
def test_r6b_2_a_noun_less_item_ranking_with_by_words_keeps_its_axis(console, monkeypatch, words) -> None:
    _state_on(console)
    text, log = _say_all(console, monkeypatch, _verdict(by_words=words), f"10 {words} tahun ini delivered qty")
    ran = _ran(log)
    assert len(ran) == 1 and ran[0]["group_by"] == "product" and ran[0]["top_n"] == 10, (text, log)


def test_r6b_3_a_top_selling_label_keeps_its_default_item_axis_whatever_by_words_says(console, monkeypatch) -> None:
    _state_on(console)
    qf = _verdict(order_status="top_selling", group_by=None, rank_group="item", rank_direction="top", by_words=None)
    text, log = _say_all(console, monkeypatch, qf, "10 paling laris tahun ini delivered qty")
    ran = _ran(log)
    assert len(ran) == 1 and ran[0]["group_by"] == "product", (text, log)


def test_r6b_4_by_capability_reads_the_typed_axis() -> None:
    from app.services.chatbot.lanes.business import report_ask

    # REPORT-UNIFY (Q1): every sales analysis / report is the report ask's; a null `by_words` names no axis, so the
    # guessed `group_by` is dropped and it is a total.
    analysis = {"order_status": "sales_analysis", "group_by": "customer", "by_words": None, "measure": None}
    out = report_ask.by_capability(analysis)
    assert out["order_status"] == "sales_ranking" and out["group_by"] is None and out["capability_from"] == "sales_analysis", out
    report = {"order_status": "sales_report", "group_by": "product", "by_words": None, "measure": None}
    out = report_ask.by_capability(report)
    assert out["order_status"] == "sales_ranking" and out["group_by"] is None and out["capability_from"] == "sales_report", out
    typed = {"order_status": "sales_analysis", "group_by": "customer", "by_words": "by customer", "measure": None}
    assert report_ask.by_capability(typed)["group_by"] == "customer"  # a named axis is kept
    absent = {"order_status": "sales_analysis", "group_by": "customer", "measure": None}
    assert report_ask.by_capability(absent)["group_by"] == "customer"  # key absent: today's behaviour
    yearly = {"order_status": "sales_analysis", "group_by": "year", "by_words": "by year", "measure": None}
    assert report_ask.by_capability(yearly)["order_status"] == "sales_analysis"  # the Yearly comparison file stays on its tool


@pytest.mark.parametrize(
    ("status", "group_by"),
    [("pending", "month"), ("pending", "transporter"), (None, "supplier"), ("pending", "date")],
)
def test_r6b_5_by_capability_leaves_the_grouping_of_a_non_report_status_alone(status, group_by) -> None:
    from app.services.chatbot.lanes.business import report_ask

    out = report_ask.by_capability({"order_status": status, "group_by": group_by, "by_words": None, "measure": None})
    assert out["group_by"] == group_by, out


def test_r6b_5_a_status_the_report_ask_can_draw_still_types_the_axis() -> None:
    from app.services.chatbot.lanes.business import report_ask

    out = report_ask.by_capability({"order_status": "sales_report", "group_by": "month", "by_words": None, "measure": None})
    assert out["group_by"] is None, out
