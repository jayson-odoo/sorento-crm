"""DO-ASK-SIMPLIFY rules 3-4 through the REAL engine: the period question, then its answer.

`documentation/plans/chatbot/PLAN-do-ask-simplify-2oct.md`. A dealer (a contact linked to a
customer, no office access type) asks for deliveries with no date: nothing is fetched and the
bot asks which period. The dealer answers with a period only ("this month"): the SAME ask runs,
for the carried customer, over that window. No pending question is armed for this; the answer
is an ordinary dated message the engine carries onto the open ask.

Harness: `test_dealer_eta_stock_routing.py`'s Console (real engine, real routes through
TestClient, real MCP presenter; only the parser verdict is stubbed).
"""
from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from app.services.ai_assistant_service import MCPRuntimeClient
from app.services.chatbot import do_ask
from tests.chatbot._turn_helpers import entity, verdict
from tests.chatbot.test_dealer_eta_stock_routing import Console, _seed
from tests.chatbot.test_engine import stub_access  # noqa: F401 - fixture

ORDERS_TOOL = "crm_order_management_orders_list"


@pytest.fixture
def dealer(session_factory, monkeypatch, stub_access):
    from app.main import app

    monkeypatch.setattr(do_ask, "today_myt", lambda: date(2026, 10, 2))
    _seed(session_factory, dealer=False, salesperson=True, shipments=False)
    console = Console(session_factory, monkeypatch, stub_access)
    calls: list[tuple[str, dict[str, Any]]] = []
    inner = MCPRuntimeClient.call_tool

    def recording(self, name, args):
        calls.append((name, dict(args)))
        return inner(self, name, args)

    monkeypatch.setattr(MCPRuntimeClient, "call_tool", recording)
    console.calls = calls
    try:
        yield console
    finally:
        app.dependency_overrides.clear()


def _ask(**extra: Any) -> dict[str, Any]:
    return verdict(
        domain_hint="order",
        intent_hint="check_order",
        entities=[entity("ZZT Dealer", hint="customer")],
        **extra,
    )


def _period(start: str, end: str) -> dict[str, Any]:
    return verdict(
        domain_hint="order",
        intent_hint="check_order",
        domain_in_message=False,
        entities=[],
        date_filter_start=start,
        date_filter_end=end,
    )


def test_no_range_asks_which_period_and_fetches_nothing(dealer):
    reply = dealer.say("delivery to zzt dealer", _ask())
    assert dealer.calls == [], dealer.calls
    assert "Which period" in reply and "This month (Oct 2026)" in reply, reply


def test_the_answer_runs_the_same_ask_over_that_window(dealer):
    dealer.say("delivery to zzt dealer", _ask())
    dealer.say("this month", _period("2026-10-01", "2026-10-31"))
    orders = [args for name, args in dealer.calls if name == ORDERS_TOOL]
    assert len(orders) == 1, dealer.calls
    args = orders[0]
    assert args.get("actual_delivery_date_from") == "2026-10-01", args
    assert args.get("actual_delivery_date_to") == "2026-10-31", args
    assert args.get("customer_ids"), f"the carried customer must scope the fetch: {args}"


def test_a_range_over_31_days_is_refused_through_the_engine(dealer):
    reply = dealer.say(
        "delivery to zzt dealer january to june",
        _ask(date_filter_start="2026-01-01", date_filter_end="2026-06-30"),
    )
    assert dealer.calls == [], dealer.calls
    assert "6 months" in reply and "Jun 2026" in reply, reply
