"""REPORT-UNIFY: chatbot understanding comes from the semantic parser ONLY (owner rule, restated 28 Oct 2026).

The Yearly basis question and the company / sales agent picks are read ONLY from the parser's declared answer to the
`Open question:` it was shown (a pick position, resolved against the options offered). A typed label or digit the
parser did not declare an answer for is never taken as the pick; a short reply is never an answer by its length.
Fake names only."""
from __future__ import annotations

from typing import Any

import pytest

from tests.chatbot.test_report_unify_company_lane import _two_companies
from tests.chatbot.test_report_unify_routing import (  # noqa: F401  (bot / console are fixtures)
    YEAR,
    _only_report_ask,
    _reply,
    _status,
    bot,
    console,
)
from tests._mc_lookup_seed import MOCHA_ID


def _answer(position: int, **over: Any) -> dict[str, Any]:
    """The parser's reading of a reply it declares an answer to the open question: a pick of one offered option."""
    return _reply(
        message_type="business_query", domain_hint=None, intent_hint=None, entities=[],
        open_question_answer={"mode": "pick", "picked": [position], "items": [], "qty_for_all": None}, **over,
    )


def _undeclared(**over: Any) -> dict[str, Any]:
    """The parser's reading of a short reply it does NOT declare an answer to the question."""
    return _reply(message_type="business_query", domain_hint=None, intent_hint=None, entities=[], **over)


def _yearly(**over: Any) -> dict[str, Any]:
    return _status("sales_analysis", **{"group_by": "year", "sales_basis": None, "basis": None, **YEAR, **over})


# ---------------------------------------------------------------- the Yearly basis


@pytest.mark.parametrize("position, basis", [(1, "invoiced"), (2, "delivered"), (3, "ordered")])
def test_the_yearly_basis_answered_by_the_parsers_pick_runs_that_basis(bot, position, basis) -> None:
    bot.say(_yearly(), "sales by year")
    # The words are not the option's label: only the declared pick position can name the basis.
    text, calls = bot.say(_answer(position), "the one i said before lah")
    assert [n for n, _a in calls] == ["crm_sales_analysis"], (calls, text)
    assert calls[0][1]["basis"] == basis, calls


@pytest.mark.parametrize("basis", ["invoiced", "delivered", "ordered"])
def test_a_short_reply_the_parser_did_not_declare_an_answer_is_not_taken_as_the_yearly_basis(bot, basis) -> None:
    bot.say(_yearly(), "sales by year")
    text, calls = bot.say(_undeclared(sales_basis=basis), basis)
    assert not [a for n, a in calls if n == "crm_sales_analysis" and a.get("basis") == basis], (calls, text)


# ---------------------------------------------------------------- the company pick


def _company_question(bot) -> tuple[str, str]:
    sorento, mocha = _two_companies(bot)
    text, calls = bot.say(_status("sales_report", basis="delivered", **YEAR), "total sales 2026")
    assert calls == [] and f"{sorento} or {mocha}?" in text, (text, calls)
    return sorento, mocha


def test_a_company_pick_answered_by_the_parsers_position_runs_that_company(bot) -> None:
    sorento, mocha = _company_question(bot)
    text, calls = bot.say(_answer(2), "the second company please")
    assert _only_report_ask(calls)["company"] == MOCHA_ID, calls


@pytest.mark.parametrize("typed", ["Mocha", "2", "mocha"])
def test_a_typed_company_label_or_digit_with_no_parser_answer_is_never_the_pick(bot, typed) -> None:
    _company_question(bot)
    text, calls = bot.say(_undeclared(), typed)
    assert not [a for n, a in calls if a.get("company")], (calls, text)


# ---------------------------------------------------------------- the engine: a parse is not overridden by a reply's shape


def test_a_short_reply_whose_parse_is_a_fresh_report_ask_goes_by_the_parse(bot) -> None:
    """With the Yearly basis question open, a short reply whose parse is a fresh sales total (and no declared answer)
    is that new ask, never the basis answer by its length (`engine` read it by shape before `by_capability`)."""
    bot.say(_yearly(), "sales by year")
    text, calls = bot.say(_status("sales_report", basis="delivered", **YEAR), "sales 2026")
    assert [n for n, _a in calls] == ["crm_report_ask"], (calls, text)
