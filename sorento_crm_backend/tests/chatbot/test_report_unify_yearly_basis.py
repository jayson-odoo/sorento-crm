"""REPORT-UNIFY phase 3 fix round, R3: the Yearly comparison (axis year, `crm_sales_analysis`) asks its basis through a
`required_fields` slot, offering only "Invoiced, delivered or ordered?", never defaulting; the answer runs the analysis
with that basis. Two turns, the harness of `test_report_unify_routing.py`."""
from __future__ import annotations

import pytest

from tests.chatbot.test_report_unify_routing import (  # noqa: F401  (bot / console are fixtures)
    YEAR,
    _reply,
    _status,
    bot,
    console,
)

QUESTION = "Invoiced, delivered or ordered?"


def _yearly(**over):
    fields = {"group_by": "year", "sales_basis": None, "basis": None, **YEAR, **over}
    return _status("sales_analysis", **fields)


def test_r3_a_yearly_comparison_naming_no_basis_asks_the_three(bot) -> None:
    text, calls = bot.say(_yearly(), "sales by year")
    assert calls == [], calls
    assert text.strip() == QUESTION, text


@pytest.mark.parametrize("basis", ["invoiced", "delivered", "ordered"])
def test_r3_the_answer_runs_the_yearly_comparison_with_that_basis(bot, basis) -> None:
    bot.say(_yearly(), "sales by year")
    text, calls = bot.say(
        _reply(message_type="business_query", domain_hint=None, intent_hint=None, entities=[], sales_basis=basis), basis
    )
    assert [n for n, _a in calls] == ["crm_sales_analysis"], (calls, text)
    args = calls[0][1]
    assert args["basis"] == basis and args["cols"] == "year", args
    assert args["date_from"] == "2026-01-01" and args["date_to"] == "2026-12-31", args


def test_r3_a_basis_named_up_front_is_never_asked(bot) -> None:
    text, calls = bot.say(_yearly(sales_basis="ordered"), "ordered sales by year")
    assert [n for n, _a in calls] == ["crm_sales_analysis"], (calls, text)
    assert calls[0][1]["basis"] == "ordered", calls
