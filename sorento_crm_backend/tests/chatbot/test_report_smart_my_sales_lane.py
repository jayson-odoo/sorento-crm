"""RED tests - REPORT-SMART-L UAC AC11, chatbot side: a sales_ranking parse with `self_reference`
true sends `mine: true` to the report-ask tool; false or None sends no `mine` (or false)."""
from __future__ import annotations

from tests.chatbot.test_report_ask_lane import (  # noqa: F401  (fixtures by name)
    _e,
    _rank,
    console,
    console_no_grant,
)


def test_a_self_reference_ranking_sends_mine_true(console) -> None:
    _text, calls = console.say(_rank(_e("Sorento", "brand"), self_reference=True), "my top 3 customers last month")
    (args,) = calls
    assert args.get("mine") is True, args


def test_a_ranking_without_self_reference_sends_no_mine(console) -> None:
    _text, calls = console.say(_rank(_e("Sorento", "brand"), self_reference=False), "top 3 customers last month")
    (args,) = calls
    assert not args.get("mine"), args


def test_a_ranking_with_self_reference_none_sends_no_mine(console) -> None:
    _text, calls = console.say(_rank(_e("Sorento", "brand"), self_reference=None), "top 3 customers last month")
    (args,) = calls
    assert not args.get("mine"), args
