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
        message_type="business_query", domain_hint=None, intent_hint=None, entities=[], by_words=None,
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
    assert [n for n, _a in calls] == ["crm_report_ask"], (calls, text)
    assert calls[0][1]["basis"] == basis and calls[0][1]["group_by"] == "year", calls


@pytest.mark.parametrize("basis", ["invoiced", "delivered", "ordered"])
def test_a_short_reply_the_parser_did_not_declare_an_answer_is_not_taken_as_the_yearly_basis(bot, basis) -> None:
    bot.say(_yearly(), "sales by year")
    text, calls = bot.say(_undeclared(sales_basis=basis), basis)
    assert not [a for n, a in calls if a.get("basis") == basis and a.get("group_by") == "year"], (calls, text)


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


@pytest.mark.parametrize("typed", ["2", "Mocha"])
@pytest.mark.parametrize("mode", ["pick", "fill"])
def test_a_declared_company_answer_that_picks_nothing_never_sends_a_company(bot, mode, typed) -> None:
    """The parser declared an answer but picked no offered option: the typed digit or label is never the fallback."""
    _company_question(bot)
    declared = _reply(
        message_type="business_query", domain_hint=None, intent_hint=None, entities=[],
        open_question_answer={"mode": mode, "picked": [], "items": [], "qty_for_all": None},
    )
    text, calls = bot.say(declared, typed)
    assert not [a for n, a in calls if a.get("company")], (calls, text)


# ---------------------------------------------------------------- the engine: a parse is not overridden by a reply's shape


def test_a_short_reply_whose_parse_is_a_fresh_report_ask_goes_by_the_parse(bot) -> None:
    """With the Yearly basis question open, a short reply whose parse is a fresh sales total (and no declared answer)
    is that new ask, never the basis answer by its length (`engine` read it by shape before `by_capability`)."""
    bot.say(_yearly(), "sales by year")
    text, calls = bot.say(_status("sales_report", basis="delivered", **YEAR), "sales 2026")
    assert [n for n, _a in calls] == ["crm_report_ask"], (calls, text)


# ---------------------------------------------------------------- the outstanding KIND question (crew hand test, head 59c9d237)
# The parser's schema `basis` enum carries the kinds, the kind question is stated to it as a pick of three options, and
# the answer is its pick resolved against them. Never "invoiced".

NO_DATES = {"date_filter_start": None, "date_filter_end": None}


def _bare_outstanding(**over: Any) -> dict[str, Any]:
    return _status("outstanding", **{"basis": None, **NO_DATES, **over})


def test_the_parser_schema_basis_enum_carries_the_outstanding_kinds() -> None:
    from app.services.chatbot.head import parser

    enum = parser._build_json_schema()["properties"]["basis"]["enum"]
    assert {"outstanding", "pending_delivery", "unpaid"} <= set(enum), enum


def test_the_kind_question_is_stated_to_the_parser_as_a_pick_of_three_that_owes_the_basis() -> None:
    from app.services.chatbot import required_fields as rf
    from app.services.chatbot.lanes.business import report_ask
    from app.services.chatbot.turn import question

    ok = rf.Resolved("ok", value=None, label="")
    out = rf.collect(
        None, report_ask.SALES_RANKING_ASK, given={"period": ok, "top_n": ok, "metric": ok},
        extras={"args": {}, "kind_ask": True},
    )
    shown = question.of_required_ask(out.slot)
    assert shown["kind"] == "pick_one" and shown["owed"] == ["basis"], shown
    assert [o["code"] for o in shown["options"]] == ["Undelivered orders", "Pending delivery", "Unpaid invoices"], shown


def test_the_kind_answered_by_the_parsers_pick_position_runs_unpaid_with_no_dates(bot) -> None:
    text, calls = bot.say(_bare_outstanding(), "outstanding")
    assert calls == [], calls
    text, calls = bot.say(_answer(3), "the invoices one")
    args = _only_report_ask(calls)
    assert args["basis"] == "unpaid" and "date_from" not in args and "date_to" not in args, args


def test_the_kind_answered_by_a_declared_fill_naming_unpaid_runs_unpaid(bot) -> None:
    bot.say(_bare_outstanding(), "outstanding")
    declared = _reply(
        message_type="business_query", domain_hint=None, intent_hint=None, entities=[], basis="unpaid",
        open_question_answer={"mode": "fill", "picked": [], "items": [], "qty_for_all": None},
    )
    text, calls = bot.say(declared, "unpaid invoices")
    assert _only_report_ask(calls)["basis"] == "unpaid", calls


@pytest.mark.parametrize("mode", ["fill", "pick"])
def test_the_kind_question_is_never_answered_with_invoiced(bot, mode) -> None:
    bot.say(_bare_outstanding(), "outstanding")
    declared = _reply(
        message_type="business_query", domain_hint=None, intent_hint=None, entities=[], basis="invoiced",
        open_question_answer={"mode": mode, "picked": [], "items": [], "qty_for_all": None},
    )
    text, calls = bot.say(declared, "unpaid invoices")
    assert not [a for n, a in calls if a.get("basis") == "invoiced"], (calls, text)


# ---------------------------------------------------------------- "total sales 2026" is a total on the report ask


def test_total_sales_with_no_axis_asks_the_four_option_basis_then_a_picked_delivered_runs_the_report_ask(bot) -> None:
    text, calls = bot.say(_status("sales_analysis", group_by=None, sales_basis=None, basis=None), "total sales 2026")
    assert calls == [] and text.strip() == "Invoiced, delivered, ordered or outstanding?", (text, calls)
    text, calls = bot.say(_answer(2), "the middle one")
    args = _only_report_ask(calls)
    assert args["basis"] == "delivered" and args["date_from"] == "2026-01-01" and args["date_to"] == "2026-12-31", args
    assert not args.get("group_by"), args


def test_total_sales_for_a_two_company_contact_asks_the_basis_then_the_company(bot) -> None:
    """#1931 (T6, kept as merged): the company sales total asks the one basis question first; the report ask then asks
    the company before it runs, and both ride the run."""
    sorento, mocha = _two_companies(bot)
    text, calls = bot.say(_status("sales_analysis", group_by=None, sales_basis=None, basis=None), "total sales 2026")
    assert calls == [] and text.strip() == "Invoiced, delivered, ordered or outstanding?", (text, calls)
    text, calls = bot.say(_answer(2), "the middle one")
    assert calls == [] and f"{sorento} or {mocha}?" in text, (text, calls)
    text, calls = bot.say(_answer(2), "the second company")
    args = _only_report_ask(calls)
    assert args["company"] == MOCHA_ID and args["basis"] == "delivered", args


# ---------------------------------------------------------------- the Yearly comparison is the report ask (crew, 28 Oct)


def test_sales_by_year_asks_the_one_basis_question_then_a_pick_runs_the_report_ask_by_year(bot) -> None:
    two_years = {"date_filter_start": "2025-01-01", "date_filter_end": "2026-12-31"}
    text, calls = bot.say(
        _status("sales_analysis", group_by="year", sales_basis=None, basis=None, **two_years), "sales by year 2025 to 2026"
    )
    assert calls == [] and text.strip() == "Invoiced, delivered, ordered or outstanding?", (text, calls)
    text, calls = bot.say(_answer(2), "the middle one")
    assert [n for n, _a in calls] == ["crm_report_ask"], (calls, text)
    args = calls[0][1]
    assert args["group_by"] == "year" and args["basis"] == "delivered", args
    assert args["date_from"] == "2025-01-01" and args["date_to"] == "2026-12-31", args


# ---------------------------------------------------------------- a breakdown is not a ranking: no "How many?"


def test_a_group_by_with_no_count_direction_or_rank_by_is_a_breakdown_never_asked_how_many(bot) -> None:
    sep = {"date_filter_start": "2026-09-01", "date_filter_end": "2026-09-30"}
    breakdown = _status(
        "sales_ranking", group_by="sales_agent", rank_direction=None, top_n=None, rank_by=None, measure=None,
        basis=None, **sep,
    )
    text, calls = bot.say(breakdown, "Total sale for all sale agents on September 2026")
    assert calls == [] and "How many" not in text, (text, calls)
    # The measure and the basis stay asked (one numbered reply); the parser fills both from one answer.
    answered = _reply(
        message_type="business_query", domain_hint=None, intent_hint=None, entities=[], measure="amount", basis="delivered",
        open_question_answer={"mode": "fill", "picked": [], "items": [], "qty_for_all": None},
    )
    text, calls = bot.say(answered, "amount, delivered")
    args = _only_report_ask(calls)
    assert args["group_by"] == "sales_agent" and args["basis"] == "delivered" and "top_n" not in {
        k for k, v in args.items() if v is None
    }, args
    assert "How many" not in text, text


# ---------------------------------------------------------------- reviewer 9ef34d6b


@pytest.mark.parametrize("mode", ["pick", "fill"])
def test_the_yearly_axis_survives_the_basis_answer_when_the_reply_carries_by_words_null(bot, mode) -> None:
    """The live prompt defines `by_words`, so a bare answer comes back with it null while `group_by: year` rides the
    carry: the axis must not be dropped (the ask must not run as one total)."""
    two_years = {"date_filter_start": "2025-01-01", "date_filter_end": "2026-12-31"}
    text, calls = bot.say(
        _status("sales_analysis", group_by="year", by_words="yearly", sales_basis=None, basis=None, **two_years),
        "yearly sales 2025 to 2026",
    )
    assert calls == [] and text.strip() == "Invoiced, delivered, ordered or outstanding?", (text, calls)
    if mode == "pick":
        reply = _answer(1)
    else:
        reply = _reply(
            message_type="business_query", domain_hint=None, intent_hint=None, entities=[], by_words=None,
            basis="invoiced", open_question_answer={"mode": "fill", "picked": [], "items": [], "qty_for_all": None},
        )
    text, calls = bot.say(reply, "invoiced")
    args = _only_report_ask(calls)
    assert args["group_by"] == "year" and args["basis"] == "invoiced", args


def test_the_kind_question_is_never_answered_by_a_basis_the_parser_did_not_declare_an_answer_for(bot) -> None:
    """K3: `basis: "unpaid"` with NO declared answer under the kind question is not taken by shape."""
    bot.say(_bare_outstanding(), "outstanding")
    text, calls = bot.say(
        _reply(message_type="business_query", domain_hint=None, intent_hint=None, entities=[], basis="unpaid"),
        "unpaid invoices",
    )
    assert not [a for n, a in calls if a.get("basis") == "unpaid"], (calls, text)


def test_the_live_v63_company_reply_is_the_pick(bot) -> None:
    """"Sorento" under the company question, as the live parser read it: `sales_company` and `reference_positions`,
    NO declared answer, a stray `group_by: "date"`. Parser output only: it is the pick of the offered company."""
    sorento, mocha = _two_companies(bot)
    text, calls = bot.say(_status("sales_report", basis="delivered", **YEAR), "total sales 2026")
    assert calls == [] and f"{sorento} or {mocha}?" in text, (text, calls)
    live = _reply(
        message_type="business_query", domain_hint=None, intent_hint=None, entities=[],
        sales_company=sorento, reference_positions=[1], group_by="date",
    )
    text, calls = bot.say(live, sorento)
    args = _only_report_ask(calls)
    assert args["company"] != MOCHA_ID and args["company"], args
    assert not args.get("group_by"), args
