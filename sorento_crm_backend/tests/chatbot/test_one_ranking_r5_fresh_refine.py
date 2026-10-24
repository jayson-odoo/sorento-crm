"""REPORT-SMART-L R5 row 7 (EVAL-BENCH mini gate, turn 75d9129a): a verdict flagged `ranking_refine` with NO report
held, that names its own axis and typed its period, is a fresh ask that keeps the period. Row 13: a live
salesperson without the Sales report switch is refused an item ranking first, never asked its measure."""
from __future__ import annotations

from tests.chatbot.test_engine import _parser_output, stub_access  # noqa: F401
from tests.chatbot.test_report_ask_lane import (  # noqa: F401 - fixtures + helpers
    TOOL,
    _say_all,
    console,
    console_no_grant,
)
from tests.chatbot.test_report_smart_salesperson_gate import _make_salesperson
from tests.chatbot.test_report_smart_step7 import KEEP, _state_on

YEAR_2026 = {"date_filter_start": "2026-01-01", "date_filter_end": "2026-12-31"}
NOT_ENABLED = "Sales report is not enabled for your account."


def _refine(**over):
    base = dict(
        domain_hint="order", intent_hint="check_order", order_status="sales_ranking", ranking_refine=True,
        group_by="product", top_n=100, measure="qty", basis="delivered", entities=[], domain_in_message=False,
        state_changes=[{"op": "keep", "axis": None, "position": None}], **YEAR_2026)
    base.update(over)
    return _parser_output(**base)


def test_r7_a_fresh_refine_naming_its_axis_keeps_its_typed_period(console, monkeypatch) -> None:
    _state_on(console)
    text, log = _say_all(console, monkeypatch, _refine(), "top 100 items this year by delivered qty")
    ran = [a for n, a in log if n == TOOL]
    assert "Which period?" not in text and len(ran) == 1, (text, log)
    assert ran[0]["group_by"] == "product" and ran[0]["top_n"] == 100, ran
    assert ran[0]["date_from"] == "2026-01-01" and ran[0]["date_to"] == "2026-12-31", ran


def test_r7_b_guard_a_refine_naming_no_axis_with_nothing_held_still_asks(console, monkeypatch) -> None:
    _state_on(console)
    qf = _refine(group_by=None, top_n=None, measure=None, basis=None)
    text, log = _say_all(console, monkeypatch, qf, "2026")
    assert [a for n, a in log if n == TOOL] == [] and "?" in text, (text, log)


def test_r13_c_guard_an_ungranted_salesperson_is_refused_items_first(console_no_grant, monkeypatch) -> None:
    _make_salesperson(console_no_grant)
    for self_reference in (None, False):
        qf = _parser_output(
            domain_hint="order", intent_hint="check_order", order_status="top_selling", group_by="product",
            rank_group="item", rank_direction="top", top_n=10, measure=None, basis=None, rank_by=None,
            self_reference=self_reference, entities=[], domain_in_message=True, state_changes=list(KEEP), **YEAR_2026)
        text, log = _say_all(console_no_grant, monkeypatch, qf, "top 10 selling items this year")
        assert text.strip() == NOT_ENABLED and "?" not in text, (self_reference, text)
        assert [n for n, _a in log if n == TOOL] == [], log
