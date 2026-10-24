"""REPORT-SMART-L R6 review (AC-OR6): the null-axis reader at every place the parser's `group_by` guess is read.
Fake codes only; the tester's file `test_one_ranking_r6_axis_words.py` is untouched."""
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


def test_r6b_1_names_its_own_ask_ignores_a_guessed_axis_when_axis_words_is_null() -> None:
    from app.services.chatbot.lanes.business import report_ask

    slot = {"extras": {"args": {"group_by": "sales_agent"}}, "values": {}}
    reply = _parser_output(
        order_status="sales_ranking", ranking_refine=False, group_by="customer", axis_words=None,
        entities=[], state_changes=list(ANSWER), **{"date_filter_start": "2025-01-01", "date_filter_end": "2025-12-31"})
    assert report_ask.names_its_own_ask(reply, slot) is False  # the period is an answer; the guessed axis is not a new ask
    typed = {**reply, "axis_words": "by customer"}
    assert report_ask.names_its_own_ask(typed, slot) is True  # a typed axis with the period is a new ask (R5 review round 8)


def _verdict(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = dict(
        domain_hint="order", intent_hint="check_order", order_status="sales_ranking", ranking_refine=False,
        group_by="product", top_n=10, measure="qty", basis="delivered", entities=[], domain_in_message=True,
        state_changes=list(KEEP), **YEAR_2026)
    base.update(over)
    return _parser_output(**base)


@pytest.mark.parametrize("words", ["paling laris", "best selling", "畅销"])
def test_r6b_2_a_noun_less_item_ranking_with_axis_words_keeps_its_axis(console, monkeypatch, words) -> None:
    _state_on(console)
    text, log = _say_all(console, monkeypatch, _verdict(axis_words=words), f"10 {words} tahun ini delivered qty")
    ran = _ran(log)
    assert len(ran) == 1 and ran[0]["group_by"] == "product" and ran[0]["top_n"] == 10, (text, log)


def test_r6b_3_a_top_selling_label_keeps_its_default_item_axis_whatever_axis_words_says(console, monkeypatch) -> None:
    _state_on(console)
    qf = _verdict(order_status="top_selling", group_by=None, rank_group="item", rank_direction="top", axis_words=None)
    text, log = _say_all(console, monkeypatch, qf, "10 paling laris tahun ini delivered qty")
    ran = _ran(log)
    assert len(ran) == 1 and ran[0]["group_by"] == "product", (text, log)


def test_r6b_4_by_capability_reads_the_typed_axis() -> None:
    from app.services.chatbot.lanes.business import report_ask

    analysis = {"order_status": "sales_analysis", "group_by": "customer", "axis_words": None, "measure": None}
    out = report_ask.by_capability(analysis)
    assert out["order_status"] == "sales_analysis" and not out.get("capability_from"), out  # stays the analysis tool's
    report = {"order_status": "sales_report", "group_by": "product", "axis_words": None, "measure": None}
    out = report_ask.by_capability(report)
    assert out["order_status"] == "sales_report" and not out.get("capability_from"), out
    typed = {"order_status": "sales_analysis", "group_by": "customer", "axis_words": "by customer", "measure": None}
    assert report_ask.by_capability(typed)["order_status"] == "sales_ranking"  # a named axis is still the report ask's
    absent = {"order_status": "sales_analysis", "group_by": "customer", "measure": None}
    assert report_ask.by_capability(absent)["order_status"] == "sales_ranking"  # key absent: today's behaviour
