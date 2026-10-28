"""REPORT-UNIFY phase 3 fix round, R3 (moved to the report ask, crew 28 Oct): the Yearly comparison (axis year) is the
report ask grouped by year; it asks the ONE basis question, never defaulting; the answer runs it with that basis. Two turns, the harness of `test_report_unify_routing.py`."""
from __future__ import annotations

import pytest

from tests.chatbot.test_report_unify_routing import (  # noqa: F401  (bot / console are fixtures)
    YEAR,
    _reply,
    _status,
    bot,
    console,
)

QUESTION = "Invoiced, delivered, ordered or outstanding?"


def _yearly(**over):
    fields = {"group_by": "year", "by_words": "yearly", "sales_basis": None, "basis": None, **YEAR, **over}
    return _status("sales_analysis", **fields)


def test_r3_a_yearly_comparison_naming_no_basis_asks_the_one_four_option_question(bot) -> None:
    text, calls = bot.say(_yearly(), "sales by year")
    assert calls == [], calls
    assert text.strip() == QUESTION, text


@pytest.mark.parametrize("position, basis", [(1, "invoiced"), (2, "delivered"), (3, "ordered")])
def test_r3_the_answer_runs_the_yearly_comparison_with_that_basis(bot, position, basis) -> None:
    bot.say(_yearly(), "sales by year")
    # Parser only (owner rule 28 Oct): the basis is the parser's declared pick of an offered option.
    text, calls = bot.say(
        _reply(
            message_type="business_query", domain_hint=None, intent_hint=None, entities=[], sales_basis=basis,
            by_words=None, open_question_answer={"mode": "pick", "picked": [position], "items": [], "qty_for_all": None},
        ),
        basis,
    )
    assert [n for n, _a in calls] == ["crm_report_ask"], (calls, text)  # no chat path calls crm_sales_analysis now
    args = calls[0][1]
    assert args["basis"] == basis and args["group_by"] == "year", args
    assert args["date_from"] == "2026-01-01" and args["date_to"] == "2026-12-31", args


def test_r3_a_basis_named_up_front_is_never_asked(bot) -> None:
    text, calls = bot.say(_yearly(sales_basis="ordered"), "ordered sales by year")
    assert [n for n, _a in calls] == ["crm_report_ask"], (calls, text)
    assert calls[0][1]["basis"] == "ordered" and calls[0][1]["group_by"] == "year", calls
