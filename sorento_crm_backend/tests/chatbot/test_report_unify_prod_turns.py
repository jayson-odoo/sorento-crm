"""REPORT-UNIFY offline eval: real prod turns P1, P2, P3, P8, P10 of
`documentation/plans/reports/CARD-report-unify-27oct.md` section 3.

The same console-turn harness as `test_report_unify_routing.py` (the REAL engine, lane and MCP presenter;
doubles are the parser, which returns the emission a model would for the message, and the MCP transport).
Every row is a seeded fake: no customer, agent or product name here is real. The agents carry placeholder
codes, so "<agent S>" and "WT" stand for ZZTS and ZZTWT.

Each docstring cites the P id and the prod turn id. The message body is the card's wording, the parse is what
the parser would emit for it.
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot.test_report_unify_routing import (  # noqa: F401  (console, bot are fixtures)
    KIND_QUESTION,
    NO_DATES,
    SEP,
    YEAR,
    Routing,
    _named,
    _only_report_ask,
    _status,
    bot,
    console,
)
from tests.chatbot.test_report_ask_lane import _e, _rank, _reply

AGENT_S_CODES = ["ZZTS I", "ZZTS III", "ZZTS IV"]  # one person, three accounts (same code stem)
AGENT_WT = "ZZTWT"
WC = "ZZT WATER CLOSET"
P286 = "SRTWC286-SH"
P286_NEW = "SRTWC286-SH-NEW"
P8518 = "SRTWC8518-SH"
P8518_250 = "SRTWC8518-SH-250"


def _seed(bot_: Routing) -> dict[str, Any]:
    """The fake rows these turns need, on top of the harness's (Sorento brand, AGENT A, ZZT CATEGORY)."""
    from app.models.product import ProductCategory
    from app.models.sales_agent import SalesAgent
    from tests._mc_lookup_seed import product

    db = bot_.console.session_factory()
    try:
        out: dict[str, Any] = {}
        wc = ProductCategory(
            id=str(uuid.uuid4()), category_code="ZZTWC", category_name=WC, company_id=DEFAULT_COMPANY_ID
        )
        agents = [
            SalesAgent(id=str(uuid.uuid4()), sales_agent=code, company_id=DEFAULT_COMPANY_ID) for code in AGENT_S_CODES
        ]
        wt = SalesAgent(id=str(uuid.uuid4()), sales_agent=AGENT_WT, company_id=DEFAULT_COMPANY_ID)
        db.add_all([wc, wt, *agents])
        db.flush()
        out.update(wc=str(wc.id), wt=str(wt.id), agent_s=[str(a.id) for a in agents])
        for code in (P286, P286_NEW, P8518, P8518_250):
            product(db, company_id=DEFAULT_COMPANY_ID, code=code)
        db.commit()
        return out
    finally:
        db.close()


@pytest.fixture
def world(bot) -> dict[str, Any]:
    return _seed(bot)


def _lines(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln.startswith("Not applied:")]


# ------------------------------------------------------------------------------------------------ P1


def test_p1_agent_brand_category_ranking_sends_every_account_of_the_agent(bot, world) -> None:
    """P1 (prod turn 73b2380f) "Sales agent <agent S> Sorento top 10 hot sale water closet": crm_report_ask
    ranking, sales_agent_ids = ALL of that person's accounts, brand SORENTO, category Water Closet, top 10."""
    text, calls = bot.say(
        _rank(
            _e("ZZTS", "sales_agent"), _e("Sorento", "brand"), _e(WC, "category"),
            group_by="product", top_n=10, measure="amount", basis="delivered", **SEP,
        ),
        "Sales agent ZZTS Sorento top 10 hot sale water closet",
    )
    args = _only_report_ask(calls)
    assert sorted(args["sales_agent_ids"]) == sorted(world["agent_s"]), args
    assert args["brand_ids"] == [bot.ids["brand"]], args
    assert args["category_ids"] == [world["wc"]], args
    assert args["group_by"] == "product" and args["top_n"] == 10, args
    assert "channel" not in args, args
    assert "AGENT A" in text or "1,200" in text, text
    assert "Not applied" not in text, text


# ------------------------------------------------------------------------------------------------ P2


def test_p2_agent_brand_and_category_are_applied_or_the_category_is_said_not_applied(bot, world) -> None:
    """P2 (prod turn 37dc441a) "Sale agent wt sorento top 10 ceramic product sale on September": the agent and
    brand are applied; "ceramic" binds to no category here, so the report runs and the reply carries a
    "Not applied:" line naming it (card section 3 P2). Never a silent "all" for the agent or the category."""
    text, calls = bot.say(
        _rank(
            _e(AGENT_WT, "sales_agent"), _e("Sorento", "brand"), _e("ceramic", "category"),
            group_by="product", top_n=10, measure="amount", basis="delivered", **SEP,
        ),
        "Sale agent wt sorento top 10 ceramic product sale on September",
    )
    args = _only_report_ask(calls)
    assert args["sales_agent_ids"] == [world["wt"]], args
    assert args["brand_ids"] == [bot.ids["brand"]], args
    assert args["date_from"] == "2026-09-01" and args["date_to"] == "2026-09-30", args
    assert not args.get("category_ids"), "no category named ceramic exists, so none can be applied"
    lines = _lines(text)
    assert len(lines) == 1 and "ceramic" in lines[0].lower(), text


def test_p2_when_the_category_does_bind_it_is_applied_with_the_agent_and_brand(bot, world) -> None:
    """P2 (prod turn 37dc441a), the other branch of the card's After: a category row named Ceramic exists, so
    agent WT + brand SORENTO + category Ceramic all travel and nothing is said not applied."""
    from app.models.product import ProductCategory

    db = bot.console.session_factory()
    try:
        ceramic = ProductCategory(
            id=str(uuid.uuid4()), category_code="ZZTCER", category_name="ZZT CERAMIC", company_id=DEFAULT_COMPANY_ID
        )
        db.add(ceramic)
        db.commit()
        ceramic_id = str(ceramic.id)
    finally:
        db.close()
    text, calls = bot.say(
        _rank(
            _e(AGENT_WT, "sales_agent"), _e("Sorento", "brand"), _e("ZZT CERAMIC", "category"),
            group_by="product", top_n=10, measure="amount", basis="delivered", **SEP,
        ),
        "Sale agent wt sorento top 10 ceramic product sale on September",
    )
    args = _only_report_ask(calls)
    assert args["sales_agent_ids"] == [world["wt"]], args
    assert args["brand_ids"] == [bot.ids["brand"]], args
    assert args["category_ids"] == [ceramic_id], args
    assert "Not applied" not in text, text


# ------------------------------------------------------------------------------------------------ P3


def test_p3_which_agent_sold_the_most_of_a_product_asks_once_then_groups_by_agent_on_that_product(bot, world) -> None:
    """P3 (prod turn 2f6fafdc) "我们哪一位业务员卖得最多srtwc286-SH": the product is kept, grouped by sales
    agent, no Dealer channel; the missing measure / basis / period are asked in ONE question first."""
    body = "我们哪一位业务员卖得最多srtwc286-SH"
    first = _rank(
        _e(P286, "product"), group_by="sales_agent", top_n=None, measure=None, basis=None,
        date_filter_start=None, date_filter_end=None,
    )
    text, calls = bot.say(first, body)
    assert calls == [], calls
    assert "?" in text or "\uff1f" in text, text  # the reply is Chinese: full-width question marks
    assert text.lstrip().startswith("1.") and "2." in text, text  # one message listing what is missing
    text, calls = bot.say(
        _reply(measure="amount", basis="delivered", top_n=10, **SEP), "amount, delivered, September"
    )
    args = _only_report_ask(calls)
    assert args["group_by"] == "sales_agent", args
    assert args["product_code"] == P286, args
    assert "channel" not in args, args
    assert args["basis"] == "delivered" and args["date_from"] == "2026-09-01", args
    assert not _named(calls, "crm_sales_report") and not _named(calls, "crm_top_selling_report"), calls


# ------------------------------------------------------------------------------------------------ P8


def test_p8_outstanding_for_a_product_family_and_length_asks_the_kind_then_runs_with_no_customer(bot, world) -> None:
    """P8 (prod turn 45622f08) "SRTWC 8518-SH-250mm got outstanding?": the kind question first (Q2); the
    answer runs basis outstanding on family SRTWC8518-SH with the length 250 spec, and NO customer."""
    parse = _status(
        "outstanding", _e(P8518, "product"),
        {
            "raw": "250mm", "hint": "specification", "canonical_code": None, "spec_key": "length",
            "spec_value": 250, "spec_unit": "mm", "current_message": True, "confident": True,
        },
        basis=None, **NO_DATES,
    )
    text, calls = bot.say(parse, "SRTWC 8518-SH-250mm got outstanding?")
    assert calls == [], calls
    assert KIND_QUESTION in text, text
    text, calls = bot.say(_reply(basis="outstanding", open_question_answer={"mode": "fill", "picked": [], "items": [], "qty_for_all": None}), "undelivered orders")
    args = _only_report_ask(calls)
    assert args["basis"] == "outstanding", args
    assert args["product_code"] == P8518, args
    assert args["spec"] == ["length:250mm"], args  # the lane's form: key:value + unit, as the parser's spec_unit
    assert not args.get("customer_ids"), args
    assert "date_from" not in args and "date_to" not in args, args


# ------------------------------------------------------------------------------------------------ P10


def test_p10_top_dealer_selling_a_product_is_a_customer_ranking_on_dealer_channel_and_that_product(bot, world) -> None:
    """P10 (prod turn 67aa1cc5) "Who is the top sale dealer selling Srtwc286-SH-new": group_by customer,
    channel dealer, product SRTWC286-SH-NEW. Never a top-items ranking, never a dropped product."""
    text, calls = bot.say(
        _rank(
            _e(P286_NEW, "product"), group_by="customer", top_n=1, measure="amount", basis="delivered",
            sales_channel="dealer", **YEAR,
        ),
        "Who is the top sale dealer selling Srtwc286-SH-new",
    )
    args = _only_report_ask(calls)
    assert args["group_by"] == "customer", args
    assert args["channel"] == "dealer", args
    assert args["product_code"] == P286_NEW, args
    assert args["group_by"] != "product", args
