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
from tests.chatbot.test_report_unify_routing import (  # noqa: F401  (console, bot are fixtures)
    KIND_QUESTION,
    NO_DATES,
    Routing,
    _only_report_ask,
    _status,
    bot,
    console,
)
from tests.chatbot.test_engine import _parser_output

PRODUCT = "SRT5733-ZZ"
DO_OFFER = "Reply 1 for the delivery order list."
SO_OFFER = "Reply 1 for the sales order list."
DO_SUMMARY = {
    "documents": 3, "qty": 40, "amount": 1234.0, "date_first": "2026-10-02", "date_last": "2026-10-20",
    "by_location": [{"name": "ZZT-WH-A", "qty": 30, "amount": 900.0}, {"name": "ZZT-WH-B", "qty": 10, "amount": 334.0}],
    "second": "customer",
    "by_second": [
        {"name": "ZZT CUSTOMER A", "qty": 25, "amount": 800.0}, {"name": "ZZT CUSTOMER B", "qty": 15, "amount": 434.0}
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
    assert calls == [] and KIND_QUESTION in text, (text, calls)
    bot.extra_body = {"summary": DO_SUMMARY, "total": {"qty": 40, "amount": 1234.0}}
    text, calls = bot.say(_kind_answer("pending_delivery"), "pending delivery")
    args = _only_report_ask(calls)
    assert args["basis"] == "pending_delivery" and args["product_code"] == PRODUCT, args
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
    assert args["product_code"] == PRODUCT, args
    assert "date_from" not in args and "date_to" not in args, args
    assert "ZZT-DO-2001" in text and "ZZT-DO-2002" in text, text
    assert DO_OFFER not in text, text


def test_an_undelivered_orders_summary_keeps_the_sales_order_offer_and_its_list(bot, world) -> None:
    bot.say(_status("outstanding", _e(PRODUCT, "product"), basis=None, state_changes=list(KEEP), **NO_DATES), "x")
    bot.extra_body = {"summary": {
        "documents": 2, "ordered_qty": 15, "qty": 11, "amount": 1100.0, "date_first": "2026-08-05",
        "date_last": "2026-09-20", "by_location": [{"name": "ZZT-WH-A", "qty": 11, "amount": 1100.0, "ordered_qty": 15}],
        "second": "customer", "by_second": [{"name": "ZZT CUSTOMER A", "qty": 11, "amount": 1100.0, "ordered_qty": 15}],
    }}
    text, _calls = bot.say(_kind_answer("outstanding"), "undelivered orders")
    assert "Sales orders: 2" in text and "Transferred to DO: 4" in text, text
    assert text.rstrip().endswith(SO_OFFER), text
    bot.extra_body = {"rows": [{"rank": 1, "name": "ZZT-SO-1001", "qty": 11, "amount": 1100.0, "keys": []}]}
    text, calls = bot.say(_pick_one(), "1")
    args = _only_report_ask(calls)
    assert args["group_by"] == "sales_order" and args["basis"] == "outstanding", args
