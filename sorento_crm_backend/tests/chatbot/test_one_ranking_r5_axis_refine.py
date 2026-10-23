"""REPORT-SMART-L R5 a3 (EVAL-BENCH live turn c404da24): a held sales TOTAL frame, "by salesppl" opens the
How many? question, and "by customer" (a refine naming another axis, filling nothing) is a NEW ask, not
the count answer. Real engine seam, the shapes the live parser emitted. Fake codes only."""
from __future__ import annotations

from typing import Any

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


def test_a3_1_a_new_axis_while_how_many_is_open_is_a_new_ask_not_the_count_answer(console, monkeypatch) -> None:
    _open_how_many(console, monkeypatch)
    text, log = _say_all(console, monkeypatch, _verdict(group_by="customer"), "by customer")
    assert "as a number" not in text, text
    assert _ran(log) == [] and text.count("?") == 1, (text, log)  # one question, nothing ran yet
    text, log = _say_all(console, monkeypatch, _verdict(top_n=5, ranking_refine=False, state_changes=[
        {"op": "answer", "axis": None, "position": None}]), "top 5")
    ran = _ran(log)
    assert len(ran) == 1, (text, log)
    assert ran[0]["group_by"] == "customer" and ran[0]["top_n"] == 5, ran
    assert ran[0]["product_code"] == PRODUCT_CODE and ran[0]["date_from"] == "2026-01-01", ran


def test_a3_2_guard_a_reply_with_the_count_is_the_answer_even_naming_an_axis(console, monkeypatch) -> None:
    for group_by in ("customer", None):
        _open_how_many(console, monkeypatch)
        text, log = _say_all(console, monkeypatch, _verdict(top_n=5, group_by=group_by), "top 5")
        ran = _ran(log)
        assert len(ran) == 1 and ran[0]["top_n"] == 5 and "as a number" not in text, (group_by, text, log)


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
