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
    CUSTOMER_NAME,
    YEAR,
    _e,
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
    assert [o["code"] for o in shown["options"]] == ["Undelivered orders", "Pending delivery"], shown  # owner 29 Oct: unpaid is not offered


def test_the_kind_answered_by_the_parsers_pick_position_runs_that_kind_with_no_dates(bot) -> None:
    text, calls = bot.say(_bare_outstanding(), "outstanding")
    assert calls == [], calls
    text, calls = bot.say(_answer(2), "the delivery one")
    args = _only_report_ask(calls)
    assert args["basis"] == "pending_delivery" and "date_from" not in args and "date_to" not in args, args


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


@pytest.mark.parametrize("basis", ["invoiced", "delivered", "ordered"])
def test_the_kind_question_is_not_answered_by_a_basis_outside_the_offered_kinds(bot, basis) -> None:
    """K3 (i): the kind question offers outstanding / pending_delivery / unpaid. A parser `basis` that is NOT one of them
    never answers it and never runs that basis. (The old K3 refused every undeclared basis; the owner rule is about
    message text, and `basis` is a parser field resolved against the offered options, AC-RU-17c.)"""
    bot.say(_bare_outstanding(), "outstanding")
    text, calls = bot.say(
        _reply(message_type="business_query", domain_hint=None, intent_hint=None, entities=[], basis=basis), basis
    )
    assert calls == [] and "Undelivered orders" in text, (calls, text)  # the kind is asked again


def test_the_kind_question_with_a_null_basis_and_no_declared_answer_runs_nothing(bot) -> None:
    """K3 (ii): no parser basis and no declared answer: nothing runs."""
    bot.say(_bare_outstanding(), "outstanding")
    text, calls = bot.say(
        _reply(message_type="business_query", domain_hint=None, intent_hint=None, entities=[], basis=None), "unpaid invoices"
    )
    assert calls == [], (calls, text)


@pytest.mark.parametrize("kind", ["outstanding", "pending_delivery", "unpaid"])
def test_the_kind_question_is_answered_by_a_parser_basis_among_the_offered_kinds(bot, kind) -> None:
    """The parser's `basis` naming an offered kind IS the answer, whatever domain or intent hint it also carried."""
    bot.say(_bare_outstanding(), "outstanding")
    text, calls = bot.say(
        _reply(message_type="business_query", domain_hint="master_products", intent_hint="check_product", entities=[], basis=kind),
        "that one",
    )
    assert _only_report_ask(calls)["basis"] == kind, (calls, text)


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


# ---------------------------------------------------------------- reviewer ec60a404: the company pick skip is narrow


def _under_the_company_question(bot):
    sorento, mocha = _two_companies(bot)
    text, calls = bot.say(_status("sales_report", basis="delivered", **YEAR), "total sales 2026")
    assert calls == [] and f"{sorento} or {mocha}?" in text, (text, calls)
    return sorento, mocha


def test_a_fresh_ranking_naming_a_company_under_the_company_question_is_a_new_ask(bot) -> None:
    """`sales_company` alone is not the pick: a ranking with a typed axis and a count is its own ask."""
    sorento, _mocha = _under_the_company_question(bot)
    fresh = _reply(
        message_type="business_query", domain_hint="order", intent_hint="check_order", order_status="sales_ranking",
        ranking_refine=False, group_by="customer", by_words="dealers", top_n=5, sales_company=sorento,
        domain_in_message=False, entities=[], **YEAR,
    )
    text, calls = bot.say(fresh, "top 5 dealers for sorento")
    assert calls == [] and "By quantity or by amount?" in text, (text, calls)


@pytest.mark.parametrize(
    "shape",
    [
        # `by_words` is ABSENT (a prompt version without it) or null: the `group_by` is a guess, never a typed axis.
        dict(order_status="sales_ranking", ranking_refine=False, group_by="customer"),
        dict(order_status="sales_report", group_by="date"),
        dict(order_status="sales_report", group_by="customer", by_words=None),
    ],
    ids=["ranking-no-typed-axis", "report-stray-axis", "report-null-by-words"],
)
def test_the_two_shapes_the_company_pick_skip_exists_for_are_the_pick(bot, shape) -> None:
    """The live parser reads a bare "Sorento" as one of these: no typed axis (`by_words` null) and no count, so the
    `group_by` is a guess; the matched company is the answer and the held total runs for it."""
    sorento, _mocha = _under_the_company_question(bot)
    reply = _reply(
        message_type="business_query", domain_hint="order", intent_hint="check_order", entities=[],
        sales_company=sorento, domain_in_message=False, **shape,
    )
    text, calls = bot.say(reply, sorento)
    args = _only_report_ask(calls)
    assert args["company"] and args["company"] != MOCHA_ID and not args.get("group_by"), args


# ---------------------------------------------------------------- hand test 2 (c858f429)


def test_a_breakdown_asks_the_basis_then_the_company_never_the_measure_and_runs_every_row(bot) -> None:
    """(a) "Total sale for all sale agents on September 2026": the required field first (the basis only: a breakdown
    shows both measures), the company last, then it runs by amount over every row."""
    from app.services.company_scope import DEFAULT_COMPANY_ID

    sorento, mocha = _two_companies(bot)
    sep = {"date_filter_start": "2026-09-01", "date_filter_end": "2026-09-30"}
    breakdown = _status(
        "sales_ranking", group_by="sales_agent", rank_direction=None, top_n=None, rank_by=None, measure=None,
        basis=None, **sep,
    )
    text, calls = bot.say(breakdown, "Total sale for all sale agents on September 2026")
    assert calls == [] and text.strip() == "Invoiced, delivered, ordered or outstanding?", (text, calls)
    text, calls = bot.say(_answer(2), "the middle one")
    assert calls == [] and f"{sorento} or {mocha}?" in text, (text, calls)
    text, calls = bot.say(_answer(1), "the first company")
    args = _only_report_ask(calls)
    assert args["group_by"] == "sales_agent" and args["basis"] == "delivered", args
    assert args["company"] == DEFAULT_COMPANY_ID and args["top_n"] == 100 and not args.get("measure"), args
    assert args["date_from"] == "2026-09-01" and args["date_to"] == "2026-09-30", args


def test_a_ranking_still_asks_the_measure(bot) -> None:
    sep = {"date_filter_start": "2026-09-01", "date_filter_end": "2026-09-30"}
    ranking = _status(
        "sales_ranking", group_by="sales_agent", rank_direction="top", top_n=5, rank_by=None, measure=None, basis=None, **sep
    )
    text, calls = bot.say(ranking, "top 5 sales agents on September 2026")
    assert calls == [] and "By quantity or by amount?" in text, (text, calls)


def test_a_fresh_bare_outstanding_after_a_sales_total_asks_the_kind_and_inherits_no_period(bot) -> None:
    """(e) Owner Q2 + AC-RU-8c: a NEW outstanding ask (the parser flags no refine) the parser picked no kind for always
    asks the kind, even with a delivered total held; it uses only a period named in its own message."""
    text, calls = bot.say(_status("sales_report", basis="delivered", **YEAR), "total sales 2026")
    assert [n for n, _a in calls] == ["crm_report_ask"], (text, calls)
    text, calls = bot.say(_bare_outstanding(), "outstanding")
    assert calls == [] and "Undelivered orders" in text, (text, calls)
    text, calls = bot.say(_answer(2), "the delivery one")
    args = _only_report_ask(calls)
    assert args["basis"] == "pending_delivery" and "date_from" not in args and "date_to" not in args, args


def test_a_flagged_refine_to_outstanding_never_infers_the_kind_but_keeps_the_period_on_screen(bot) -> None:
    """(e) A follow-up the parser flags `ranking_refine` keeps what is on screen (AC-RU-16), its period included, but
    the kind is still asked, never inferred from the held delivered basis."""
    bot.say(_status("sales_report", basis="delivered", **YEAR), "total sales 2026")
    text, calls = bot.say(_bare_outstanding(ranking_refine=True), "outstanding")
    assert calls == [] and "Undelivered orders" in text, (text, calls)
    text, calls = bot.say(_answer(2), "the delivery one")
    args = _only_report_ask(calls)
    assert args["basis"] == "pending_delivery" and args["date_from"] == "2026-01-01" and args["date_to"] == "2026-12-31", args


@pytest.mark.parametrize("status", ["outstanding"])
def test_a_fresh_outstanding_kind_the_parser_picked_drops_the_carried_period_a_refine_keeps_it(bot, status) -> None:
    """(e) The parser naming the kind (`basis: outstanding`) is not asked; a fresh ask has all dates, a refine keeps 2026."""
    bot.say(_status("sales_report", basis="delivered", **YEAR), "total sales 2026")
    text, calls = bot.say(_bare_outstanding(order_status=status, basis="outstanding"), "outstanding")
    args = _only_report_ask(calls)
    assert args["basis"] == "outstanding" and "date_from" not in args and "date_to" not in args, args
    bot.say(_status("sales_report", basis="delivered", **YEAR), "total sales 2026")
    text, calls = bot.say(_bare_outstanding(order_status=status, basis="outstanding", ranking_refine=True), "by outstanding")
    args = _only_report_ask(calls)
    assert args["basis"] == "outstanding" and args["date_from"] == "2026-01-01", args


def test_a_sales_ranking_refine_to_the_outstanding_kind_keeps_the_period_on_screen(bot) -> None:
    bot.say(_status("sales_report", basis="delivered", **YEAR), "total sales 2026")
    text, calls = bot.say(
        _bare_outstanding(order_status="sales_ranking", basis="outstanding", ranking_refine=True), "by outstanding"
    )
    args = _only_report_ask(calls)
    assert args["basis"] == "outstanding" and args["date_from"] == "2026-01-01", args


@pytest.mark.parametrize(
    "shape",
    [
        dict(order_status="sales_ranking", group_by="customer"),
        dict(order_status="outstanding", group_by="customer"),
        dict(order_status=None, group_by=None),
    ],
    ids=["stray-ranking-axis", "stale-outstanding-axis", "bare"],
)
def test_reply_one_under_the_sales_order_list_offer_opens_the_list(bot, shape) -> None:
    """(b) The open offer is answered before any axis check: a parser position 1 opens the list whatever status or
    axis the real parse also carried."""
    text, calls = bot.say(_status("outstanding", basis="outstanding", **NO_DATES), "undelivered orders")
    assert "Reply 1 for the sales order list." in text, (text, calls)
    reply = _reply(
        message_type="business_query", domain_hint=None, intent_hint=None, entities=[], reference_positions=[1],
        by_words=None, **shape,
    )
    text, calls = bot.say(reply, "1")
    args = _only_report_ask(calls)
    assert args["group_by"] == "sales_order" and args["basis"] == "outstanding", args


# ---------------------------------------------------------------- reviewer 71da74ae: a switch to an outstanding axis keeps no sales basis


def _product_ranking(**over: Any) -> dict[str, Any]:
    return _status(
        "sales_ranking",
        **{"group_by": "product", "rank_direction": "top", "top_n": 5, "measure": "amount", "basis": "delivered", **YEAR, **over},
    )


def test_p1_a_new_outstanding_axis_after_a_delivered_ranking_asks_the_kind_and_runs_nothing_on_delivered(bot) -> None:
    """P1: the S6c carry must not copy the held DELIVERED basis onto an outstanding ask the parser named no kind for."""
    text, calls = bot.say(_product_ranking(), "top 5 products 2026")
    assert [n for n, _a in calls] == ["crm_report_ask"], (text, calls)
    text, calls = bot.say(_bare_outstanding(group_by="customer"), "outstanding by customer")
    assert calls == [] and "Undelivered orders" in text, (text, calls)
    text, calls = bot.say(_answer(1), "the first one")
    args = _only_report_ask(calls)
    assert args["basis"] == "outstanding" and args["group_by"] == "customer", args
    assert "date_from" not in args and "date_to" not in args, args  # a switch from a sales basis drops the held period


def test_p2_a_by_x_over_an_outstanding_ranking_keeps_the_held_period(bot) -> None:
    """P2 (AC-RU-16): the source frame already an outstanding kind: a new axis keeps the 2026 on screen."""
    text, calls = bot.say(_bare_outstanding(basis="outstanding", group_by="product", rank_direction="top", top_n=5, measure="amount", **YEAR), "outstanding products 2026")
    assert [n for n, _a in calls] == ["crm_report_ask"], (text, calls)
    text, calls = bot.say(_bare_outstanding(basis="outstanding", group_by="customer", rank_direction="top", top_n=5, measure="amount"), "outstanding by customer")
    args = _only_report_ask(calls)
    assert args["basis"] == "outstanding" and args["group_by"] == "customer", args
    assert args["date_from"] == "2026-01-01" and args["date_to"] == "2026-12-31", args


def test_held_total_path_does_not_lend_a_sales_total_period_to_an_outstanding_kind(bot) -> None:
    """The HELD_KEY path (a held sales TOTAL, no ranking): a new outstanding axis the parser named the kind for drops the
    sales period (kills M7: always use the held period)."""
    bot.say(_status("sales_report", basis="delivered", **YEAR), "total sales 2026")
    text, calls = bot.say(
        _bare_outstanding(basis="outstanding", group_by="customer", rank_direction="top", top_n=5, measure="amount", entity_op="reuse"),
        "outstanding by customer",
    )
    args = _only_report_ask(calls)
    assert args["basis"] == "outstanding" and "date_from" not in args, args


def test_held_outstanding_total_keeps_its_period_for_a_new_axis(bot) -> None:
    """AC-RU-16 on the held-total path: an outstanding total for 2026, then "by customer", keeps 2026."""
    bot.say(_bare_outstanding(basis="outstanding", **YEAR), "outstanding 2026")
    text, calls = bot.say(
        _bare_outstanding(basis="outstanding", group_by="customer", rank_direction="top", top_n=5, measure="amount", entity_op="reuse"),
        "by customer",
    )
    args = _only_report_ask(calls)
    assert args["group_by"] == "customer" and args["date_from"] == "2026-01-01" and args["date_to"] == "2026-12-31", args


def test_held_sales_total_then_an_outstanding_ask_drops_the_period_and_asks_the_kind(bot) -> None:
    """The counterpart: a sales total for 2026, then an outstanding ask with no kind: the kind is asked and the sales
    period is not lent to it."""
    bot.say(_status("sales_report", basis="delivered", **YEAR), "total sales 2026")
    text, calls = bot.say(
        _bare_outstanding(group_by="customer", rank_direction="top", top_n=5, measure="amount", entity_op="reuse"),
        "outstanding by customer",
    )
    assert calls == [] and "Undelivered orders" in text, (text, calls)
    text, calls = bot.say(_answer(1), "the first one")
    args = _only_report_ask(calls)
    assert args["basis"] == "outstanding" and "date_from" not in args, args


def test_a_kind_answer_that_also_binds_a_customer_runs_for_that_customer_never_the_whole_scope(bot) -> None:
    """Under the kind question, a parse with `basis: unpaid` AND a customer entity bound this turn keeps that customer:
    the run carries the filter (or is a fresh ask that applies it), never the contact's whole scope."""
    bot.say(_bare_outstanding(), "outstanding")
    reply = _reply(
        message_type="business_query", domain_hint=None, intent_hint=None, basis="unpaid",
        entities=[_e(CUSTOMER_NAME, "customer")],
    )
    text, calls = bot.say(reply, "unpaid for that customer")
    args = _only_report_ask(calls)
    assert args["basis"] == "unpaid" and args.get("customer_ids") == [bot.ids["customer"]], args


# ---------------------------------------------------------------- B2: a whole new ask under the kind question


def _no_kind_question_or_basis_refusal(text: str) -> None:
    assert "Undelivered orders" not in text and "as a basis" not in text, text


def test_b2a_a_fresh_sales_ask_naming_basis_and_period_under_the_kind_question_runs_that_ask(bot) -> None:
    """B2a: "invoiced sales this year" under the kind question is a NEW ask, not a basis answer to the kind question."""
    bot.say(_bare_outstanding(), "outstanding")
    reply = _status("sales_analysis", group_by=None, measure=None, sales_basis="invoiced", sales_company=None, basis="invoiced", **YEAR)
    text, calls = bot.say(reply, "invoiced sales this year")
    _no_kind_question_or_basis_refusal(text)
    args = _only_report_ask(calls)
    assert args["basis"] == "invoiced" and args.get("date_from") == YEAR["date_filter_start"], args


def test_b2a_live_a_declared_fill_with_a_fresh_invoiced_sales_ask_under_the_kind_question_runs_that_ask(bot) -> None:
    """Step 20 live parse: declared `fill`, basis and sales_basis invoiced, `sales_analysis`, 2026, domain order."""
    bot.say(_bare_outstanding(), "outstanding")
    reply = _status(
        "sales_analysis", group_by=None, measure=None, basis="invoiced", sales_basis="invoiced", sales_company=None,
        domain_in_message=True, entity_op="reuse", by_words=None,
        open_question_answer={"mode": "fill", "items": [], "picked": [], "qty_for_all": None}, **YEAR,
    )
    text, calls = bot.say(reply, "invoiced sales this year")
    _no_kind_question_or_basis_refusal(text)
    if calls:
        args = _only_report_ask(calls)
        assert args["basis"] == "invoiced" and args.get("date_from") == YEAR["date_filter_start"], args


def test_b2b_a_fresh_delivered_sales_report_under_the_kind_question_is_not_the_kind_question_again(bot) -> None:
    """B2b: a sales-report ask with basis delivered runs, or asks only what it is missing; never the kind question."""
    bot.say(_bare_outstanding(), "outstanding")
    text, calls = bot.say(_status("sales_report", basis="delivered"), "total sales this year")
    _no_kind_question_or_basis_refusal(text)
    assert _only_report_ask(calls)["basis"] == "delivered", calls


def test_b2c_an_invoiced_parse_binding_a_customer_under_the_kind_question_is_never_the_kind_question_or_a_run_without_the_customer(bot) -> None:
    """B2c: basis invoiced + a customer bound this turn, no domain hint: not the kind question; any run keeps the customer."""
    bot.say(_bare_outstanding(), "outstanding")
    reply = _reply(
        message_type="business_query", domain_hint=None, intent_hint=None, basis="invoiced",
        entities=[_e(CUSTOMER_NAME, "customer")],
    )
    text, calls = bot.say(reply, "invoiced for that customer")
    _no_kind_question_or_basis_refusal(text)
    assert calls == [], calls


def test_b4_a_kind_pick_by_position_that_also_binds_a_customer_runs_for_that_customer_never_the_whole_scope(bot) -> None:
    """Kind option 2 is Pending delivery; a position pick AND a customer bound this turn keeps the customer."""
    text, calls = bot.say(_bare_outstanding(), "outstanding")
    low = text.lower()
    assert low.index("pending delivery") > low.index("undelivered orders") and "unpaid" not in low, text
    reply = _reply(
        message_type="business_query", domain_hint=None, intent_hint=None, by_words=None, reference_positions=[2],
        entities=[_e(CUSTOMER_NAME, "customer")],
        open_question_answer={"mode": "pick", "picked": [2], "items": [], "qty_for_all": None},
    )
    text, calls = bot.say(reply, "the delivery one for that customer")
    args = _only_report_ask(calls)
    assert args["basis"] == "pending_delivery" and args.get("customer_ids") == [bot.ids["customer"]], args


# ---------------------------------------------------------------- B5: the kind under the kind question, with a subject


def _kind_with_customer(bot, *, declared=None, positions=(), basis=None):
    text, calls = bot.say(_bare_outstanding(), "outstanding")
    low = text.lower()
    assert low.index("undelivered orders") < low.index("pending delivery") and "unpaid" not in low, text
    extra = {"basis": basis} if basis else {}
    reply = _reply(
        message_type="business_query", domain_hint=None, intent_hint=None, by_words=None,
        reference_positions=list(positions), entities=[_e(CUSTOMER_NAME, "customer")],
        open_question_answer=declared, **extra,
    )
    return bot.say(reply, "that one for that customer")


def _pick(*positions: int) -> dict[str, Any]:
    return {"mode": "pick", "picked": list(positions), "items": [], "qty_for_all": None}


def test_p1_a_declared_pick_with_a_customer_and_no_positions_runs_that_kind_for_the_customer(bot) -> None:
    text, calls = _kind_with_customer(bot, declared=_pick(1))
    args = _only_report_ask(calls)
    assert args["basis"] == "outstanding" and args.get("customer_ids") == [bot.ids["customer"]], args


def test_p2_the_declared_pick_wins_over_reference_positions(bot) -> None:
    text, calls = _kind_with_customer(bot, declared=_pick(2), positions=[1])
    args = _only_report_ask(calls)
    assert args["basis"] == "pending_delivery" and args.get("customer_ids") == [bot.ids["customer"]], args


def test_p6_a_declared_cancel_is_honoured_over_reference_positions(bot) -> None:
    cancel = {"mode": "cancel", "picked": [], "items": [], "qty_for_all": None}
    text, calls = _kind_with_customer(bot, declared=cancel, positions=[2])
    assert not [n for n, a in calls if n == "crm_report_ask"], (calls, text)


def test_p3_the_parsers_offered_kind_basis_wins_over_reference_positions(bot) -> None:
    text, calls = _kind_with_customer(bot, positions=[1], basis="pending_delivery")
    args = _only_report_ask(calls)
    assert args["basis"] == "pending_delivery" and args.get("customer_ids") == [bot.ids["customer"]], args


def test_p7_a_declared_fill_naming_a_kind_with_a_customer_runs_that_kind_for_the_customer(bot) -> None:
    bot.say(_bare_outstanding(), "outstanding")
    reply = _reply(
        message_type="business_query", domain_hint=None, intent_hint=None, by_words=None, basis="unpaid",
        entities=[_e(CUSTOMER_NAME, "customer")],
        open_question_answer={"mode": "fill", "picked": [], "items": [], "qty_for_all": None},
    )
    text, calls = bot.say(reply, "unpaid for that customer")
    args = _only_report_ask(calls)
    assert args["basis"] == "unpaid" and args.get("customer_ids") == [bot.ids["customer"]], args
