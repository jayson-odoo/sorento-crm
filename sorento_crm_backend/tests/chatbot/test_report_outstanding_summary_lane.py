"""REPORT-OUTSTANDING-SUMMARY (29 Oct 2026): the outstanding summary through the chatbot lane, on the one report ask.

Prod turn #b6e9 (26 Oct 09:28) "Srt5733 stock and outstanding": before #1922 the outstanding half printed the DO
summary (Delivery orders, DO qty, Delivered, Outstanding, DO date range, By location, By customer) and "Reply 1 for
the delivery order list.". On the one engine the kind is asked first (owner 27 Oct Q2, never defaulted), then the
route's `summary` prints in that shape (`presenters._ask_summary`), and "1" lists the delivery orders: the SAME held
ask grouped by `delivery_order`. Fake names only; the parser and the MCP transport are the only doubles.
"""
from __future__ import annotations

from typing import Any

import pytest

from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot.test_report_ask_lane import _e, _reply
from tests.chatbot.test_report_smart_step7 import KEEP
from tests.chatbot.test_report_ask_lane import console_no_grant  # noqa: F401  (a fixture)
from tests.chatbot.test_report_unify_routing import (  # noqa: F401  (console, bot are fixtures)
    KIND_QUESTION,
    NO_DATES,
    Routing,
    _only_report_ask,
    _status,
    bot,
    console,
)
from tests.chatbot.test_engine import CONTACT_ID, _parser_output

PRODUCT = "SRT5733-ZZ"
DO_OFFER = "Reply 1 for the delivery order list."
SO_OFFER = "Reply 1 for the sales order list."
DO_SUMMARY = {
    "documents": 3, "qty": 40, "amount": 1234.0, "date_first": "2026-10-02", "date_last": "2026-10-20",
    "groups": [
        {"axis": "location", "label": "Location", "rows": [
            {"name": "ZZT-WH-A", "qty": 30, "amount": 900.0}, {"name": "ZZT-WH-B", "qty": 10, "amount": 334.0}]},
        {"axis": "customer", "label": "Customer", "rows": [
            {"name": "ZZT CUSTOMER A", "qty": 25, "amount": 800.0}, {"name": "ZZT CUSTOMER B", "qty": 15, "amount": 434.0}]},
    ],
}
DO_ROWS = [
    {"rank": 1, "name": "ZZT-DO-2001", "qty": 30, "amount": 900.0, "keys": []},
    {"rank": 2, "name": "ZZT-DO-2002", "qty": 10, "amount": 334.0, "keys": []},
]


@pytest.fixture
def world(bot) -> None:
    from tests._mc_lookup_seed import product

    db = bot.console.session_factory()
    try:
        product(db, company_id=DEFAULT_COMPANY_ID, code=PRODUCT)
        db.commit()
    finally:
        db.close()


def _kind_answer(kind: str) -> dict[str, Any]:
    return _reply(basis=kind, open_question_answer={"mode": "fill", "picked": [], "items": [], "qty_for_all": None})


def _pick_one() -> dict[str, Any]:
    return _parser_output(
        message_type="casual", intent_hint=None, domain_hint=None, entities=[], order_status=None,
        reference_positions=[1], open_question_answer={"mode": "pick", "picked": [1], "items": [], "qty_for_all": None},
        state_changes=[{"op": "answer", "axis": None, "position": 1}],
    )


def _outstanding_for_the_product(bot: Routing) -> str:
    """Turn 1 asks the kind; turn 2 ("pending delivery") runs the report ask with the route's summary."""
    text, calls = bot.say(
        _status("outstanding", _e(PRODUCT, "product"), basis=None, state_changes=list(KEEP), **NO_DATES),
        "Srt5733 outstanding",
    )
    assert calls == [] and text.strip().startswith(KIND_QUESTION), (text, calls)
    assert "unpaid" not in text.lower(), text  # owner 29 Oct: unpaid is not an outstanding kind to offer
    bot.extra_body = {"summary": DO_SUMMARY, "total": {"qty": 40, "amount": 1234.0}}
    text, calls = bot.say(_kind_answer("pending_delivery"), "pending delivery")
    args = _only_report_ask(calls)
    assert args["basis"] == "pending_delivery" and len(args["product_ids"]) == 1 and "product_code" not in args, args
    assert not args.get("group_by"), args
    return text


def test_the_prod_turn_prints_the_delivery_order_summary_then_the_list_offer(bot, world) -> None:
    text = _outstanding_for_the_product(bot)
    lines = text.split("\n")
    for wanted in (
        "Delivery orders: 3", "DO qty: 40", "Delivered: 0", "Outstanding: 40 pcs, RM 1,234.00",
        "DO date range: 02/10/2026 to 20/10/2026", "*_By location_*", "ZZT-WH-A: 30 (O/S: 30)",
        "*_By customer_*", "ZZT CUSTOMER A: 25 (O/S: 25)",
    ):
        assert wanted in lines, (wanted, text)
    assert text.rstrip().endswith(DO_OFFER), text
    assert lines.index("*_By location_*") < lines.index("*_By customer_*"), text


def test_reply_one_lists_the_delivery_orders_of_the_same_ask(bot, world) -> None:
    _outstanding_for_the_product(bot)
    bot.extra_body = {"rows": DO_ROWS, "total_count": 2, "group_label": "Delivery order"}
    text, calls = bot.say(_pick_one(), "1")
    args = _only_report_ask(calls)
    assert args["group_by"] == "delivery_order" and args["basis"] == "pending_delivery", args
    assert len(args["product_ids"]) == 1 and "product_code" not in args, args
    assert "date_from" not in args and "date_to" not in args, args
    assert "ZZT-DO-2001" in text and "ZZT-DO-2002" in text, text
    assert DO_OFFER not in text, text


def test_an_undelivered_orders_summary_keeps_the_sales_order_offer_and_its_list(bot, world) -> None:
    bot.say(_status("outstanding", _e(PRODUCT, "product"), basis=None, state_changes=list(KEEP), **NO_DATES), "x")
    bot.extra_body = {"summary": {
        "documents": 2, "ordered_qty": 15, "qty": 11, "amount": 1100.0, "date_first": "2026-08-05",
        "date_last": "2026-09-20", "groups": [
            {"axis": "location", "label": "Location", "rows": [{"name": "ZZT-WH-A", "qty": 11, "amount": 1100.0, "ordered_qty": 15}]},
            {"axis": "customer", "label": "Customer", "rows": [{"name": "ZZT CUSTOMER A", "qty": 11, "amount": 1100.0, "ordered_qty": 15}]},
        ],
    }}
    text, _calls = bot.say(_kind_answer("outstanding"), "undelivered orders")
    assert "Sales orders: 2" in text and "Transferred to DO: 4" in text, text
    assert text.rstrip().endswith(SO_OFFER), text
    bot.extra_body = {"rows": [{"rank": 1, "name": "ZZT-SO-1001", "qty": 11, "amount": 1100.0, "keys": []}]}
    text, calls = bot.say(_pick_one(), "1")
    args = _only_report_ask(calls)
    assert args["group_by"] == "sales_order" and args["basis"] == "outstanding", args


# ================================================================ owner 29 Oct: the kinds the contact may see


@pytest.fixture
def do_only(console_no_grant) -> Routing:
    """The #b6e9 contact: office staff with no Outstanding reveal. Before #1922 it saw the DO half only."""
    from tests.chatbot._turn_helpers import make_office_access_type
    from app.services.chatbot.lanes.business.report_ask import KIND_QUESTION as _KQ  # noqa: F401

    make_office_access_type(console_no_grant.session_factory, CONTACT_ID)
    return Routing(console_no_grant)


@pytest.fixture
def do_only_world(do_only) -> None:
    from tests._mc_lookup_seed import product

    db = do_only.console.session_factory()
    try:
        product(db, company_id=DEFAULT_COMPANY_ID, code=PRODUCT)
        db.commit()
    finally:
        db.close()


def test_b6e9_a_do_only_contact_gets_the_delivery_order_summary_with_no_question(do_only, do_only_world) -> None:
    """Prod turn #b6e9 pin: "Srt5733 ... outstanding" from a contact that may see pending delivery only runs it straight
    away (no kind question) and prints the DO summary: by location, by customer, the delivery order list offer."""
    do_only.extra_body = {
        "summary": DO_SUMMARY, "total": {"qty": 40, "amount": 1234.0},
        "filters": [{"key": "product", "label": "Product", "values": [PRODUCT]}],  # the route's own echo
    }
    text, calls = do_only.say(
        _status("outstanding", _e(PRODUCT, "product"), basis=None, state_changes=list(KEEP), **NO_DATES),
        "Srt5733 outstanding",
    )
    args = _only_report_ask(calls)
    assert args["basis"] == "pending_delivery" and len(args["product_ids"]) == 1 and "product_code" not in args, args
    assert KIND_QUESTION not in text, text
    lines = text.split("\n")
    assert lines[:6] == [  # item 5: the pre-#1922 header and block title
        f"Product: {PRODUCT}", "Customer: all", "Location: all", "Order date: all", "", "*Delivery order outstanding*",
    ], text
    for wanted in ("Delivery orders: 3", "*_By location_*", "ZZT-WH-A: 30 (O/S: 30)", "*_By customer_*"):
        assert wanted in lines, (wanted, text)
    assert text.rstrip().endswith(DO_OFFER), text


def test_a_do_only_contact_naming_undelivered_orders_gets_pending_delivery_with_the_so_line(do_only, do_only_world) -> None:
    """Eval rpt-030/-038, as before #1922 (D13): a contact that may see pending delivery only, asking undelivered
    orders, is not refused: the one SO sentence, then the pending delivery answer (the route still refuses SO data)."""
    do_only.extra_body = {"summary": DO_SUMMARY, "total": {"qty": 40, "amount": 1234.0}}
    text, calls = do_only.say(
        _status("outstanding", _e(PRODUCT, "product"), basis="outstanding", state_changes=list(KEEP), **NO_DATES),
        "Srt5733 undelivered",
    )
    args = _only_report_ask(calls)
    assert args["basis"] == "pending_delivery", args
    assert text.startswith("Sales order figures are not enabled for your account."), text
    assert "Delivery orders: 3" in text and "Outstanding is not enabled" not in text, text


def test_an_unknown_contact_without_the_reveal_is_refused_outstanding(console_no_grant) -> None:
    """Unlinked and not office staff: no kind it may see, so the refusal, never a question."""
    bot_ = Routing(console_no_grant)
    text, calls = bot_.say(
        _status("outstanding", _e(PRODUCT, "product"), basis=None, state_changes=list(KEEP), **NO_DATES),
        "Srt5733 outstanding",
    )
    assert calls == [] and KIND_QUESTION not in text, (text, calls)
    assert "Outstanding is not enabled for your account." in text, text  # review S2: the refusal, never silence


def test_a_named_axis_keeps_the_summary_and_the_list_offer(do_only, do_only_world) -> None:
    """Owner 29 Oct Q2: "by brand" replaces the default breakdowns; the route returns the summary with it. (An agent axis
    is the route's to refuse this unrevealed contact, security S1.)"""
    do_only.extra_body = {"summary": {**DO_SUMMARY, "groups": [
        {"axis": "brand", "label": "Brand", "rows": [{"name": "ZZT BRAND", "qty": 40, "amount": 1234.0}]}]}}
    text, calls = do_only.say(
        _status("outstanding", _e(PRODUCT, "product"), basis=None, group_by="brand", state_changes=list(KEEP),
                **NO_DATES),
        "Srt5733 outstanding by brand",
    )
    args = _only_report_ask(calls)
    assert args["basis"] == "pending_delivery" and args["group_by"] == "brand", args
    assert "*_By brand_*" in text and text.rstrip().endswith(DO_OFFER), text
    do_only.extra_body = {"rows": DO_ROWS, "total_count": 2, "group_label": "Delivery order"}
    text, calls = do_only.say(_pick_one(), "1")
    args = _only_report_ask(calls)
    assert args["group_by"] == "delivery_order", args


# ================================================================ item 3 (owner 29 Oct): no subject = the document list


def test_an_outstanding_ask_with_no_subject_is_the_delivery_order_list(bot) -> None:
    """Pre-#1922 a subject-less outstanding ask was the outstanding document list, not a company figure."""
    text, calls = bot.say(_status("outstanding", basis=None, state_changes=list(KEEP), **NO_DATES), "any outstanding?")
    assert calls == [] and KIND_QUESTION in text, (text, calls)
    bot.extra_body = {"rows": DO_ROWS, "total_count": 2, "group_label": "Delivery order"}
    text, calls = bot.say(_kind_answer("pending_delivery"), "pending delivery")
    args = _only_report_ask(calls)
    assert args["basis"] == "pending_delivery" and args["group_by"] == "delivery_order", args
    assert "date_from" not in args, args


def test_an_outstanding_ask_naming_its_kind_and_no_subject_is_the_sales_order_list(bot) -> None:
    """No product, customer or brand: the list, with no question."""
    text, calls = bot.say(_status("outstanding", basis="outstanding", state_changes=list(KEEP), **NO_DATES), "undelivered")
    args = _only_report_ask(calls)
    assert args["group_by"] == "sales_order", args


def test_an_unlinked_non_staff_contact_gets_no_outstanding_list(console) -> None:
    """V1-DOC-SCOPE, as before #1922: a contact that owns no customer and is not staff is told so; nothing runs."""
    bot_ = Routing(console)  # holds both reveals, but no office access type and no linked customer
    text, calls = bot_.say(_status("outstanding", basis="pending_delivery", state_changes=list(KEEP), **NO_DATES), "outstanding")
    assert calls == [], (text, calls)
    from app.services import contact_customer_scope as scope_mod

    assert text.strip() == scope_mod.refusal_line(scope_mod.ContactCustomerScope(linked=(), staff=False)), text


# ================================================================ eval send-back (rpt-010, rpt-009): the context product


def _stock_ask() -> dict[str, Any]:
    return _parser_output(
        domain_hint="inventory", intent_hint="check_stock", order_status=None, entities=[_e(PRODUCT, "product")],
    )


def _carried() -> dict[str, Any]:
    return dict(_e(PRODUCT, "product"), current_message=False)


def test_rpt010_outstanding_after_a_stock_ask_keeps_the_product_and_runs_its_summary(do_only, do_only_world) -> None:
    """Eval rpt-010 shape: "<code> stock", then "outstanding". As before #1922 the outstanding report runs on the product
    in context: the product's summary, never the whole company's delivery order list."""
    do_only.say(_stock_ask(), f"{PRODUCT} stock")
    do_only.extra_body = {"summary": DO_SUMMARY, "total": {"qty": 40, "amount": 1234.0}}
    text, calls = do_only.say(
        _status("outstanding", _carried(), basis=None, state_changes=list(KEEP), entity_op="reuse", **NO_DATES),
        "outstanding",
    )
    args = _only_report_ask(calls)
    assert args["basis"] == "pending_delivery" and len(args.get("product_ids") or []) == 1, args
    assert args.get("group_by") is None, args  # the summary, not the document list
    assert "Delivery orders: 3" in text, text


def test_rpt009_dealer_outstanding_only_after_a_product_ask_keeps_the_product(do_only, do_only_world) -> None:
    """Eval rpt-009 shape: a product ask, then "dealer outstanding only": the channel narrows the product's figure."""
    do_only.say(_stock_ask(), f"{PRODUCT} stock")
    do_only.extra_body = {"summary": DO_SUMMARY, "total": {"qty": 40, "amount": 1234.0}}
    _text, calls = do_only.say(
        _status("outstanding", _carried(), basis=None, sales_channel="dealer", state_changes=list(KEEP),
                entity_op="reuse", **NO_DATES),
        "dealer outstanding only",
    )
    args = _only_report_ask(calls)
    assert len(args.get("product_ids") or []) == 1 and args.get("group_by") is None, args


# ================================================================ eval send-back: #b6e9 on the prod prompt (v70)

ASKS = [{"domain": "inventory", "intent": "check_stock"}, {"domain": "order", "intent": "check_order"}]


def _v70_b6e9(asks: Any = ASKS) -> dict[str, Any]:
    """v70's reading of "SRT5733 stock and outstanding": a stock ask and a sales report whose basis word is outstanding
    (`sales_basis`), the shape the pre-#1922 lane turned into the outstanding report (`sales_basis_ask.as_report_ask`)."""
    return _status(
        "sales_report", _e(PRODUCT, "product"), basis=None, sales_basis="outstanding", asks=asks,
        state_changes=list(KEEP), **NO_DATES,
    )


def test_b6e9_v70_a_do_only_contact_gets_stock_then_the_do_summary_with_no_question(do_only, do_only_world) -> None:
    do_only.extra_body = {"summary": DO_SUMMARY, "total": {"qty": 40, "amount": 1234.0}}
    text, calls = do_only.say(_v70_b6e9(), "SRT5733 stock and outstanding")
    assert calls[0][0] == "crm_inventory_stock_balance_list", calls  # the stock half still runs, first
    (args,) = [a for n, a in calls if n == "crm_report_ask"]
    assert args["basis"] == "pending_delivery" and len(args["product_ids"]) == 1, args
    assert "date_from" not in args and "Which period" not in text and KIND_QUESTION not in text, text
    assert "Delivery orders: 3" in text and text.rstrip().endswith(DO_OFFER), text


def test_b6e9_v70_a_contact_seeing_both_kinds_is_asked_the_kind_never_the_period(bot, world) -> None:
    text, calls = bot.say(_v70_b6e9(), "SRT5733 stock and outstanding")
    assert not [c for c in calls if c[0] == "crm_report_ask"], calls
    assert "Which period" not in text and text.rstrip().endswith(KIND_QUESTION), text


@pytest.fixture
def dealer_no_reveal(console_no_grant) -> Routing:
    """A linked contact (dealer) without the Outstanding reveal: pending delivery only, on its own customer."""
    from tests.chatbot.test_report_ask_lane import _link_dealer

    console_no_grant.own_customer = _link_dealer(console_no_grant)
    return Routing(console_no_grant)


def test_rpt030_a_dealer_asking_undelivered_orders_gets_its_pending_delivery_with_the_so_line(dealer_no_reveal) -> None:
    from tests._mc_lookup_seed import product

    db = dealer_no_reveal.console.session_factory()
    try:
        product(db, company_id=DEFAULT_COMPANY_ID, code=PRODUCT)
        db.commit()
    finally:
        db.close()
    dealer_no_reveal.extra_body = {"summary": DO_SUMMARY, "total": {"qty": 40, "amount": 1234.0}}
    text, calls = dealer_no_reveal.say(
        _status("so_outstanding", _e(PRODUCT, "product"), basis=None, state_changes=list(KEEP), **NO_DATES),
        "Srt5733 sales order outstanding",
    )
    args = _only_report_ask(calls)
    assert args["basis"] == "pending_delivery", args
    assert text.startswith("Sales order figures are not enabled for your account."), text


def test_b6e9_v70_with_no_asks_list_is_still_the_do_summary(do_only, do_only_world) -> None:
    """Crew: v189 emits `asks: null` on these turns; the outstanding reading must not depend on a filled list."""
    do_only.extra_body = {"summary": DO_SUMMARY, "total": {"qty": 40, "amount": 1234.0}}
    text, calls = do_only.say(_v70_b6e9(asks=None), "SRT5733 stock and outstanding")
    (args,) = [a for n, a in calls if n == "crm_report_ask"]
    assert args["basis"] == "pending_delivery" and "Which period" not in text, (args, text)


def _so_document_ask(*entities: dict[str, Any]) -> dict[str, Any]:
    """v189's reading of rpt-030 / rpt-038 ("<customer> outstanding sales order"): `so_outstanding` with the SO
    document word, `asks` null (crew's gate verdicts, 29 Oct)."""
    return _status(
        "so_outstanding", *entities, basis=None, document=["SO"], asks=None, entity_op="replace_combine",
        scope_intent="specific", **NO_DATES,
    )


def test_rpt038_a_dealer_naming_its_customer_and_outstanding_sales_order_gets_pending_delivery(dealer_no_reveal) -> None:
    dealer_no_reveal.extra_body = {"summary": DO_SUMMARY, "total": {"qty": 40, "amount": 1234.0}}
    text, calls = dealer_no_reveal.say(
        _so_document_ask(_e("ZZT OWN DEALER SDN BHD", "customer")), "ZZT OWN DEALER SDN BHD OUTSTANDING SALES ORDER",
    )
    reports = [a for n, a in calls if n == "crm_report_ask"]
    assert reports and reports[0]["basis"] == "pending_delivery", (calls, text)
    assert text.startswith("Sales order figures are not enabled for your account."), text
    assert "Outstanding is not enabled" not in text, text


def test_rpt030_shape_a_dealer_naming_its_customer_and_a_brand_gets_pending_delivery(dealer_no_reveal) -> None:
    from tests.test_report_unify_outstanding_bases import _brand  # noqa: F401  (brand row helper)
    from tests._pg_fixture import unique_code  # noqa: F401

    dealer_no_reveal.extra_body = {"summary": DO_SUMMARY, "total": {"qty": 40, "amount": 1234.0}}
    text, calls = dealer_no_reveal.say(
        _so_document_ask(_e("ZZT OWN DEALER SDN BHD", "customer"), _e("mocha", "brand")),
        "ZZT OWN DEALER SDN BHD\nany outstanding mocha item in sales order",
    )
    assert "Outstanding is not enabled" not in text, (calls, text)


def test_the_so_line_rides_a_question_asked_before_the_redirected_answer(do_only, do_only_world) -> None:
    """Review (eval round): a redirected undelivered-orders ask that stops before running (here its only filter, a
    brand word, binds to nothing) still says the SO sentence above that line."""
    text, calls = do_only.say(
        _so_document_ask(_e("ZZTNOBRAND", "brand")), "any outstanding ZZTNOBRAND item in sales order",
    )
    assert calls == [] and "I don't know 'ZZTNOBRAND' as a brand." in text, (calls, text)
    assert text.startswith("Sales order figures are not enabled for your account."), text
