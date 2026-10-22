"""REPORT-SMART-L round S4.

AC-S4-1: with the ranking question open (basis owed) after "top 5 salesman this year vs last
year", the reply "compare with last year" keeps the comparison and asks the owed field again;
never "I don't know ..."; the parser's Open question shows the held comparison.
AC-S4-2: the access level question for a flyer ask names the kind the parser set, with the brand,
whether or not a flyer entity survived grounding. Fake names and codes only.
"""
from __future__ import annotations

from typing import Any

from tests.chatbot.test_engine import _parser_output, stub_access  # noqa: F401
from tests.chatbot.test_report_ask_lane import _e, _rank, _reply, console  # noqa: F401 - fixtures + helpers
from tests.chatbot.test_report_smart_s3_period import _answer, _record_state
from tests.chatbot.test_report_smart_step7 import KEEP, THIS_YEAR, _state_on


def _first(**overrides: Any) -> dict[str, Any]:
    """'top 5 salesman this year vs last year': measure given, basis owed."""
    base: dict[str, Any] = dict(
        top_n=5, measure="qty", basis=None, compare_to="last_year", state_changes=list(KEEP), **THIS_YEAR)
    base.update(overrides)
    return _rank(**base)


def _compare_reply() -> dict[str, Any]:
    """'compare with last year' as the live parser sent it (stored turn 40de9753)."""
    return _parser_output(
        domain_hint="order", intent_hint="check_order", entities=[], compare_to="last_year", basis=None,
        open_question_answer={"mode": None, "picked": [], "items": [], "qty_for_all": None},
        state_changes=list(KEEP),
    )


def _ask(console) -> None:
    _state_on(console)
    text, calls = console.say(_first(), "top 5 salesman this year vs last year")
    assert calls == [], ("setup: the first ask must ask the basis", text, calls)


def test_s4_1_a_comparison_reply_keeps_the_question_and_asks_the_basis_again(console) -> None:
    _ask(console)
    text, calls = console.say(_compare_reply(), "compare with last year")
    assert calls == [], (text, calls)
    assert "I don't know" not in text, text
    assert "delivered" in text.lower() and "ordered" in text.lower(), text  # the basis question again


def test_s4_1_the_held_comparison_survives_to_the_run(console) -> None:
    _ask(console)
    console.say(_compare_reply(), "compare with last year")
    text, calls = console.say(_answer(basis="delivered", top_n=None, measure=None), "delivered")
    assert len(calls) == 1, (text, calls)
    args = calls[0]
    assert args.get("compare_to") == "last_year" and args["basis"] == "delivered", args
    assert args["group_by"] == "sales_agent" and args["top_n"] == 5, args


def test_s4_1_the_parser_is_shown_the_held_comparison_in_the_open_question(console) -> None:
    _state_on(console)
    shown = _record_state(console)
    console.say(_first(), "top 5 salesman this year vs last year")
    console.say(_compare_reply(), "compare with last year")
    line = next((ln for ln in shown[-1].splitlines() if ln.startswith("- open question:")), "")
    assert "last_year" in line or "last year" in line, shown[-1]


def test_s4_1_near_miss_a_reply_filling_the_basis_runs_with_the_comparison(console) -> None:
    _ask(console)
    text, calls = console.say(_answer(basis="delivered", top_n=None, measure=None), "delivered")
    assert len(calls) == 1, (text, calls)
    assert calls[0].get("compare_to") == "last_year" and calls[0]["basis"] == "delivered", calls[0]


# ---------------------------------------------------------------- AC-S4-2


def _flyer_qf(kind: str | None) -> dict[str, Any]:
    """'srt a3 flyer': a brand entity, NO flyer entity (grounding dropped it)."""
    from tests.chatbot.test_promo_kind_subject import _qf

    return _qf(kind=kind, typed="srt")


def test_s4_2_the_access_question_names_the_kind_and_the_brand(session_factory, monkeypatch) -> None:
    from tests.chatbot.test_promo_brand_category import _mcp
    from tests.chatbot.test_promo_kind_subject import _say, _seed_world

    _seed_world(session_factory, sorento_live_flyer=True)  # seeds promotion type a3_flyer, "A3 Flyer"
    _mcp(monkeypatch, session_factory)
    reply, _ = _say(session_factory, monkeypatch, _flyer_qf("a3_flyer"), "srt a3 flyer", "zzt-s4-kind")
    first = reply.splitlines()[0]
    assert first.startswith("Which access level do you need for"), reply
    assert "Sorento" in first and "a3 flyer" in first.casefold(), reply


def test_s4_2_near_miss_no_promotion_kind_is_worded_as_today(session_factory, monkeypatch) -> None:
    from tests.chatbot.test_promo_brand_category import _mcp
    from tests.chatbot.test_promo_kind_subject import _say, _seed_world

    _mcp(monkeypatch, session_factory)
    _seed_world(session_factory, sorento_live_flyer=True)
    reply, _ = _say(session_factory, monkeypatch, _flyer_qf(None), "srt promotion", "zzt-s4-nokind")
    assert reply.splitlines()[0] == "Which access level do you need for Sorento?", reply


# ---------------------------------------------------------------- S4 review round


def test_s4_review_a_month_ranking_answered_with_a_comparison_gets_the_compare_by_month_line(console) -> None:
    from app.services.chatbot.lanes.business.report_ask import COMPARE_BY_MONTH_LINE

    _state_on(console)
    text, calls = console.say(
        _first(group_by="month", compare_to=None), "top 5 months this year by qty")
    assert calls == [], ("setup: the first ask must ask the basis", text, calls)
    text, calls = console.say(_compare_reply(), "compare with last year")
    assert text == COMPARE_BY_MONTH_LINE, text
    text2, calls2 = console.say(_answer(basis="delivered", top_n=None, measure=None), "delivered")
    every = calls + calls2
    assert not any(c.get("group_by") == "month" and c.get("compare_to") for c in every), every


def test_s4_review_guard_a_comparison_only_the_reply_adds_carries_to_the_run(console) -> None:
    _state_on(console)
    text, calls = console.say(_first(compare_to=None), "top 5 salesman this year by qty")
    assert calls == [], ("setup: the first ask must ask the basis", text, calls)
    text, calls = console.say(_compare_reply(), "compare with last year")
    assert calls == [] and "I don't know" not in text, (text, calls)
    assert "delivered" in text.lower() and "ordered" in text.lower(), text
    text, calls = console.say(_answer(basis="delivered", top_n=None, measure=None), "delivered")
    assert len(calls) == 1, (text, calls)
    args = calls[0]
    assert args.get("compare_to") == "last_year" and args["basis"] == "delivered", args
    assert args["group_by"] == "sales_agent", args
