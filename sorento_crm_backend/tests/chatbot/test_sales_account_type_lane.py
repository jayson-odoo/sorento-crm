"""SALES-ACCOUNT-TYPE PR 2, Phase 2 RED tests: the bot (AT-20 to AT-27, AT-28 month half, AT-29, AT-32 to AT-36).

`documentation/plans/sales/sales-account-type-acceptance-criteria.md` section "PR 2" and the plan's section 4.

The harness of `test_report_unify_company_lane.py`: the REAL engine, lane and MCP presenter; only the parser verdict and
the MCP transport are doubles (`bot.say(verdict, message) -> (reply, tool_calls)`). Every reading below is a parser
verdict; the lane never reads the user's words.

Contract the tests pin (nothing else):
* entity `kind_said` (True = the message said which: brand or account type; None = a bare word; ABSENT = the prompt text
  does not define it), hint `brand` or `account_type`;
* verdict `group_by: "account_type"`;
* route params `account_types` (a word in the stored type's own spelling, a number or tag as typed) and `brand_ids`;
* the question is the whole reply `Cabana: brand or account type?`, capitalised off the typed word, and runs nothing;
* `app.services.chatbot.turn.context.known_account_types_line(types)`; the user block line and the entity key
  `kind_said` follow the prompt text (`Known account types`, `kind_said`).

Invented data only (public repo): types CABANA, CERAMIC, ZZTWORD, brands Cabana and ZZTWORD, AGENT A.
"""
from __future__ import annotations

import types as pytypes
import uuid
from typing import Any

import pytest

from app.models.product import Brand
from app.services.chatbot.head import parser as parser_mod
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._mc_lookup_seed import MOCHA_ID, customer as seed_customer, seed_mocha
from tests.chatbot.test_chat_state_parser_input import (  # noqa: F401  (_fresh_prompt_cache is an autouse fixture)
    _entity_props,
    _fresh_prompt_cache,
    _sent_schema,
)
from tests.chatbot.test_report_ask_lane import _e, _rank, _reply, console_no_grant  # noqa: F401
from tests.chatbot.test_report_unify_company_lane import _two_companies
from tests.chatbot.test_report_unify_routing import (  # noqa: F401  (bot / console are fixtures)
    YEAR,
    Routing,
    _customer,
    _only_report_ask,
    _status,
    bot,
    console,
)

# The real `resolve_config`, taken before any fixture replaces it with a stub.
_REAL_RESOLVE = parser_mod.resolve_config

JAN = {"date_filter_start": "2026-01-01", "date_filter_end": "2026-01-31"}
QUESTION = "Cabana: brand or account type?"
BASIS_Q = "Invoiced, delivered, ordered or outstanding?"
MISSING = object()


# --------------------------------------------------------------------------------------------- builders


def _word(raw: str = "cabana", hint: str = "brand", code: Any = "CABANA", kind_said: Any = None) -> dict[str, Any]:
    """The parser's entity for one word. `kind_said=MISSING` leaves the key out (a prompt that does not define it)."""
    ent: dict[str, Any] = {"raw": raw, "hint": hint, "canonical_code": code, "current_message": True, "confident": True}
    if kind_said is not MISSING:
        ent["kind_said"] = kind_said
    return ent


def _acct(raw: str) -> dict[str, Any]:
    """A number or tag as typed ("4", "A/C IV")."""
    return _word(raw, "account_type", None, None)


def _pick(position: int) -> dict[str, Any]:
    """The parser's declared pick of one offered option (position 1 = brand, 2 = account type; for the basis question
    2 = delivered)."""
    return _reply(
        message_type="business_query", domain_hint=None, intent_hint=None, entities=[],
        open_question_answer={"mode": "pick", "picked": [position], "items": [], "qty_for_all": None},
    )


def _sales(*entities: dict[str, Any], **over: Any) -> dict[str, Any]:
    return _status("sales_report", *entities, **{**JAN, **over})


def _ledger(db, company_id: str, name: str, dtype: str | None) -> None:
    row = seed_customer(db, company_id=company_id, name=name)
    row.autocount_debtor_type = dtype
    db.flush()


def _seed(bot, *, brands: tuple[str, ...] = ("Cabana",), ledgers: tuple[tuple[str, str], ...] = ()) -> dict[str, str]:
    """Own chain: brands (name -> id) and ledgers (customer name, stored type) in the contact's company."""
    db = bot.console.session_factory()
    try:
        ids: dict[str, str] = {}
        for name in brands:
            b = Brand(id=str(uuid.uuid4()), brand_code=name.upper(), brand_name=name, company_id=DEFAULT_COMPANY_ID)
            db.add(b)
            ids[name.upper()] = b.id
        db.flush()
        for name, dtype in ledgers:
            _ledger(db, DEFAULT_COMPANY_ID, name, dtype)
        db.commit()
        return ids
    finally:
        db.close()


#: CABANA is account 4, CERAMIC account 3 (read from the tags, never stated in code).
BOOK = (
    ("ZZT LEDGER ONE [A/C IV]", "CABANA"), ("ZZT LEDGER TWO [A/C IV]", "CABANA"),
    ("ZZT LEDGER THREE [A/C III]", "CERAMIC"), ("ZZT LEDGER FOUR [A/C III]", "CERAMIC"),
)


@pytest.fixture
def seeded(bot) -> dict[str, str]:
    ids = _seed(bot, ledgers=BOOK)
    bot.cabana = ids["CABANA"]
    return ids


@pytest.fixture
def echo(monkeypatch):
    """The route echoes the filters it ran, as the real one does (`filters[].label/values`)."""
    from tests.chatbot import test_report_unify_routing as routing

    real = routing._fake_body

    def fake(args):
        body = real(args)
        if args.get("account_types"):
            body["filters"] = [{"label": "Account type", "values": list(args["account_types"])}]
        return body

    monkeypatch.setattr(routing, "_fake_body", fake)


# --------------------------------------------------------------------------------------------- AT-20


def test_at20_a_word_that_is_both_asks_brand_or_account_type_and_runs_nothing(bot, seeded) -> None:
    text, calls = bot.say(
        _sales(_e("AGENT A", "sales_agent"), _word()), "AGENT sales for cabana in Jan"
    )
    assert calls == [], calls
    assert text.strip() == QUESTION, text


# --------------------------------------------------------------------------------------------- AT-21


def test_at21_account_type_answer_runs_the_held_ask_with_the_account_filter(bot, seeded) -> None:
    bot.say(_sales(_e("AGENT A", "sales_agent"), _word()), "AGENT sales for cabana in Jan")
    text, calls = bot.say(_pick(2), "account type")
    args = _only_report_ask(calls)
    assert args["account_types"] == ["CABANA"] and "brand_ids" not in args, args
    assert args["sales_agent_ids"] == [bot.ids["agent"]], args
    assert args["date_from"] == "2026-01-01" and args["date_to"] == "2026-01-31", args
    assert not args.get("group_by"), args


def test_at21_brand_answer_runs_the_held_ask_with_the_brand_filter(bot, seeded) -> None:
    bot.say(_sales(_e("AGENT A", "sales_agent"), _word()), "AGENT sales for cabana in Jan")
    text, calls = bot.say(_pick(1), "brand")
    args = _only_report_ask(calls)
    assert args["brand_ids"] == [seeded["CABANA"]] and "account_types" not in args, args
    assert args["sales_agent_ids"] == [bot.ids["agent"]], args
    assert args["date_from"] == "2026-01-01" and args["date_to"] == "2026-01-31", args


def test_at21_a_reply_repeating_the_word_is_the_answer_not_a_new_ask(bot, seeded) -> None:
    bot.say(_sales(_e("AGENT A", "sales_agent"), _word()), "AGENT sales for cabana in Jan")
    repeated = _reply(
        domain_hint=None, intent_hint=None,
        entities=[_word("cabana", "account_type", None, True)],
    )
    text, calls = bot.say(repeated, "cabana account")
    args = _only_report_ask(calls)
    assert args["account_types"] == ["CABANA"], args
    assert args["sales_agent_ids"] == [bot.ids["agent"]], args


def test_at20_an_outstanding_ask_asks_too(bot, seeded) -> None:
    text, calls = bot.say(
        _status("outstanding", _word(), basis="pending_delivery", date_filter_start=None, date_filter_end=None),
        "outstanding for cabana",
    )
    assert calls == [], calls
    assert text.strip() == QUESTION, text


def test_at20_a_bare_word_the_parser_hinted_account_type_still_asks(bot, seeded) -> None:
    text, calls = bot.say(_sales(_word("cabana", "account_type", None, None)), "sales for cabana in Jan")
    assert calls == [], calls
    assert text.strip() == QUESTION, text


def test_at20_the_question_keeps_the_typed_capitals(bot, seeded) -> None:
    text, calls = bot.say(_sales(_word("CABANA")), "sales for CABANA in Jan")
    assert calls == [], calls
    assert text.strip() == "CABANA: brand or account type?", text


def test_at21_two_words_in_both_ask_one_question_and_the_answer_covers_both(bot) -> None:
    ids = _seed(
        bot, brands=("Cabana", "Bravat"),
        ledgers=(("ZZT LEDGER ONE", "CABANA"), ("ZZT LEDGER TWO", "BRAVAT")),
    )
    ask = _sales(_word("cabana"), _word("bravat", "brand", "BRAVAT"))
    text, calls = bot.say(ask, "sales for cabana and bravat in Jan")
    assert calls == [] and text.strip() == "Cabana, bravat: brand or account type?", (text, calls)
    text, calls = bot.say(_pick(2), "account type")
    args = _only_report_ask(calls)
    assert args["account_types"] == ["CABANA", "BRAVAT"] and "brand_ids" not in args, args
    # a fresh conversation for the brand answer
    bot.console.session_vars = {}
    bot.say(ask, "sales for cabana and bravat in Jan")
    text, calls = bot.say(_pick(1), "brand")
    args = _only_report_ask(calls)
    assert sorted(args["brand_ids"]) == sorted([ids["CABANA"], ids["BRAVAT"]]), args
    assert "account_types" not in args, args


# --------------------------------------------------------------------------------------------- AT-22


def test_at22_the_overlap_is_read_from_the_data_a_made_up_word_asks(bot) -> None:
    ids = _seed(bot, brands=("ZZTWORD",), ledgers=(("ZZT LEDGER ONE", "ZZTWORD"),))
    text, calls = bot.say(_sales(_word("zztword", "brand", "ZZTWORD")), "sales for zztword in Jan")
    assert calls == [], calls
    assert text.strip() == "Zztword: brand or account type?", text


def test_at22_no_customer_carrying_the_word_means_the_brand_with_no_question(bot) -> None:
    ids = _seed(bot, ledgers=(("ZZT LEDGER THREE [A/C III]", "CERAMIC"),))  # nobody carries CABANA
    text, calls = bot.say(_sales(_word()), "sales for cabana in Jan")
    args = _only_report_ask(calls)
    assert args["brand_ids"] == [ids["CABANA"]] and "account_types" not in args, args


def test_at22_a_type_only_another_company_carries_asks_nothing(bot) -> None:
    ids = _seed(bot, ledgers=(("ZZT LEDGER THREE [A/C III]", "CERAMIC"),))
    db = bot.console.session_factory()
    try:
        seed_mocha(db)
        _ledger(db, MOCHA_ID, "ZZT MOCHA LEDGER [A/C IV]", "CABANA")  # the contact holds the default company only
        db.commit()
    finally:
        db.close()
    text, calls = bot.say(_sales(_word()), "sales for cabana in Jan")
    args = _only_report_ask(calls)
    assert args["brand_ids"] == [ids["CABANA"]] and "account_types" not in args, args
    assert QUESTION not in text, text


@pytest.mark.parametrize("kind", ["outstanding", "pending_delivery"])
def test_at20_an_outstanding_ask_on_an_account_type_is_a_figure_not_a_list(bot, seeded, kind) -> None:
    text, calls = bot.say(
        _status(
            "outstanding", _word("cabana", "account_type", None, True), basis=kind,
            date_filter_start=None, date_filter_end=None,
        ),
        f"{kind} cabana account",
    )
    args = _only_report_ask(calls)
    assert args["account_types"] == ["CABANA"], args
    assert args.get("group_by") not in ("sales_order", "delivery_order"), args


# --------------------------------------------------------------------------------------------- AT-23


def test_at23_cabana_brand_asks_nothing_and_runs_the_brand_filter(bot, seeded) -> None:
    text, calls = bot.say(_sales(_word(kind_said=True)), "cabana brand sales in Jan")
    args = _only_report_ask(calls)
    assert args["brand_ids"] == [seeded["CABANA"]] and "account_types" not in args, args
    assert QUESTION not in text, text


@pytest.mark.parametrize("message", ["cabana account sales in Jan", "CABANA debtor type sales in Jan"])
def test_at23_cabana_account_asks_nothing_and_runs_the_account_filter(bot, seeded, message) -> None:
    text, calls = bot.say(_sales(_word("cabana", "account_type", None, True)), message)
    args = _only_report_ask(calls)
    assert args["account_types"] == ["CABANA"] and "brand_ids" not in args, args
    assert QUESTION not in text, text


def test_at23_the_word_the_message_said_settles_it_as_brand(bot, seeded) -> None:
    text, calls = bot.say(_sales(_word(kind_said="brand")), "cabana brand sales in Jan")
    args = _only_report_ask(calls)
    assert args["brand_ids"] == [seeded["CABANA"]] and "account_types" not in args, args
    assert QUESTION not in text, text


def test_at23_the_word_the_message_said_settles_it_as_account(bot, seeded) -> None:
    text, calls = bot.say(_sales(_word("cabana", "account_type", None, "debtor type")), "cabana debtor type sales in Jan")
    args = _only_report_ask(calls)
    assert args["account_types"] == ["CABANA"] and "brand_ids" not in args, args
    assert QUESTION not in text, text


def test_at23_a_blank_kind_said_is_not_said(bot, seeded) -> None:
    text, calls = bot.say(_sales(_word(kind_said="  ")), "sales for cabana in Jan")
    assert calls == [], calls
    assert text.strip() == QUESTION, text


# --------------------------------------------------------------------------------------------- AT-24


def test_at24_a_word_that_is_only_a_stored_type_runs_the_account_filter_with_no_question(bot, seeded) -> None:
    text, calls = bot.say(_sales(_word("ceramic", "account_type", None, None)), "ceramic sales in Jan")
    args = _only_report_ask(calls)
    assert args["account_types"] == ["CERAMIC"] and "brand_ids" not in args, args
    assert "brand or account type" not in text, text


def test_at24_a_full_customer_name_containing_the_word_stays_the_customer(bot) -> None:
    db = bot.console.session_factory()
    try:
        row = seed_customer(db, company_id=DEFAULT_COMPANY_ID, name="ZZT CERAMIC TRADING SDN BHD")
        row.autocount_debtor_type = "CERAMIC"
        db.commit()
        cid = str(row.id)
    finally:
        db.close()
    text, calls = bot.say(
        _sales(_e("ZZT CERAMIC TRADING SDN BHD", "customer")), "sales for zzt ceramic trading sdn bhd in Jan"
    )
    args = _only_report_ask(calls)
    assert args["customer_ids"] == [cid] and "account_types" not in args, args


# --------------------------------------------------------------------------------------------- AT-25


@pytest.mark.parametrize("raw", ["4", "A/C IV"])
def test_at25_a_number_or_tag_runs_account_types_as_typed(bot, seeded, echo, raw) -> None:
    text, calls = bot.say(_sales(_acct(raw)), f"account type {raw} sales in Jan")
    args = _only_report_ask(calls)
    assert args["account_types"] == [raw], args
    assert f"Account type: {raw}" in text, text


def test_at25_no_reply_prints_the_type_a_number_stands_for(bot, seeded, echo) -> None:
    text, calls = bot.say(_sales(_acct("4")), "account 4 sales in Jan")
    _only_report_ask(calls)
    assert "Account type: 4" in text, text
    assert "CABANA" not in text.upper(), text


# --------------------------------------------------------------------------------------------- AT-26


def test_at26_a_word_with_its_own_number_is_the_account_filter_alone(bot, seeded) -> None:
    text, calls = bot.say(_sales(_word(), _acct("4")), "cabana sales in Jan for account 4")
    args = _only_report_ask(calls)
    assert args["account_types"] == ["4"] and "brand_ids" not in args, args
    assert QUESTION not in text, text


def test_at26_a_word_with_another_number_is_the_brand_on_that_account(bot, seeded) -> None:
    text, calls = bot.say(_sales(_word(), _acct("3")), "cabana on account type 3 sales in Jan")
    args = _only_report_ask(calls)
    assert args["account_types"] == ["3"] and args["brand_ids"] == [seeded["CABANA"]], args
    assert QUESTION not in text, text


def test_at26_a_word_said_as_brand_with_its_own_number_keeps_both(bot, seeded) -> None:
    text, calls = bot.say(_sales(_word(kind_said=True), _acct("4")), "cabana brand on account 4 sales in Jan")
    args = _only_report_ask(calls)
    assert args["account_types"] == ["4"] and args["brand_ids"] == [seeded["CABANA"]], args
    assert QUESTION not in text, text


def test_at26_a_word_said_as_account_with_its_own_number_is_one_account(bot, seeded) -> None:
    text, calls = bot.say(
        _sales(_word("cabana", "account_type", None, True), _acct("4")), "cabana account 4 sales in Jan"
    )
    args = _only_report_ask(calls)
    assert args["account_types"] == ["4"] and "brand_ids" not in args, args
    assert QUESTION not in text, text


# --------------------------------------------------------------------------------------------- AT-27 (readings that stay)


def test_at27_cabana_stock_stays_the_brand_with_no_question(bot, seeded) -> None:
    stock = _status(
        "none", _word(), domain_hint="inventory", intent_hint="check_stock", order_status=None, basis=None,
    )
    text, calls = bot.say(stock, "cabana stock")
    assert QUESTION not in text, text
    assert not any(n == "crm_report_ask" for n, _a in calls), calls


def test_at27_project_sales_stays_the_channel(bot, seeded) -> None:
    text, calls = bot.say(_sales(sales_channel="project"), "project sales in Jan")
    args = _only_report_ask(calls)
    assert args["channel"] == "project" and "account_types" not in args, args


def test_at27_sample_stays_the_category(bot, seeded) -> None:
    text, calls = bot.say(_sales(_e("ZZT CATEGORY", "category")), "sample sales in Jan")
    args = _only_report_ask(calls)
    assert args["category_ids"] == [bot.ids["category"]] and "account_types" not in args, args


def test_at27_top_accounts_stays_customers(bot, seeded) -> None:
    text, calls = bot.say(_rank(group_by="customer", top_n=5, **JAN), "top accounts in Jan")
    args = _only_report_ask(calls)
    assert args["group_by"] == "customer" and "account_types" not in args, args


# --------------------------------------------------------------------------------------------- AT-28 (month half)


def test_at28_a_month_alone_is_that_month_one_total(bot, seeded) -> None:
    text, calls = bot.say(_sales(_word(kind_said=True)), "sales for cabana in Jan")
    args = _only_report_ask(calls)
    assert args["date_from"] == "2026-01-01" and args["date_to"] == "2026-01-31", args
    assert not args.get("group_by"), args


def test_at28_after_a_held_2026_month_list_a_month_is_still_one_total(bot, seeded) -> None:
    bot.say(
        _status("sales_analysis", group_by="month", measure="amount", sales_basis="delivered", basis=None, **YEAR),
        "sales analysis by month 2026",
    )
    text, calls = bot.say(_sales(_word(kind_said=True)), "sales for cabana in Jan")
    args = _only_report_ask(calls)
    assert args["date_from"] == "2026-01-01" and args["date_to"] == "2026-01-31", args
    assert not args.get("group_by"), args
    assert args["brand_ids"] == [seeded["CABANA"]], args


def test_at28_a_month_split_across_months_stays_a_split(bot, seeded) -> None:
    text, calls = bot.say(
        _sales(_acct("4"), group_by="month", measure="amount", date_filter_start="2026-01-01", date_filter_end="2026-03-31"),
        "account 4 sales by month Jan to Mar",
    )
    args = _only_report_ask(calls)
    assert args["group_by"] == "month", args


def test_at28_a_month_split_of_a_year_stays_a_split(bot, seeded) -> None:
    text, calls = bot.say(
        _sales(_acct("4"), group_by="month", measure="amount", **YEAR), "account 4 sales by month 2026"
    )
    args = _only_report_ask(calls)
    assert args["group_by"] == "month", args


def test_at28_a_year_split_across_years_stays_a_split(bot, seeded) -> None:
    text, calls = bot.say(
        _sales(_acct("4"), group_by="year", measure="amount", date_filter_start="2025-01-01", date_filter_end="2026-12-31"),
        "account 4 sales by year 2025 to 2026",
    )
    args = _only_report_ask(calls)
    assert args["group_by"] == "year", args


# --------------------------------------------------------------------------------------------- AT-29 (AT-16's figures)


def test_at29_account_reads_100400_and_brand_reads_150000(bot, seeded) -> None:
    bot.extra_body = {"total": {"qty": 40, "amount": 100400.0}}
    bot.say(_sales(_word()), "sales for cabana in Jan")
    text, calls = bot.say(_pick(2), "account type")
    args = _only_report_ask(calls)
    assert args["account_types"] == ["CABANA"], args
    assert "RM 100,400.00" in text, text


def test_at29_brand_answer_reads_the_brand_figure(bot, seeded) -> None:
    bot.extra_body = {"total": {"qty": 60, "amount": 150000.0}}
    bot.say(_sales(_word()), "sales for cabana in Jan")
    text, calls = bot.say(_pick(1), "brand")
    args = _only_report_ask(calls)
    assert args["brand_ids"] == [seeded["CABANA"]], args
    assert "RM 150,000.00" in text, text


# --------------------------------------------------------------------------------------------- AT-32 (dealer)


@pytest.fixture
def dealer_bot(console) -> Routing:
    """A customer-scoped contact (linked to one customer of its own), not staff."""
    from tests.chatbot.test_report_ask_lane import _link_dealer

    _link_dealer(console)
    return Routing(console)


def test_at32_a_dealer_cabana_stays_the_brand_with_no_question(dealer_bot) -> None:
    ids = _seed(dealer_bot, ledgers=BOOK)
    text, calls = dealer_bot.say(_sales(_word()), "cabana sales in Jan")
    args = _only_report_ask(calls)
    assert args["brand_ids"] == [ids["CABANA"]] and "account_types" not in args, args
    assert QUESTION not in text, text


def test_at32_a_dealer_account_4_is_the_dealer_refusal(dealer_bot) -> None:
    from app.services.chatbot.lanes.business import report_ask

    _seed(dealer_bot, ledgers=BOOK)
    text, calls = dealer_bot.say(_sales(_acct("4")), "account 4 sales in Jan")
    assert calls == [], calls
    assert text.strip() == report_ask.DEALER_REFUSAL, text


# --------------------------------------------------------------------------------------------- AT-33 (unchanged)


def test_at33_a_customers_own_ledger_keeps_todays_reading_and_sends_no_account_types(bot, seeded) -> None:
    ledger = dict(_customer(bot), account=3)
    text, calls = bot.say(_sales(ledger), "zzt rank customer a/c 3 sales in Jan")
    assert not any(a.get("account_types") for n, a in calls if n == "crm_report_ask"), calls


# --------------------------------------------------------------------------------------------- AT-34 (follow-ups)


def test_at34_a_word_that_is_both_asks_and_the_answer_keeps_what_is_on_screen(bot, seeded) -> None:
    from tests.chatbot.test_report_ask_lane import PRODUCT_CODE

    bot.say(_sales(_e(PRODUCT_CODE, "product")), f"sales for {PRODUCT_CODE} in Jan")
    refine = _rank(_word(), group_by=None, top_n=None, ranking_refine=True, **JAN)
    text, calls = bot.say(refine, "and for cabana")
    assert calls == [] and text.strip() == QUESTION, (text, calls)
    text, calls = bot.say(_pick(2), "account type")
    args = _only_report_ask(calls)
    assert args["product_code"] == PRODUCT_CODE and args["account_types"] == ["CABANA"], args


def test_at34_an_account_word_replaces_the_held_account_filter(bot, seeded) -> None:
    bot.say(_sales(_word("ceramic", "account_type", None, True)), "ceramic account sales in Jan")
    refine = _rank(_word("cabana", "account_type", None, True), group_by=None, top_n=None, ranking_refine=True, **JAN)
    text, calls = bot.say(refine, "cabana account")
    args = _only_report_ask(calls)
    assert args["account_types"] == ["CABANA"], args


def test_at34_a_new_axis_keeps_the_held_account_filter(bot, seeded) -> None:
    bot.say(_sales(_word("ceramic", "account_type", None, True)), "ceramic account sales in Jan")
    text, calls = bot.say(
        _rank(group_by="sales_agent", top_n=5, ranking_refine=True, **JAN), "by sales agent"
    )
    args = _only_report_ask(calls)
    assert args["group_by"] == "sales_agent" and args["account_types"] == ["CERAMIC"], args


def test_at34_group_by_account_type_lists_one_row_per_type(bot, seeded) -> None:
    bot.extra_body = {
        "group_label": "Account type",
        "rows": [
            {"rank": 1, "name": "CABANA", "qty": 40, "amount": 100400.0},
            {"rank": 2, "name": "CERAMIC", "qty": 20, "amount": 50000.0},
        ],
        "total_count": 2, "total": {"qty": 60, "amount": 150400.0},
    }
    text, calls = bot.say(
        _status("sales_analysis", group_by="account_type", measure="amount", sales_basis="delivered", basis=None, **JAN),
        "sales by account type in Jan",
    )
    args = _only_report_ask(calls)
    assert args["group_by"] == "account_type", args
    assert "1. CABANA" in text and "2. CERAMIC" in text, text


# --------------------------------------------------------------------------------------------- AT-35 (two companies)


def test_at35_a_contact_in_two_companies_naming_only_an_account_type_is_asked_the_company(bot, seeded) -> None:
    sorento, mocha = _two_companies(bot)
    text, calls = bot.say(_sales(_word("ceramic", "account_type", None, True)), "ceramic account sales in Jan")
    assert calls == [], calls
    assert f"{sorento} or {mocha}?" in text, text


def test_at35_the_answer_runs_the_held_filter_for_that_company(bot, seeded) -> None:
    sorento, mocha = _two_companies(bot)
    bot.say(_sales(_word("ceramic", "account_type", None, True)), "ceramic account sales in Jan")
    text, calls = bot.say(
        _reply(
            message_type="business_query", domain_hint=None, intent_hint=None, entities=[],
            open_question_answer={"mode": "pick", "picked": [2], "items": [], "qty_for_all": None},
        ),
        mocha,
    )
    args = _only_report_ask(calls)
    assert args["company"] == MOCHA_ID and args["account_types"] == ["CERAMIC"], args


def test_at35_a_contact_naming_the_company_is_not_asked(bot, seeded) -> None:
    sorento, mocha = _two_companies(bot)
    text, calls = bot.say(
        _sales(_word("ceramic", "account_type", None, True), sales_company=mocha), "mocha ceramic account sales in Jan"
    )
    args = _only_report_ask(calls)
    assert args["company"] == MOCHA_ID and args["account_types"] == ["CERAMIC"], args


# --------------------------------------------------------------------------------------------- AT-36 (before the label moves)


def test_at36_known_account_types_line_is_sorted_and_none_when_empty() -> None:
    from app.services.chatbot.turn.context import known_account_types_line

    assert known_account_types_line(["CERAMIC", "CABANA"]) == "Known account types: CABANA, CERAMIC"
    assert known_account_types_line([]) is None


def test_at36_an_entity_with_no_kind_said_key_asks_nothing_and_reads_as_today(bot, seeded) -> None:
    text, calls = bot.say(_sales(_word(kind_said=MISSING)), "sales for cabana in Jan")
    args = _only_report_ask(calls)
    assert args["brand_ids"] == [seeded["CABANA"]] and "account_types" not in args, args
    assert QUESTION not in text, text


def _use_prompt(bot, raw: str) -> list[str]:
    """Seed `raw` as the production parser prompt, put the REAL resolve_config back, and record every user block."""
    from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
    from app.services import ai_assistant_service, ai_prompt_registry, llm_provider

    mp = bot.console.monkeypatch
    db = bot.console.session_factory()
    try:
        v = AIPromptVersion(
            id=str(uuid.uuid4()), name=parser_mod.PROMPT_KEY, version=1, type="text", template=raw,
            variables=["current_date"],
        )
        db.add(v)
        db.flush()
        db.add(AIPromptLabel(id=str(uuid.uuid4()), name=parser_mod.PROMPT_KEY, label="production", version_id=v.id))
        db.commit()
    finally:
        db.close()
    cfg = pytypes.SimpleNamespace(provider="openai", model="gpt-test")
    mp.setattr(ai_assistant_service, "AIAssistantConfigService", lambda d: pytypes.SimpleNamespace(get=lambda: cfg))
    mp.setattr(llm_provider, "resolve_api_key", lambda config, provider: "sk-test")
    mp.setattr(parser_mod, "resolve_config", _REAL_RESOLVE)
    ai_prompt_registry.bust_cache()
    blocks: list[str] = []

    class Spy:
        def __init__(self, inner) -> None:
            self._inner = inner

        def setattr(self, target, name, value=None, *a, **kw):
            if target is parser_mod and name == "parse":
                inner = value

                def spy(config, user_block):
                    blocks.append(str(user_block))
                    return inner(config, user_block)

                return self._inner.setattr(target, name, spy)
            return self._inner.setattr(target, name, value, *a, **kw)

        def __getattr__(self, item):
            return getattr(self._inner, item)

    bot.console.monkeypatch = Spy(mp)
    return blocks


def _line(block: str) -> list[str]:
    return [ln for ln in block.splitlines() if ln.startswith("Known account types")]


def test_at36_a_prompt_that_defines_it_gets_the_line_of_the_scoped_company_only(bot, seeded) -> None:
    db = bot.console.session_factory()
    try:
        seed_mocha(db)
        _ledger(db, MOCHA_ID, "ZZT MOCHA LEDGER", "ZZMOCHATYPE")
        db.commit()
    finally:
        db.close()
    blocks = _use_prompt(bot, "Rules {{current_date}}. Known account types lists the stored types.\n")
    bot.say(_sales(_word(kind_said=True)), "sales for cabana brand in Jan")
    assert _line(blocks[-1]) == ["Known account types: CABANA, CERAMIC"], blocks[-1]


def test_at36_a_prompt_that_does_not_define_it_gets_no_line(bot, seeded) -> None:
    blocks = _use_prompt(bot, "Rules {{current_date}}. Nothing about types here.\n")
    bot.say(_sales(_word(kind_said=MISSING)), "sales for cabana in Jan")
    assert _line(blocks[-1]) == [], blocks[-1]


def test_at36_the_line_is_absent_when_no_customer_carries_a_type(bot) -> None:
    _seed(bot, ledgers=(("ZZT LEDGER ONE", None),))
    blocks = _use_prompt(bot, "Rules {{current_date}}. Known account types lists the stored types.\n")
    bot.say(_sales(_word(kind_said=True)), "sales for cabana brand in Jan")
    assert _line(blocks[-1]) == [], blocks[-1]


def test_at32_the_line_is_never_in_a_dealers_parser_input(dealer_bot) -> None:
    _seed(dealer_bot, ledgers=BOOK)
    blocks = _use_prompt(dealer_bot, "Rules {{current_date}}. Known account types lists the stored types.\n")
    dealer_bot.say(_sales(_word()), "cabana sales in Jan")
    assert _line(blocks[-1]) == [], blocks[-1]


@pytest.mark.parametrize("defines", [True, False])
def test_at36_the_entity_schema_offers_kind_said_only_when_the_prompt_defines_it(
    monkeypatch, session_factory, defines
) -> None:
    raw = "Rules {{current_date}} compare_to by_words" + (" kind_said" if defines else "") + ".\n"
    config, schema = _sent_schema(monkeypatch, session_factory, raw)
    props = _entity_props(schema)
    required = schema["properties"]["entities"]["items"]["required"]
    assert ("kind_said" in props) is defines, props.keys()
    assert ("kind_said" in required) is defines, required


def test_at36_the_entity_schema_kind_said_is_a_string_or_null(monkeypatch, session_factory) -> None:
    config, schema = _sent_schema(monkeypatch, session_factory, "Rules {{current_date}} compare_to by_words kind_said.\n")
    assert _entity_props(schema)["kind_said"]["type"] == ["string", "null"], _entity_props(schema)["kind_said"]


# ============================================================================================= review round
from tests.chatbot import test_report_ask_lane as _lane_tests  # noqa: E402
from tests.chatbot.test_report_unify_span_binding import (  # noqa: E402,F401  (span_bot is a fixture)
    WHICH_AGENT,
    _agent_spans,
    _ent,
    _number_of,
    _pick as _span_pick,
    bot as span_bot,
)


def test_at28_a_stray_month_axis_prints_one_row_under_by_month(bot, seeded) -> None:
    bot.extra_body = {
        "group_label": "Month", "rows": [{"rank": 1, "name": "2026-01", "qty": 40, "amount": 100400.0}],
        "total_count": 1, "total": {"qty": 40, "amount": 100400.0},
    }
    text, calls = bot.say(_sales(_acct("4"), group_by="month", measure="amount"), "account 4 sales in Jan")
    args = _only_report_ask(calls)
    assert args["group_by"] == "month" and args["account_types"] == ["4"], args
    assert text.splitlines()[0].startswith("By month"), text


def test_at20_a_basis_still_owed_is_asked_first_then_the_question(bot, seeded) -> None:
    text, calls = bot.say(_sales(_e("AGENT A", "sales_agent"), _word(), basis=None), "AGENT sales for cabana in Jan")
    assert calls == [] and text.strip() == BASIS_Q, (text, calls)
    text, calls = bot.say(_pick(2), "the second")  # Delivered
    assert calls == [] and text.strip() == QUESTION, (text, calls)
    text, calls = bot.say(_pick(2), "account type")
    args = _only_report_ask(calls)
    assert args["account_types"] == ["CABANA"] and args["basis"] == "delivered", args
    assert args["sales_agent_ids"] == [bot.ids["agent"]], args


def test_at21_a_basis_then_the_question_then_the_ask_runs_with_both(bot, seeded) -> None:
    bot.say(_sales(_e("AGENT A", "sales_agent"), _word(), basis=None), "AGENT sales for cabana in Jan")
    bot.say(_pick(2), "the second")  # Delivered
    text, calls = bot.say(_pick(1), "brand")
    args = _only_report_ask(calls)
    assert args["brand_ids"] == [seeded["CABANA"]] and "account_types" not in args, args
    assert args["basis"] == "delivered" and args["sales_agent_ids"] == [bot.ids["agent"]], args
    assert args["date_from"] == "2026-01-01" and args["date_to"] == "2026-01-31", args


def test_at20_an_agent_pick_is_not_lost(span_bot) -> None:
    _seed(span_bot, ledgers=BOOK)
    text, calls = span_bot.say(
        _status("sales_report", _ent("yu", "sales_agent"), _word(), basis="delivered", **JAN),
        "sales agent yu cabana sales in Jan", spans=_agent_spans(),
    )
    assert calls == [] and WHICH_AGENT in text, (text, calls)
    n = _number_of(text, "ZZT-YU-3")
    text, calls = span_bot.say(_span_pick(n), str(n))
    assert calls == [] and text.strip() == QUESTION, (text, calls)
    text, calls = span_bot.say(_pick(2), "account type")
    args = _only_report_ask(calls)
    assert args["sales_agent_ids"] == [span_bot.ids["agents"]["ZZT-YU-3"]], args
    assert args["account_types"] == ["CABANA"], args


def test_at20_a_breakdown_gets_no_extra_question_after_the_answer(bot, seeded) -> None:
    ask = _status(
        "sales_analysis", _word(), group_by="customer", measure="amount", sales_basis="delivered", basis=None, **JAN
    )
    text, calls = bot.say(ask, "sales by customer for cabana in Jan")
    assert calls == [] and text.strip() == QUESTION, (text, calls)
    text, calls = bot.say(_pick(2), "account type")
    args = _only_report_ask(calls)
    assert args["group_by"] == "customer" and args["account_types"] == ["CABANA"], args
    assert "By quantity or by amount?" not in text, text


def test_at21_the_answer_replaces_a_held_account_filter(bot, seeded) -> None:
    text, calls = bot.say(_sales(_acct("3")), "account 3 sales in Jan")
    assert _only_report_ask(calls)["account_types"] == ["3"]
    refine = _rank(_word(), group_by=None, top_n=None, ranking_refine=True, **JAN)
    text, calls = bot.say(refine, "and for cabana")
    assert calls == [] and text.strip() == QUESTION, (text, calls)
    text, calls = bot.say(_pick(2), "account type")
    args = _only_report_ask(calls)
    assert args["account_types"] == ["CABANA"], args


FEB = {"date_filter_start": "2026-02-01", "date_filter_end": "2026-02-28"}


def _ask_open(bot) -> None:
    text, calls = bot.say(_sales(_word()), "sales for cabana in Jan")
    assert calls == [] and text.strip() == QUESTION, (text, calls)


def _open_agent(bot) -> None:
    """The word question open on AGENT A, Jan."""
    text, calls = bot.say(_sales(_e("AGENT A", "sales_agent"), _word()), "AGENT sales for cabana in Jan")
    assert calls == [] and text.strip() == QUESTION, (text, calls)


def test_at21_a_repeat_with_its_own_period_edits_the_held_ask(bot, seeded) -> None:
    _open_agent(bot)
    text, calls = bot.say(_sales(_word(kind_said="brand"), **FEB), "cabana brand in Feb")
    args = _only_report_ask(calls)
    assert args["sales_agent_ids"] == [bot.ids["agent"]], args
    assert args["brand_ids"] == [seeded["CABANA"]] and "account_types" not in args, args
    assert args["date_from"] == "2026-02-01" and args["date_to"] == "2026-02-28", args


def test_at21_a_repeat_with_its_own_axis_and_count_edits_the_held_ask(bot, seeded) -> None:
    _open_agent(bot)
    text, calls = bot.say(
        _rank(_word("cabana", "account_type", None, "account"), group_by="customer", top_n=5, **JAN),
        "cabana account by customer top 5",
    )
    args = _only_report_ask(calls)
    assert args["group_by"] == "customer" and args["top_n"] == 5 and args["account_types"] == ["CABANA"], args
    assert args["sales_agent_ids"] == [bot.ids["agent"]], args


def test_at21_a_reply_on_another_subject_drops_the_question(bot, seeded) -> None:
    _ask_open(bot)
    stock = _status(
        "none", _word(kind_said="brand"), domain_hint="inventory", intent_hint="check_stock", order_status=None,
        basis=None, domain_in_message=True,
    )
    text, calls = bot.say(stock, "cabana brand stock")
    assert not any(n == "crm_report_ask" for n, _a in calls), calls
    assert QUESTION not in text, text


def test_at26_a_bare_word_hinted_account_type_with_another_number_is_the_brand_on_it(bot, seeded) -> None:
    text, calls = bot.say(_sales(_word("cabana", "account_type", None, None), _acct("3")), "cabana on account 3 in Jan")
    args = _only_report_ask(calls)
    assert args["account_types"] == ["3"] and args["brand_ids"] == [seeded["CABANA"]], args


def _disagreeing_books(bot) -> tuple[str, str, str]:
    """Default company: 4 = CABANA. Mocha: 4 = CERAMIC, and it carries CABANA (tagged 2) as a type too."""
    sorento, mocha = _two_companies(bot)
    db = bot.console.session_factory()
    try:
        brand_id = str(uuid.uuid4())
        db.add(Brand(id=brand_id, brand_code="CABANA", brand_name="Cabana", company_id=MOCHA_ID))
        for name, dtype in (
            ("ZZT MOCHA LEDGER ONE [A/C IV]", "CERAMIC"), ("ZZT MOCHA LEDGER TWO [A/C IV]", "CERAMIC"),
            ("ZZT MOCHA LEDGER THREE [A/C II]", "CABANA"), ("ZZT MOCHA LEDGER FOUR [A/C II]", "CABANA"),
        ):
            _ledger(db, MOCHA_ID, name, dtype)
        db.commit()
    finally:
        db.close()
    return sorento, mocha, brand_id


def test_at35_books_that_disagree_keep_the_brand(bot, seeded) -> None:
    sorento, mocha, _ = _disagreeing_books(bot)
    text, calls = bot.say(_sales(_word(), _acct("4"), sales_company=mocha), "mocha cabana on account 4 sales in Jan")
    args = _only_report_ask(calls)
    assert args["company"] == MOCHA_ID and args["account_types"] == ["4"], args
    assert args.get("brand_ids"), args


def test_at35_a_word_that_asks_is_asked_the_company_first(bot, seeded) -> None:
    sorento, mocha, _ = _disagreeing_books(bot)
    text, calls = bot.say(_sales(_word()), "sales for cabana in Jan")
    assert calls == [] and f"{sorento} or {mocha}?" in text, (text, calls)
    text, calls = bot.say(_pick(2), mocha)
    assert calls == [] and text.strip() == QUESTION, (text, calls)
    text, calls = bot.say(_pick(2), "account type")
    args = _only_report_ask(calls)
    assert args["company"] == MOCHA_ID and args["account_types"] == ["CABANA"], args


# --------------------------------------------------------------------------------------------- scoped drill (report_ask.py ~2280)


@pytest.fixture
def drill(console, monkeypatch):
    from tests.chatbot import test_report_drilldown_lane as dd

    monkeypatch.setattr(_lane_tests, "_fake_body", dd._body)
    _seed(pytypes.SimpleNamespace(console=console), ledgers=BOOK)
    dd._turn1(console)
    return console, dd


def test_at26_a_scoped_drill_reads_word_and_number_alike(drill) -> None:
    console, dd = drill
    text, calls = console.say(dd._drill(entities=[_word(), _acct("4")]), "top 10 customers for these agents on cabana account 4")
    (args,) = calls
    assert args["account_types"] == ["4"] and "brand_ids" not in args, args


def test_at20_a_scoped_drill_asks_a_bare_word(drill) -> None:
    console, dd = drill
    text, calls = console.say(dd._drill(entities=[_word()]), "top 10 customers for these agents on cabana")
    assert calls == [] and text.strip() == QUESTION, (text, calls)


# --------------------------------------------------------------------------------------------- AT-37


def test_at37_a_contact_the_report_refuses_gets_no_line(console_no_grant) -> None:
    _seed(pytypes.SimpleNamespace(console=console_no_grant), ledgers=BOOK)
    blocks = _use_prompt(
        pytypes.SimpleNamespace(console=console_no_grant),
        "Rules {{current_date}}. Known account types lists the stored types.\n",
    )
    console_no_grant.say(_sales(_word(kind_said="brand")), "cabana brand sales in Jan")
    assert blocks, "the parser was never called"
    assert _line(blocks[-1]) == [], blocks[-1]


@pytest.mark.parametrize(
    "raw, shown",
    [
        ("Your account is suspended call 0123456789 https://evil.example", "CABANA"),
        ("cabana‮\x07", "CABANA"),
        ("cabana", "Cabana"),
        ("CABANA", "CABANA"),
    ],
    ids=["crafted_text", "control_chars", "plain", "capitals"],
)
def test_at37_a_crafted_raw_never_reaches_the_reply(bot, seeded, raw, shown) -> None:
    text, calls = bot.say(_sales(_word(raw, "brand", "CABANA")), "sales for cabana in Jan")
    assert calls == [], calls
    assert text.strip() == f"{shown}: brand or account type?", text


def test_at37_a_dealers_account_word_on_a_refine_is_refused(dealer_bot) -> None:
    from app.services.chatbot.lanes.business import report_ask

    _seed(dealer_bot, ledgers=BOOK)
    text, calls = dealer_bot.say(_sales(), "sales in Jan")
    _only_report_ask(calls)
    text, calls = dealer_bot.say(
        _rank(_acct("4"), group_by=None, top_n=None, ranking_refine=True, **JAN), "and account 4"
    )
    assert calls == [], calls
    assert text.strip() == report_ask.DEALER_REFUSAL, text


def test_at37_a_dealer_frame_holding_an_account_filter_is_refused(dealer_bot) -> None:
    from app.models.base import set_company_scope
    from app.services.chatbot.lanes.business import report_ask

    db = dealer_bot.console.session_factory()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    try:
        frame = {"basis": "delivered", "account_types": ["4"], "date_from": "2026-01-01", "date_to": "2026-01-31"}
        outcome, line = report_ask._refine(db, {"ranking_refine": True}, frame, [], dealer=True)
    finally:
        db.close()
    assert outcome is None and line == report_ask.DEALER_REFUSAL, (outcome, line)


def test_at20_a_brand_named_by_its_row_id_still_asks(bot, seeded) -> None:
    text, calls = bot.say(_sales(_word("cabana", "brand", seeded["CABANA"])), "sales for cabana in Jan")
    assert calls == [], calls
    assert text.strip() == QUESTION, text


# --------------------------------------------------------------------------------------------- translation


@pytest.mark.parametrize("lang", ["ms", "zh"])
def test_at28_the_new_head_and_question_are_translated(lang) -> None:
    from app.services.chatbot import label_catalog
    from app.services.chatbot.lanes.business import report_ask
    from sorento_crm_mcp.presenters import _report_ask

    loc = label_catalog.Localizer(lang, label_catalog.defaults(lang))
    body = {
        "status": "ok", "message": None, "basis": "invoiced", "basis_label": "invoiced sales", "measure": "amount",
        "group_by": "month", "group_label": "Month", "sort": "desc", "date_from": "2026-01-01", "date_to": "2026-03-31",
        "filters": [{"label": "Account type", "values": ["4"]}],
        "rows": [{"rank": 1, "name": "2026-01", "qty": 4, "amount": 100.0}], "more": 0, "total_count": 1,
        "total": {"qty": 4, "amount": 100.0},
    }
    out = loc.reply(_report_ask(body))
    assert "By month" not in out.splitlines()[0], out
    assert label_catalog.LABELS["By month"][lang] in out.splitlines()[0], out
    assert "Account type" not in out, out
    question = loc.reply(report_ask._kind_question({"kind_words": ["cabana"]}))
    assert "brand or account type" not in question, question
    assert question.startswith("Cabana"), question


# ============================================================================================= round 3
from tests.chatbot.test_report_unify_routing import KIND_QUESTION  # noqa: E402,F401
from tests.chatbot.test_report_ask_lane import TOPN_Q  # noqa: E402


def _drive(bot, first, message, *, agent_code: str | None = None, limit: int = 8):
    """Answer whatever the bot asks until a report runs. Returns (args, [the question texts asked in order])."""
    asked: list[str] = []
    text, calls = bot.say(first, message, spans=_agent_spans()) if hasattr(bot, "spans") else bot.say(first, message)
    for _ in range(limit):
        if calls:
            args = _only_report_ask(calls)
            return args, asked
        asked.append(text.strip())
        if WHICH_AGENT in text:
            n = _number_of(text, agent_code or "ZZT-YU-3")
            reply = _span_pick(n)
        else:
            reply = _pick(2)  # basis: delivered; company: the second; the word: account type
        text, calls = bot.say(reply, "2")
    raise AssertionError(("never ran", asked, text))


def test_at20_the_word_question_survives_a_count_give_up(bot, seeded) -> None:
    text, calls = bot.say(_rank(_word(), group_by="customer", top_n=None, **JAN), "top customers for cabana in Jan")
    assert calls == [] and TOPN_Q in text, (text, calls)
    text, calls = bot.say(_reply(top_n=None), "lots")
    assert calls == [] and TOPN_Q in text, (text, calls)
    text, calls = bot.say(_reply(top_n=None), "plenty")
    assert calls == [] and text.strip() == QUESTION, (text, calls)
    text, calls = bot.say(_pick(2), "account type")
    args = _only_report_ask(calls)
    assert args["top_n"] == 10 and args["account_types"] == ["CABANA"], args


def test_at20_an_agent_pick_survives_an_owed_basis(span_bot) -> None:
    _seed(span_bot, ledgers=BOOK)
    args, asked = _drive(
        span_bot, _status("sales_report", _ent("yu", "sales_agent"), _word(), basis=None, **JAN),
        "sales agent yu cabana sales in Jan",
    )
    assert asked[-1] == QUESTION, asked
    assert args["sales_agent_ids"] == [span_bot.ids["agents"]["ZZT-YU-3"]], (args, asked)
    assert args["account_types"] == ["CABANA"] and args["basis"] == "delivered", args


def test_at35_an_agent_pick_survives_the_company_question(span_bot) -> None:
    _seed(span_bot, ledgers=BOOK)
    sorento, mocha = _two_companies(span_bot)
    args, asked = _drive(
        span_bot, _status("sales_report", _ent("yu", "sales_agent"), _word(), basis="delivered", **JAN),
        "sales agent yu cabana sales in Jan",
    )
    assert asked[-1] == QUESTION and any(f"{sorento} or {mocha}?" in a for a in asked), asked
    assert args["sales_agent_ids"] == [span_bot.ids["agents"]["ZZT-YU-3"]], (args, asked)
    assert args["account_types"] == ["CABANA"] and args["company"] == MOCHA_ID, args


def test_an_agent_pick_survives_an_owed_basis_with_no_word(span_bot) -> None:
    args, asked = _drive(
        span_bot, _status("sales_report", _ent("yu", "sales_agent"), basis=None, **JAN), "sales agent yu sales in Jan"
    )
    assert any(WHICH_AGENT in a for a in asked), asked
    assert args["sales_agent_ids"] == [span_bot.ids["agents"]["ZZT-YU-3"]], (args, asked)
    assert args["basis"] == "delivered", args


def test_at21_an_echoed_held_period_is_the_answer_not_a_new_ask(bot, seeded) -> None:
    bot.say(_sales(_e("AGENT A", "sales_agent"), _word()), "AGENT sales for cabana in Jan")
    echo = _reply(
        domain_hint=None, intent_hint=None, entities=[_word("cabana", "account_type", None, "account")], **JAN
    )
    text, calls = bot.say(echo, "cabana account")
    args = _only_report_ask(calls)
    assert args["account_types"] == ["CABANA"] and args["sales_agent_ids"] == [bot.ids["agent"]], args


@pytest.mark.parametrize("mocha_ledgers", [(), (("ZZT MOCHA LEDGER ONE [A/C II]", "CERAMIC"),)], ids=["no_types", "no_4"])
def test_at35_a_company_without_the_number_does_not_count(bot, seeded, mocha_ledgers) -> None:
    _two_companies(bot)
    db = bot.console.session_factory()
    try:
        for name, dtype in mocha_ledgers:
            _ledger(db, MOCHA_ID, name, dtype)
        db.commit()
    finally:
        db.close()
    text, calls = bot.say(_sales(_word(), _acct("4")), "cabana on account 4 sales in Jan")
    args = _only_report_ask(calls)
    assert args["account_types"] == ["4"] and not args.get("brand_ids"), args


def test_at35_a_refine_on_a_held_company_reads_that_book(bot, seeded) -> None:
    sorento, mocha, _ = _disagreeing_books(bot)
    text, calls = bot.say(_sales(_acct("4"), sales_company=mocha), "mocha account 4 sales in Jan")
    assert _only_report_ask(calls)["company"] == MOCHA_ID
    refine = _rank(_word(), _acct("4"), group_by=None, top_n=None, ranking_refine=True, **JAN)
    text, calls = bot.say(refine, "and cabana")
    args = _only_report_ask(calls)
    assert args["company"] == MOCHA_ID and args["account_types"] == ["4"], args
    assert args.get("brand_ids"), args


def _repeat(**over):
    return _reply(domain_hint=None, intent_hint=None, entities=[_word("cabana", "account_type", None, "account")], **over)


@pytest.mark.parametrize("by_words", [MISSING, None], ids=["no_key", "null"])
def test_at21_a_stray_axis_on_the_repeat_is_still_the_answer(bot, seeded, by_words) -> None:
    bot.say(_sales(_e("AGENT A", "sales_agent"), _word()), "AGENT sales for cabana in Jan")
    verdict = _repeat(group_by="customer")
    if by_words is MISSING:
        verdict.pop("by_words", None)
    else:
        verdict["by_words"] = by_words
    text, calls = bot.say(verdict, "cabana account")
    args = _only_report_ask(calls)
    assert args["account_types"] == ["CABANA"] and not args.get("group_by"), args
    assert "I can rank sales by" not in text and "I can break sales down by" not in text, text


def test_at21_a_typed_axis_on_the_repeat_edits_the_held_ask(bot, seeded) -> None:
    _open_agent(bot)
    typed = _rank(
        _word("cabana", "account_type", None, "account"), group_by="customer", by_words="by customer", top_n=5, **JAN
    )
    text, calls = bot.say(typed, "cabana account by customer top 5")
    args = _only_report_ask(calls)
    assert args["group_by"] == "customer" and args["account_types"] == ["CABANA"], args
    assert args["sales_agent_ids"] == [bot.ids["agent"]], args


def test_at21_a_stray_domain_on_the_repeat_is_still_the_answer(bot, seeded) -> None:
    _ask_open(bot)
    verdict = _reply(domain_hint="master_products", intent_hint="check_product", entities=[_word(kind_said="brand")])
    verdict.pop("domain_in_message", None)
    text, calls = bot.say(verdict, "cabana brand")
    args = _only_report_ask(calls)
    assert args["brand_ids"] == [seeded["CABANA"]] and "account_types" not in args, args


def test_at21_an_echo_with_no_status_is_still_the_answer(bot, seeded) -> None:
    _ask_open(bot)
    verdict = _reply(domain_hint=None, intent_hint=None, order_status=None, entities=[_word(kind_said="brand")])
    text, calls = bot.say(verdict, "cabana brand")
    args = _only_report_ask(calls)
    assert args["brand_ids"] == [seeded["CABANA"]], args


def test_at21_a_declared_pick_with_its_own_period_uses_it(bot, seeded) -> None:
    bot.say(_sales(_e("AGENT A", "sales_agent"), _word()), "AGENT sales for cabana in Jan")
    pick = _reply(
        message_type="business_query", domain_hint=None, intent_hint=None, entities=[],
        open_question_answer={"mode": "pick", "picked": [2], "items": [], "qty_for_all": None}, **FEB,
    )
    text, calls = bot.say(pick, "account type, in Feb")
    args = _only_report_ask(calls)
    assert args["account_types"] == ["CABANA"] and args["sales_agent_ids"] == [bot.ids["agent"]], args
    assert args["date_from"] == "2026-02-01" and args["date_to"] == "2026-02-28", args


def test_at20_a_bare_word_with_an_unbound_id_still_asks(bot, seeded) -> None:
    text, calls = bot.say(_sales(_word("cabana", "brand", str(uuid.uuid4()))), "sales for cabana in Jan")
    assert calls == [], calls
    assert text.strip() == QUESTION, text


@pytest.mark.parametrize("lang", ["ms", "zh"])
def test_at28_the_account_type_ranking_and_refusals_are_translated(lang) -> None:
    from app.services.chatbot import label_catalog
    from sorento_crm_mcp.presenters import _report_ask

    loc = label_catalog.Localizer(lang, label_catalog.defaults(lang))
    rows = [{"rank": i, "name": n, "qty": 4, "amount": 100.0} for i, n in ((1, "CABANA"), (2, "CERAMIC"))]
    body = {
        "status": "ok", "message": None, "basis": "invoiced", "basis_label": "invoiced sales", "measure": "amount",
        "group_by": "account_type", "group_label": "Account type", "sort": "desc",
        "date_from": "2026-01-01", "date_to": "2026-03-31", "filters": [], "rows": rows, "more": 0,
        "total_count": 2, "total": {"qty": 8, "amount": 200.0},
    }
    head = loc.reply(_report_ask(body)).splitlines()[0]
    assert "account types" not in head and "Top" not in head, head
    for line in (
        "Account types are not loaded from AutoCount yet",
        "No account type 9. Account types: 3, 4, CERAMIC.",
    ):
        out = loc.reply(line)
        assert out != line and "ccount type" not in out.replace("CERAMIC", ""), (line, out)


# ============================================================================================= round 4
def _open_top5(bot) -> None:
    text, calls = bot.say(
        _rank(_e("AGENT A", "sales_agent"), _word(), group_by="customer", top_n=5, **JAN),
        "top 5 customers of AGENT for cabana in Jan",
    )
    assert calls == [] and text.strip() == QUESTION, (text, calls)


def test_at21_an_echoed_held_count_changes_nothing(bot, seeded) -> None:
    _open_top5(bot)
    echo = _rank(_word("cabana", "account_type", None, "account"), group_by="customer", top_n=5, **JAN)
    text, calls = bot.say(echo, "cabana account")
    args = _only_report_ask(calls)
    assert args["group_by"] == "customer" and args["top_n"] == 5, args
    assert args["sales_agent_ids"] == [bot.ids["agent"]] and args["account_types"] == ["CABANA"], args


def test_at21_a_repeat_with_its_own_count_edits_the_held_ask(bot, seeded) -> None:
    _open_top5(bot)
    own = _rank(_word("cabana", "account_type", None, "account"), group_by="customer", top_n=10, **JAN)
    text, calls = bot.say(own, "cabana account top 10")
    args = _only_report_ask(calls)
    assert args["group_by"] == "customer" and args["top_n"] == 10, args
    assert args["sales_agent_ids"] == [bot.ids["agent"]] and args["account_types"] == ["CABANA"], args


def test_at21_a_repeat_with_its_own_period_on_replace_combine_keeps_the_agent(bot, seeded) -> None:
    _open_agent(bot)
    text, calls = bot.say(_repeat(entity_op="replace_combine", **FEB), "cabana account in Feb")
    args = _only_report_ask(calls)
    assert args["sales_agent_ids"] == [bot.ids["agent"]] and args["account_types"] == ["CABANA"], args
    assert args["date_from"] == "2026-02-01" and args["date_to"] == "2026-02-28", args


def test_at21_a_repeat_with_its_own_channel_is_applied(bot, seeded) -> None:
    _open_agent(bot)
    text, calls = bot.say(_repeat(sales_channel="project", **JAN), "cabana account project")
    args = _only_report_ask(calls)
    assert args["channel"] == "project" and args["account_types"] == ["CABANA"], args


def test_at21_a_pick_with_its_own_channel_is_applied(bot, seeded) -> None:
    _open_agent(bot)
    pick = _reply(
        message_type="business_query", domain_hint=None, intent_hint=None, entities=[], sales_channel="project",
        open_question_answer={"mode": "pick", "picked": [2], "items": [], "qty_for_all": None},
    )
    text, calls = bot.say(pick, "account type, project")
    args = _only_report_ask(calls)
    assert args["channel"] == "project" and args["account_types"] == ["CABANA"], args


def test_at21_a_repeat_naming_a_company_is_applied(bot, seeded) -> None:
    sorento, mocha = _two_companies(bot)
    text, calls = bot.say(
        _sales(_e("AGENT A", "sales_agent"), _word(), sales_company=sorento), "sorento AGENT cabana sales in Jan"
    )
    assert calls == [] and text.strip() == QUESTION, (text, calls)
    text, calls = bot.say(_repeat(sales_company=mocha, **JAN), "mocha cabana account")
    args = _only_report_ask(calls)
    assert args["company"] == MOCHA_ID and args["sales_agent_ids"] == [bot.ids["agent"]], args


def test_at21_a_repeat_with_its_own_basis_is_applied(bot, seeded) -> None:
    text, calls = bot.say(
        _sales(_e("AGENT A", "sales_agent"), _word(), basis="invoiced"), "AGENT invoiced sales for cabana in Jan"
    )
    assert calls == [] and text.strip() == QUESTION, (text, calls)
    text, calls = bot.say(_repeat(basis="delivered", **JAN), "cabana account delivered")
    args = _only_report_ask(calls)
    assert args["basis"] == "delivered" and args["account_types"] == ["CABANA"], args


def test_at21_a_repeat_naming_another_filter_word_is_a_new_ask(bot, seeded) -> None:
    _open_agent(bot)
    verdict = _sales(_word("cabana", "account_type", None, "account"), _customer(bot))
    text, calls = bot.say(verdict, "cabana account for the customer")
    args = _only_report_ask(calls)
    assert args["customer_ids"] == [bot.ids["customer"]] and args["account_types"] == ["CABANA"], args
    assert "sales_agent_ids" not in args, args


@pytest.fixture
def plain_span_bot(console, monkeypatch):
    """The span bot's contact WITHOUT the office access type: a plain contact holding the sales report reveal."""
    from sqlalchemy import text as sql

    from app.services.contact_field_reveal_service import set_granted_keys
    from tests.chatbot.test_engine import CONTACT_ID
    from tests.chatbot.test_report_unify_span_binding import SpanBot

    db = console.session_factory()
    try:
        internal = db.execute(
            sql("SELECT id FROM respond_contacts WHERE respond_io_id = :cid"), {"cid": str(CONTACT_ID)}
        ).scalar_one()
        set_granted_keys(db, str(internal), ["sales_orders.sales_report"], actor_id=None)
        db.commit()
    finally:
        db.close()
    return SpanBot(console, monkeypatch)


def _agent_ask_then_link(bot):
    from tests.chatbot.test_report_ask_lane import _link_dealer

    text, calls = bot.say(
        _status("sales_report", _ent("yu", "sales_agent"), basis=None, **JAN), "sales agent yu sales in Jan",
        spans=_agent_spans(),
    )
    assert calls == [], calls
    _link_dealer(bot.console)
    return bot.say(_pick(2), "delivered")


def test_at37_a_contact_linked_between_turns_is_not_offered_agents(plain_span_bot) -> None:
    from app.services.chatbot.lanes.business import report_ask

    text, calls = _agent_ask_then_link(plain_span_bot)
    assert calls == [], calls
    assert text.strip() == report_ask.DEALER_REFUSAL, text
    assert "ZZT-YU" not in text, text


def test_at37_a_linked_staff_contact_keeps_the_agent_list(span_bot) -> None:
    from app.services.chatbot.lanes.business import report_ask

    text, calls = _agent_ask_then_link(span_bot)
    assert calls == [], calls
    assert text.strip() != report_ask.DEALER_REFUSAL, text
    assert WHICH_AGENT in text and "ZZT-YU-3" in text, text


def test_at35_a_refine_on_a_held_default_company_reads_only_its_book(bot, seeded) -> None:
    sorento, mocha, _ = _disagreeing_books(bot)
    text, calls = bot.say(_sales(_acct("4")), "account 4 sales in Jan")
    assert calls == [] and f"{sorento} or {mocha}?" in text, (text, calls)
    text, calls = bot.say(_pick(1), sorento)
    assert _only_report_ask(calls)["company"] == DEFAULT_COMPANY_ID
    refine = _rank(_word(), _acct("4"), group_by=None, top_n=None, ranking_refine=True, **JAN)
    text, calls = bot.say(refine, "and cabana")
    args = _only_report_ask(calls)
    assert args["account_types"] == ["4"] and not args.get("brand_ids"), args


def test_at35_a_scoped_drill_on_a_held_company_reads_that_book(console, monkeypatch) -> None:
    from tests.chatbot import test_report_drilldown_lane as dd
    from tests.chatbot.test_report_ask_lane import PRODUCT_CODE

    monkeypatch.setattr(_lane_tests, "_fake_body", dd._body)
    shim = pytypes.SimpleNamespace(console=console)
    _seed(shim, ledgers=BOOK)
    sorento, mocha, _ = _disagreeing_books(shim)
    _text, calls = console.say(
        _rank(_e(PRODUCT_CODE, "product"), sales_company=mocha, top_n=3), f"top 3 salesman for {PRODUCT_CODE} mocha"
    )
    assert len(calls) == 1 and calls[0]["company"] == MOCHA_ID, calls
    text, calls = console.say(dd._drill(entities=[_word(), _acct("4")]), "top 10 customers on cabana account 4")
    (args,) = calls
    assert args["account_types"] == ["4"] and args.get("brand_ids"), args


# ============================================================================================= round 5
_PICK2 = {"mode": "pick", "picked": [2], "items": [], "qty_for_all": None}


@pytest.mark.parametrize(
    "entity, key, ids_key",
    [
        (lambda b: _customer(b), "customer_ids", "customer"),
        (lambda b: _e("ZZT CATEGORY", "category"), "category_ids", "category"),
    ],
    ids=["customer", "category"],
)
def test_at21_a_pick_naming_another_filter_word_is_a_new_ask(bot, seeded, entity, key, ids_key) -> None:
    _open_agent(bot)
    verdict = _reply(
        message_type="business_query", domain_hint=None, intent_hint=None, entities=[entity(bot)],
        basis="delivered", open_question_answer=dict(_PICK2), **JAN,
    )
    text, calls = bot.say(verdict, "account type, for the customer")
    args = _only_report_ask(calls)
    assert args[key] == [bot.ids[ids_key]], args
    assert "account_types" not in args, args


def test_at21_a_pick_on_another_subject_is_a_new_ask(bot, seeded) -> None:
    _open_agent(bot)
    verdict = _reply(
        message_type="business_query", domain_hint="inventory", intent_hint="check_stock", order_status=None,
        domain_in_message=True, entities=[], open_question_answer=dict(_PICK2),
    )
    text, calls = bot.say(verdict, "2, stock")
    assert not any(n == "crm_report_ask" for n, _a in calls), calls


@pytest.mark.parametrize(
    "extra", [JAN, {"date_filter_start": None, "date_filter_end": None}, {"order_status": None}],
    ids=["jan_echoed", "null_dates", "no_status"],
)
def test_at21_a_number_answers_the_question(bot, seeded, extra) -> None:
    _open_agent(bot)
    text, calls = bot.say(_reply(domain_hint=None, intent_hint=None, entities=[_acct("4")], **extra), "account 4")
    args = _only_report_ask(calls)
    assert args["account_types"] == ["4"] and args["sales_agent_ids"] == [bot.ids["agent"]], args
    assert args["date_from"] == "2026-01-01" and args["date_to"] == "2026-01-31", args
    assert QUESTION not in text, text


def test_at21_a_word_and_number_answers_the_question(bot, seeded) -> None:
    _open_agent(bot)
    verdict = _reply(
        domain_hint=None, intent_hint=None, entities=[_word("cabana", "account_type", None, "account"), _acct("4")]
    )
    text, calls = bot.say(verdict, "cabana account 4")
    args = _only_report_ask(calls)
    assert args["account_types"] == ["4"] and "brand_ids" not in args, args
    assert args["sales_agent_ids"] == [bot.ids["agent"]], args


def test_at21_a_tag_answers_the_question(bot, seeded) -> None:
    _open_agent(bot)
    text, calls = bot.say(_reply(domain_hint=None, intent_hint=None, entities=[_acct("A/C IV")]), "A/C IV")
    args = _only_report_ask(calls)
    assert args["account_types"] == ["A/C IV"] and args["sales_agent_ids"] == [bot.ids["agent"]], args


# ============================================================================================= round 6
def _pick_of(position: int, *entities: dict[str, Any]) -> dict[str, Any]:
    return _reply(
        message_type="business_query", domain_hint=None, intent_hint=None, entities=list(entities),
        open_question_answer={"mode": "pick", "picked": [position], "items": [], "qty_for_all": None},
    )


@pytest.mark.parametrize("kind_said", [None, "brand"], ids=["bare_word", "said_brand"])
def test_at21_a_word_and_another_number_reads_as_one_message(bot, seeded, kind_said) -> None:
    _open_agent(bot)
    verdict = _reply(domain_hint=None, intent_hint=None, entities=[_word(kind_said=kind_said), _acct("3")])
    text, calls = bot.say(verdict, "cabana on account 3")
    args = _only_report_ask(calls)
    assert args["account_types"] == ["3"] and args["brand_ids"] == [seeded["CABANA"]], args
    assert args["sales_agent_ids"] == [bot.ids["agent"]], args


def test_at21_a_brand_pick_with_a_number_keeps_both(bot, seeded) -> None:
    _open_agent(bot)
    text, calls = bot.say(_pick_of(1, _acct("3")), "brand, account 3")
    args = _only_report_ask(calls)
    assert args["account_types"] == ["3"] and args["brand_ids"] == [seeded["CABANA"]], args
    assert args["sales_agent_ids"] == [bot.ids["agent"]], args


def test_at21_an_account_pick_with_a_number_is_the_number(bot, seeded) -> None:
    _open_agent(bot)
    text, calls = bot.say(_pick_of(2, _acct("3")), "account type, account 3")
    args = _only_report_ask(calls)
    assert args["account_types"] == ["3"] and "brand_ids" not in args, args
    assert args["sales_agent_ids"] == [bot.ids["agent"]], args


def test_at21_an_account_pick_with_another_type_word_is_that_type(bot, seeded) -> None:
    _open_agent(bot)
    text, calls = bot.say(_pick_of(2, _word("ceramic", "account_type", None, None)), "account type, ceramic")
    args = _only_report_ask(calls)
    assert args["account_types"] == ["CERAMIC"], args
    assert args["sales_agent_ids"] == [bot.ids["agent"]], args


def test_at21_a_product_lookup_under_the_question_stays_a_lookup(bot, seeded) -> None:
    from tests.chatbot.test_report_ask_lane import PRODUCT_CODE

    _open_agent(bot)
    verdict = _reply(
        domain_hint="master_products", intent_hint="check_product", order_status=None,
        entities=[_e(PRODUCT_CODE, "product")],
    )
    verdict.pop("domain_in_message", None)
    text, calls = bot.say(verdict, PRODUCT_CODE.lower())
    assert not any(n == "crm_report_ask" for n, _a in calls), calls
    assert BASIS_Q not in text and "Invoiced, delivered" not in text, text


# ============================================================================================= round 7
def _refine_bare(**over: Any) -> dict[str, Any]:
    return _rank(_word(), group_by=None, top_n=None, ranking_refine=True, **{**JAN, **over})


@pytest.mark.parametrize("answer", ["pick", "repeat"])
def test_at34_a_brand_answer_keeps_a_held_account_filter(bot, seeded, answer) -> None:
    text, calls = bot.say(_sales(_acct("3")), "account 3 sales in Jan")
    assert _only_report_ask(calls)["account_types"] == ["3"]
    text, calls = bot.say(_refine_bare(), "and for cabana")
    assert calls == [] and text.strip() == QUESTION, (text, calls)
    if answer == "pick":
        reply = _pick(1)
    else:
        reply = _reply(domain_hint=None, intent_hint=None, entities=[_word(kind_said="brand")])
    text, calls = bot.say(reply, "brand")
    args = _only_report_ask(calls)
    assert args["brand_ids"] == [seeded["CABANA"]] and args["account_types"] == ["3"], args


def test_at34_an_account_answer_keeps_a_held_brand(bot) -> None:
    ids = _seed(bot, brands=("Cabana", "Bravat"), ledgers=BOOK)
    text, calls = bot.say(_sales(_word("bravat", "brand", "BRAVAT")), "bravat sales in Jan")
    assert _only_report_ask(calls)["brand_ids"] == [ids["BRAVAT"]]
    text, calls = bot.say(_refine_bare(), "and for cabana")
    assert calls == [] and text.strip() == QUESTION, (text, calls)
    text, calls = bot.say(_pick(2), "account type")
    args = _only_report_ask(calls)
    assert args["account_types"] == ["CABANA"] and args["brand_ids"] == [ids["BRAVAT"]], args


def test_at21_a_second_filter_of_the_first_message_survives_a_brand_beside_the_account_answer(bot) -> None:
    ids = _seed(bot, brands=("Cabana", "Bravat"), ledgers=BOOK)
    text, calls = bot.say(_sales(_word("bravat", "brand", "BRAVAT"), _word()), "bravat and cabana sales in Jan")
    assert calls == [] and text.strip() == QUESTION, (text, calls)
    text, calls = bot.say(_pick(2), "account type")
    args = _only_report_ask(calls)
    assert args["account_types"] == ["CABANA"] and args["brand_ids"] == [ids["BRAVAT"]], args


def test_at21_a_second_filter_of_the_first_message_survives_a_type_beside_the_brand_answer(bot, seeded) -> None:
    text, calls = bot.say(
        _sales(_word("ceramic", "account_type", None, None), _word()), "ceramic and cabana sales in Jan"
    )
    assert calls == [] and text.strip() == QUESTION, (text, calls)
    text, calls = bot.say(_pick(1), "brand")
    args = _only_report_ask(calls)
    assert args["brand_ids"] == [seeded["CABANA"]] and args["account_types"] == ["CERAMIC"], args


def test_at35_a_company_picked_at_the_question_narrows_the_book(bot, seeded) -> None:
    sorento, mocha, _ = _disagreeing_books(bot)
    text, calls = bot.say(_sales(_acct("4")), "account 4 sales in Jan")
    assert calls == [] and f"{sorento} or {mocha}?" in text, (text, calls)
    text, calls = bot.say(_pick(1), sorento)
    assert _only_report_ask(calls)["company"] == DEFAULT_COMPANY_ID
    refine = _rank(_word(), _acct("4"), group_by=None, top_n=None, ranking_refine=True, **JAN)
    text, calls = bot.say(refine, "and cabana")
    args = _only_report_ask(calls)
    assert args["account_types"] == ["4"] and "brand_ids" not in args, args


def test_at37_an_answer_never_prints_a_crafted_word(bot, seeded) -> None:
    _ask_open(bot)
    crafted = ("x" * 1500) + "‮\x07" + ("y" * 1500)
    verdict = _reply(
        domain_hint=None, intent_hint=None, entities=[_word("cabana", "brand", crafted, "brand")],
    )
    text, calls = bot.say(verdict, "cabana brand")
    assert calls == [], calls
    assert text.strip() == "I don't know that brand.", text


# ============================================================================================= round 6 (AT-35 follow-ups)


def test_at35_b_followup_naming_only_an_account_keeps_the_held_company(bot, seeded) -> None:
    """An account number names no company, so it is no subject for the company question: the held company stays."""
    sorento, mocha, _ = _disagreeing_books(bot)
    text, calls = bot.say(_sales(_acct("4"), sales_company=mocha), "mocha account 4 sales in Jan")
    assert _only_report_ask(calls)["company"] == MOCHA_ID
    # Control: a follow-up naming no subject keeps the held company (passes today; guards the fix from over-reaching).
    follow = _sales(ranking_refine=False, entity_op="reuse")
    text, calls = bot.say(follow, "and for Jan")
    assert _only_report_ask(calls)["company"] == MOCHA_ID, (text, calls)
    # The case: not a refine, names only account 4.
    follow = _sales(_acct("4"), ranking_refine=False, entity_op="reuse")
    text, calls = bot.say(follow, "and account 4")
    assert f"{sorento} or {mocha}?" not in text, text
    args = _only_report_ask(calls)
    assert args["company"] == MOCHA_ID and args["account_types"] == ["4"], args


def _refine_all_customers(*entities: dict[str, Any]) -> dict[str, Any]:
    return _rank(
        *entities, group_by=None, top_n=None, ranking_refine=True, broaden_axis="customer", broaden_to="all", **JAN
    )


def test_at35_c_refine_dropping_the_held_customer_with_a_covered_word_asks_no_company(bot, seeded) -> None:
    """Coverage test for the guard the merge added (expected to pass before any fix): a word an account number made
    redundant is no subject for the company question; with no covered word the question is still asked."""
    sorento, mocha = _two_companies(bot)
    held = _rank(_customer(bot), group_by="product", top_n=3, **JAN)
    text, calls = bot.say(held, "top 3 products for the customer in Jan")
    args = _only_report_ask(calls)
    assert args.get("customer_ids") and not args.get("company"), args
    # No covered word: dropping the customer on a two-company contact asks the company.
    text, calls = bot.say(_refine_all_customers(), "how about all customers")
    assert calls == [] and f"{sorento} or {mocha}?" in text, (text, calls)
    bot.say(held, "top 3 products for the customer in Jan")
    # Covered word: cabana with account 4, where every company reads 4 as CABANA, asks no company question.
    text, calls = bot.say(_refine_all_customers(_word(), _acct("4")), "all customers on cabana account 4")
    assert f"{sorento} or {mocha}?" not in text, text
    args = _only_report_ask(calls)
    assert not args.get("customer_ids") and args["account_types"] == ["4"], args
