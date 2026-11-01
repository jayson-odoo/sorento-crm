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
from tests.chatbot.test_chat_state_parser_input import _entity_props, _sent_schema  # noqa: F401
from tests.chatbot.test_report_ask_lane import _e, _rank, _reply
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


def test_at20_the_question_comes_before_a_basis_that_is_also_owed(bot, seeded) -> None:
    text, calls = bot.say(_sales(_e("AGENT A", "sales_agent"), _word(), basis=None), "AGENT sales for cabana in Jan")
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


def test_at21_a_basis_still_owed_is_asked_next_then_the_ask_runs(bot, seeded) -> None:
    bot.say(_sales(_e("AGENT A", "sales_agent"), _word(), basis=None), "AGENT sales for cabana in Jan")
    text, calls = bot.say(_pick(2), "account type")
    assert calls == [] and text.strip() == BASIS_Q, (text, calls)
    text, calls = bot.say(_pick(2), "the second")  # Delivered
    args = _only_report_ask(calls)
    assert args["account_types"] == ["CABANA"] and args["basis"] == "delivered", args
    assert args["sales_agent_ids"] == [bot.ids["agent"]] and args["date_from"] == "2026-01-01", args


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
        bot, brands=("Cabana", "Sorento"),
        ledgers=(("ZZT LEDGER ONE", "CABANA"), ("ZZT LEDGER TWO", "SORENTO")),
    )
    ask = _sales(_word("cabana"), _word("sorento", "brand", "SORENTO"))
    text, calls = bot.say(ask, "sales for cabana and sorento in Jan")
    assert calls == [] and text.strip() == "Cabana, sorento: brand or account type?", (text, calls)
    text, calls = bot.say(_pick(2), "account type")
    args = _only_report_ask(calls)
    assert args["account_types"] == ["CABANA", "SORENTO"] and "brand_ids" not in args, args
    # a fresh conversation for the brand answer
    bot.console.session_vars = {}
    bot.say(ask, "sales for cabana and sorento in Jan")
    text, calls = bot.say(_pick(1), "brand")
    args = _only_report_ask(calls)
    assert sorted(args["brand_ids"]) == sorted([ids["CABANA"], ids["SORENTO"]]), args
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
