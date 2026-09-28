"""Top selling fix lane round 8: the owner's hand test of round 7 (28 Sep 2026 11:22 to
11:24 MYT, console :3083, head b992353c, PR #1273).

The owner's PR comment "Owner hand test of top selling round 7 (:3083, head b992353c):
the outstanding ask after a ranking takes the wrong route" is the work list, and it
supersedes round 7's "Filters from the ranking" shape:

    "the "can see the outstanignd?" should channel to the same route which is this
    format [Product / Customer / Location / Order date, then "Outstanding for which
    document?"] with the customer all, location all, product i think is the products
    listed in [the Top 10 ranking], basidcally it should carry all these as an input
    to the message and conitnue from there"

* R1 an outstanding ask typed after a ranking runs the ORDINARY outstanding path, with
  the ranking's filters carried in as inputs: Product = the ranked codes the reply
  listed, Customer = the ranking's customer (all when all), Location = all, Order date =
  the ranking's period. It prints the ordinary header and the ordinary scope menu, and
  "1" gives the sales order outstanding report over the same product set;
* R2 no "Filters from the ranking: ..." header and no "... is not a filter for ..."
  line anywhere; the sales agent filter is simply not carried into outstanding;
* R3 the ranking's own filters never answer "No matching results found" when the ranked
  products have open orders: the ask never falls into the order list (whose window is
  the actual delivery date, which an outstanding order does not have yet);
* R4 the owner's seven messages replayed in order.

Every message goes through `console_service.run_console_turn` the way the console runs
it (round 7's `Console`), with the real resolver on seeded rows. Postgres only.
"""
from __future__ import annotations

import pytest

from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot.test_outstanding_lane import REPORT_HIT
from tests.chatbot.test_top_selling_round5 import (
    ASK_METRIC,
    ORDERS,
    OUTSTANDING,
    _answer,
    _ask,
    _calls,
    _e,
    _low_signal,
    _position,
    _report,
)
from tests.chatbot.test_top_selling_round7 import (
    OUTSTANDING_READINGS,
    WT,
    _clean,
    _line,
    _outstanding_carrying,
    _ranked_by_jayden,
    console_factory,  # noqa: F401  (the fixture, re-exported for this module)
)

#: The owner's Top 10 (11:23:13), the codes the reply listed.
RANKED = [
    "SRTWC286-SH", "SRTWC286-SH-NEW", "SRTBS1001", "SRTWC5501", "SRTTP1001",
    "CBNWC2001", "SRTWC5502", "SRTTP1002", "CBNWC2002", "CWC7601-S-ECO",
]
#: The SRTWC286 family the owner's 11:24:19 ask resolved to.
FAMILY = [
    "SRTWC286-SH", "SRTWC286-SH-150", "SRTWC286-SH-200", "SRTWC286-SH-NEW", "SRTWC286-SH-NEW-150",
    "SRTWC286-SH-NEW-200", "SRTWC286-SH-NEW-P", "SRTWC286-SH-P", "SRTWC286-SH-PP", "SRTWC286-SH-UF",
]
YEAR = "01/01/2026 to 31/12/2026"
SCOPE_MENU = (
    "Outstanding for which document?\n"
    "1. Sales orders (not yet transferred to DO)\n"
    "2. Delivery orders (not yet delivered)\n"
    "3. Both"
)
#: Never in any reply after a ranking (round 7's header and note, and the miss).
WILLIAM_WHO = (
    f"Do you mean customer SAMPLE - WILLIAM or sales agent {WT}? "
    "Reply 1 for the customer, 2 for the sales agent."
)
GONE = ("Filters from the ranking", "is not a filter for", "No matching results found")


def _no_hop_lines(text: str, body: str) -> None:
    _clean(text, body)
    for bad in GONE:
        assert bad not in text, (body, bad, text)


def _scope_question(text: str, *, product: str, customer: str = "all", order_date: str = YEAR) -> None:
    """The ordinary outstanding question, byte for byte: the four header lines, then the
    menu, and nothing above them."""
    assert text == (
        f"Product: {product}\nCustomer: {customer}\nLocation: all\nOrder date: {order_date}\n{SCOPE_MENU}"
    ), text


def _seed_family(session_factory) -> None:
    from tests._mc_lookup_seed import product

    db = session_factory()
    try:
        for code in FAMILY:
            product(db, company_id=DEFAULT_COMPANY_ID, code=code)
        db.commit()
    finally:
        db.close()


def _seed_william_ledger(session_factory) -> None:
    from tests._mc_lookup_seed import customer

    db = session_factory()
    try:
        customer(db, company_id=DEFAULT_COMPANY_ID, name="SAMPLE - WILLIAM")
        db.commit()
    finally:
        db.close()


def _top_10_by_wt(c) -> str:
    """"top 10 hot selling item by wt", "amount": the owner's Top 10, sales agent WT."""
    c.codes = list(RANKED)
    c.say(_ask(top_n=10, entities=[_e("wt", "sales_agent")]), "top 10 hot selling item by wt")
    text, captured = c.say(_answer(rank_by="amount"), "amount")
    (args,) = _calls(captured)
    assert sorted(args["sales_agent_ids"]) == c.seeded.agents("WT"), args
    _line(text, "Sales agent", WT)
    return text


# --------------------------------------------------------------------------- #
# R1 + R2: the ordinary outstanding path, the ranking's filters as its inputs
# --------------------------------------------------------------------------- #


class TestR1OrdinaryRoute:
    @pytest.mark.parametrize("reading", list(OUTSTANDING_READINGS))
    def test_can_see_the_outstanding_asks_the_ordinary_question(self, console_factory, reading) -> None:
        """"can see the outstanignd/" after the Top 10: the ordinary header with the ten
        ranked codes, Customer all, Location all, the ranking's year, then the menu. No
        fetch yet (the direct path asks first), never the order list."""
        c = console_factory()
        _top_10_by_wt(c)
        text, captured = c.say(OUTSTANDING_READINGS[reading]("wt"), "can see the outstanignd/")
        _no_hop_lines(text, "can see the outstanignd/")
        _scope_question(text, product=", ".join(RANKED))
        assert _calls(captured, ORDERS) == [], captured
        assert _calls(captured, OUTSTANDING) == [], captured
        assert c.open_question.get("kind") == "outstanding_scope", c.open_question

    def test_one_gives_the_sales_order_report_for_the_ranked_products(self, console_factory) -> None:
        """"1" continues exactly as the direct path does: the sales order outstanding
        report, the same ten codes, the ranking's year, every customer, and no sales agent
        filter (silently)."""
        c = console_factory()
        _top_10_by_wt(c)
        c.say(_report("outstanding", continuation=True), "can see the outstanding?")
        text, captured = c.say(_position(1), "1")
        _no_hop_lines(text, "1")
        (args,) = _calls(captured, OUTSTANDING)
        assert args["scope"] == "so", args
        assert args["product_codes"] == RANKED, args
        assert (args["order_date_from"], args["order_date_to"]) == ("2026-01-01", "2026-12-31"), args
        assert "customer_ids" not in args and "sales_agent_ids" not in args, args
        assert _calls(captured, ORDERS) == [], captured
        assert "*Sales order outstanding*" in text, text

    def test_the_ranking_customer_rides_along(self, console_factory) -> None:
        """A ranking narrowed to HANLIM hands its customer in as the Customer line."""
        c = console_factory()
        c.codes = list(RANKED)
        _ranked_by_jayden(c)
        text, captured = c.say(_outstanding_carrying("Jayden"), "any outstanding?")
        _no_hop_lines(text, "any outstanding?")
        assert text.startswith(f"Product: {', '.join(RANKED)}\nCustomer: HANLIM TRADING"), text
        assert text.endswith(SCOPE_MENU), text
        text, captured = c.say(_position(1), "1")
        _no_hop_lines(text, "1")
        (args,) = _calls(captured, OUTSTANDING)
        assert sorted(args["customer_ids"]) == c.seeded.customers("HANLIM TRADING", "HANLIM TRADING (SRT)"), args
        assert args["product_codes"] == RANKED, args

    def test_a_period_ranking_hands_its_period(self, console_factory) -> None:
        c = console_factory()
        c.codes = list(RANKED)
        c.say(_ask(top_n=10, rank_by="quantity", date_filter_start="2026-01-01", date_filter_end="2026-03-31"),
              "top 10 hot selling item in q1 2026")
        text, captured = c.say(_report("outstanding", continuation=True), "can see its outstanding?")
        _no_hop_lines(text, "can see its outstanding?")
        _scope_question(text, product=", ".join(RANKED), order_date="01/01/2026 to 31/03/2026")

    def test_a_product_named_in_the_ask_wins_over_the_ranked_ones(self, console_factory, session_factory) -> None:
        """"any outstandding for srtwc286" after a ranking asks about SRTWC286, not the
        ranked ten."""
        _seed_family(session_factory)
        c = console_factory()
        _top_10_by_wt(c)
        text, captured = c.say(
            _report("outstanding", entities=[_e("srtwc286", "product")]), "any outstandding for srtwc286"
        )
        _no_hop_lines(text, "any outstandding for srtwc286")
        assert text.startswith("Product: SRTWC286-SH"), text
        assert "SRTBS1001" not in text and "CWC7601-S-ECO" not in text, text
        assert text.endswith(SCOPE_MENU), text


class TestR2NoRankingHeader:
    @pytest.mark.parametrize(
        "body, qf",
        [
            ("can show me the DO", _report("do_outstanding", continuation=True, document=["DO"])),
            ("show me the orders", _report(None, domain_in_message=True)),
        ],
    )
    def test_no_header_on_any_report_after_a_ranking(self, console_factory, body, qf) -> None:
        """Any report after a ranking prints no "Filters from the ranking" header and no
        dropped filter line."""
        c = console_factory()
        _top_10_by_wt(c)
        text, _ = c.say(qf, body)
        for bad in GONE[:2]:
            assert bad not in text, (body, bad, text)


# --------------------------------------------------------------------------- #
# R4: the owner's seven messages, in order
# --------------------------------------------------------------------------- #


class TestOwnerTranscript:
    def test_replay(self, console_factory, session_factory) -> None:
        _seed_family(session_factory)
        _seed_william_ledger(session_factory)
        c = console_factory(wt_alias="William")
        c.codes = list(RANKED)

        # 11:22:55: "william" is a customer ledger and WT's alias, so the bot asks which.
        text, captured = c.say(_ask(top_n=10, entities=[_e("william", "customer")]), "top 10 hot selling item by william")
        assert text == WILLIAM_WHO, text
        assert captured == [], captured
        # 11:23:06
        text, captured = c.say(_low_signal(), "sales agent")
        assert text == ASK_METRIC, text
        # 11:23:13
        text, captured = c.say(_answer(rank_by="amount"), "amount")
        (args,) = _calls(captured)
        assert sorted(args["sales_agent_ids"]) == c.seeded.agents("WT"), args
        assert text.startswith("*Top 10 selling items*"), text

        # 11:23:26
        text, captured = c.say(_report("outstanding", continuation=True), "can see the outstanignd/")
        _no_hop_lines(text, "can see the outstanignd/")
        _scope_question(text, product=", ".join(RANKED))
        assert _calls(captured, ORDERS) == [], captured

        # 11:23:53: "for all customer" widens the customer, which is all already.
        text, captured = c.say(
            _report("outstanding", correction=True, broaden_axis="customer", broaden_to="all"),
            "any outstandding for all customer",
        )
        _no_hop_lines(text, "any outstandding for all customer")
        _scope_question(text, product=", ".join(RANKED))
        assert _calls(captured, ORDERS) == [], captured

        # 11:24:19
        text, captured = c.say(
            _report("outstanding", entities=[_e("srtwc286", "product")]), "any outstandding for srtwc286"
        )
        _no_hop_lines(text, "any outstandding for srtwc286")
        assert text.startswith("Product: SRTWC286-SH"), text
        assert "SRTBS1001" not in text, text
        assert text.endswith(f"Customer: all\nLocation: all\nOrder date: {YEAR}\n{SCOPE_MENU}"), text

        # 11:24:27
        c.report = REPORT_HIT
        text, captured = c.say(_position(1), "1")
        _no_hop_lines(text, "1")
        (args,) = _calls(captured, OUTSTANDING)
        assert args["scope"] == "so", args
        codes = args.get("product_codes") or [args.get("product_code")]
        assert all(code.startswith("SRTWC286") for code in codes), args
        assert "SRTBS1001" not in codes, args
        assert "*Sales order outstanding*" in text, text
