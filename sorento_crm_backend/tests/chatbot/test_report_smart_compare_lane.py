"""REPORT-SMART-1021 step 4 (stretch): the lane passes the parser's `compare_to`.

Needs the parser's `compare_to` field (previous_period | last_year | null; lines handed to
crew for CHAT-CLOSED-LISTS-L). A fresh ask names it, a refine adds or changes it, and an ask
that does not name it compares with nothing."""
from __future__ import annotations

from tests.chatbot.test_engine import _parser_output, stub_access  # noqa: F401
from tests.chatbot.test_report_ask_lane import _e, _rank, _refine, _seed_cabana, console  # noqa: F401

SEP = {"date_filter_start": "2026-09-01", "date_filter_end": "2026-09-30"}


def test_a_fresh_ask_naming_last_year_compares_with_it(console) -> None:
    text, calls = console.say(_rank(_e("Sorento", "brand"), compare_to="last_year", **SEP), "top 3 salesman sorento sept vs last year")
    assert len(calls) == 1 and calls[0]["compare_to"] == "last_year", (text, calls)


def test_paraphrase_previous_period(console) -> None:
    text, calls = console.say(
        _rank(_e("Sorento", "brand"), compare_to="previous_period", **SEP), "top 3 SA sorento september compared to august"
    )
    assert len(calls) == 1 and calls[0]["compare_to"] == "previous_period", (text, calls)


def test_a_refine_adds_the_comparison_to_the_held_ranking(console) -> None:
    console.cabana = _seed_cabana(console)
    console.say(_rank(_e("Cabana", "brand"), **SEP), "top 3 salesman cabana september")
    text, calls = console.say(_refine(compare_to="last_year"), "compare with last year")
    assert len(calls) == 1, (text, calls)
    args = calls[0]
    assert args["compare_to"] == "last_year" and args["brand_ids"] == [console.cabana], args
    assert args["basis"] == "delivered" and args["measure"] == "amount", args


def test_near_miss_no_comparison_named_sends_none(console) -> None:
    text, calls = console.say(_rank(_e("Sorento", "brand"), **SEP), "top 3 salesman sorento september")
    assert len(calls) == 1 and "compare_to" not in calls[0], (text, calls)


def test_near_miss_an_unknown_comparison_word_is_dropped(console) -> None:
    text, calls = console.say(_rank(_e("Sorento", "brand"), compare_to="last_week", **SEP), "x")
    assert len(calls) == 1 and "compare_to" not in calls[0], (text, calls)


def test_a_month_trend_compared_is_said_never_sent(console) -> None:
    text, calls = console.say(_rank(_e("Sorento", "brand"), group_by="month", compare_to="last_year", **SEP), "sorento by month vs last year")
    assert calls == [], (text, calls)
    assert "month" in text.lower() and "compare" in text.lower(), text
