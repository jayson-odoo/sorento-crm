"""SALES-TOTAL-ASK (owner ruling 27 Oct 2026, "total sales should ask", #1931) on the report ask.

Every chatbot sales total is `crm_report_ask`; the one basis question is its own "Invoiced, delivered, ordered or
outstanding?", answered ONLY by the parser's declared answer (the option it picked, or the basis it filled). These are
#1931's cases, moved from the retired `crm_sales_analysis` path: the question, a named basis, the answers, a cancel, a
declared answer naming no option, and the first message's own ask winning over the answer's parse."""
from __future__ import annotations

from typing import Any

import pytest

from tests.chatbot.test_report_unify_routing import (  # noqa: F401  (bot / console are fixtures)
    SEP,
    YEAR,
    _only_report_ask,
    _reply,
    _status,
    bot,
    console,
)

QUESTION = "Invoiced, delivered, ordered or outstanding?"


def _total(**over: Any) -> dict[str, Any]:
    return _status("sales_analysis", **{"group_by": None, "sales_basis": None, "basis": None, **SEP, **over})


def _answer(mode: str = "pick", picked: list[int] | None = None, **over: Any) -> dict[str, Any]:
    return _reply(
        message_type="business_query", domain_hint=None, intent_hint=None, entities=[],
        open_question_answer={"mode": mode, "picked": picked or [], "items": [], "qty_for_all": None}, **over,
    )


def test_a_total_with_no_basis_is_asked_never_run(bot) -> None:
    text, calls = bot.say(_total(), "total sales Sep 2026")
    assert calls == [] and text.strip() == QUESTION, (text, calls)


@pytest.mark.parametrize("named", [{"sales_basis": "invoiced"}, {"sales_basis": "ordered"}, {"basis": "delivered"}])
def test_a_named_basis_runs_without_asking(bot, named) -> None:
    text, calls = bot.say(_total(**named), "total sales Sep 2026")
    assert _only_report_ask(calls)["basis"] == next(iter(named.values())), calls


@pytest.mark.parametrize("position, basis", [(1, "invoiced"), (2, "delivered"), (3, "ordered")])
def test_a_declared_pick_runs_the_first_messages_total_with_that_basis(bot, position, basis) -> None:
    bot.say(_total(), "total sales Sep 2026")
    text, calls = bot.say(_answer(picked=[position]), "that one")
    args = _only_report_ask(calls)
    assert args["basis"] == basis and not args.get("group_by"), args
    assert args["date_from"] == "2026-09-01" and args["date_to"] == "2026-09-30", args


@pytest.mark.parametrize("key", ["basis", "sales_basis"])
def test_a_declared_fill_naming_the_basis_answers_it(bot, key) -> None:
    bot.say(_total(), "total sales Sep 2026")
    text, calls = bot.say(_answer("fill", **{key: "delivered"}), "delivered")
    assert _only_report_ask(calls)["basis"] == "delivered", calls


def test_outstanding_picked_runs_the_report_ask_outstanding_total(bot) -> None:
    bot.say(_total(), "total sales Sep 2026")
    text, calls = bot.say(_answer(picked=[4]), "outstanding")
    assert _only_report_ask(calls)["basis"] == "outstanding", calls


def test_the_first_messages_ask_wins_over_a_stray_axis_and_count_on_the_answer(bot) -> None:
    bot.say(_total(sales_channel="dealer"), "dealer total sales Sep 2026")
    text, calls = bot.say(_answer(picked=[2], group_by="customer", top_n=5), "delivered")
    args = _only_report_ask(calls)
    assert args["basis"] == "delivered" and not args.get("group_by") and not args.get("top_n"), args
    assert args["channel"] == "dealer", args


def test_a_declared_cancel_cancels(bot) -> None:
    bot.say(_total(), "total sales Sep 2026")
    text, calls = bot.say(_answer("cancel"), "never mind")
    assert calls == [] and "cancel" in text.lower(), (text, calls)


def test_a_declared_answer_naming_no_option_is_asked_again_then_given_up(bot) -> None:
    bot.say(_total(), "total sales Sep 2026")
    text, calls = bot.say(_answer(picked=[9]), "the ninth")
    assert calls == [] and text.strip().endswith(QUESTION), (text, calls)
    text, calls = bot.say(_answer(picked=[9]), "the ninth again")
    assert calls == [] and "still can't read" in text, (text, calls)
