"""A stock read that failed must never tell a customer there is no stock.

Owner, 1 Nov 2026: "when the stock lookup fails, the bot shouldnt say no stock. Its a very
dangerous business consequences."

Production, 29 Oct (masked): a dealer asked for stock of one code and read, in one reply,
"I could not fetch stock just now, please try again." and "No stock and no incoming for X."
Nothing had measured an absence: the stock read itself had failed.

Runs the real engine end to end; only the parser and the MCP transport are faked. Fake
fixture codes only.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from app.services.ai_assistant_service import MCPRuntimeClient, MCPToolCallError
from tests.chatbot._avail_mode_console import AvailConsole, _seed
from tests.chatbot._r9_engine_console import product, stock, verdict
from tests.chatbot.test_engine import stub_access  # noqa: F401 - a pytest fixture

pytestmark = pytest.mark.usefixtures("stub_access")

CODE = "SRT364-HP"
OTHER = "SRT365-HP"
STOCK_TOOL = "crm_inventory_stock_balance_list"
INCOMING_TOOL = "crm_incoming_stock_list"
COULD_NOT_FETCH_STOCK = f"*stock* for {CODE}:\nI could not fetch stock just now, please try again."


@pytest.fixture
def console(session_factory, monkeypatch, stub_access):
    c = AvailConsole(session_factory, monkeypatch, stub_access, phone="+60100000911")
    c.codes.update(_seed(session_factory, [CODE, OTHER]))
    c.uuid_of = {code: pid for pid, code in c.codes.items()}
    return c


def _failing(monkeypatch, c: AvailConsole, tool: str, failure: BaseException | str) -> None:
    """`tool` fails on the wire; every other tool answers as the console's own fake does.
    A string is what the transport hands back in place of a tool answer."""
    real = MCPRuntimeClient.call_tool

    def call_tool(client, name: str, args: dict[str, Any]) -> str:
        if name != tool:
            return real(client, name, args)
        c.tool_calls.append((name, args))
        if isinstance(failure, BaseException):
            raise failure
        return failure

    monkeypatch.setattr(MCPRuntimeClient, "call_tool", call_tool)


def _tools(c: AvailConsole) -> list[str]:
    return [name for name, _ in c.tool_calls]


FAILURES = {
    "read_timeout": TimeoutError("The read operation timed out"),
    "tool_error": MCPToolCallError("Upstream CRM returned 500"),
    "connection_dropped": ConnectionError("Server disconnected without sending a response"),
    # `sorento_crm_mcp.presenters._http_error_envelope`: what a non-2xx CRM answer becomes.
    "http_error_envelope": json.dumps(
        {
            "result_type": STOCK_TOOL,
            "error": "GET /api/v1/inventory/stock-balance returned HTTP 500",
            "status_code": 500,
            "detail": {},
            "response": "",
            "answers": [],
            "attachments": [],
            "has_result": False,
        }
    ),
    # `present_response` hands a 2xx body it cannot parse back unchanged (`presenters.py:1917`).
    "not_json": "Internal Server Error",
}


@pytest.mark.parametrize("failure", FAILURES.values(), ids=FAILURES.keys())
def test_failed_stock_read_with_a_quantity_says_could_not_fetch_and_nothing_else(
    console, monkeypatch, failure
) -> None:
    _failing(monkeypatch, console, STOCK_TOOL, failure)
    out = console.say(f"check stock {CODE} x 3", stock(product(CODE, 3)))
    assert STOCK_TOOL in _tools(console), console.tool_calls
    assert out == COULD_NOT_FETCH_STOCK


@pytest.mark.parametrize("failure", FAILURES.values(), ids=FAILURES.keys())
def test_failed_stock_read_without_a_quantity_says_could_not_fetch_and_nothing_else(
    console, monkeypatch, failure
) -> None:
    _failing(monkeypatch, console, STOCK_TOOL, failure)
    out = console.say(f"check stock {CODE}", stock(product(CODE)))
    assert out == COULD_NOT_FETCH_STOCK


@pytest.mark.parametrize("failure", FAILURES.values(), ids=FAILURES.keys())
def test_a_failed_stock_read_starts_no_other_lookup(console, monkeypatch, failure) -> None:
    """The probe behind the false line: nothing may be climbed from a read that never answered."""
    _failing(monkeypatch, console, STOCK_TOOL, failure)
    console.say(f"check stock {CODE} x 3", stock(product(CODE, 3)))
    assert INCOMING_TOOL not in _tools(console), console.tool_calls


def test_failed_stock_read_for_two_codes_claims_no_absence_for_either(console, monkeypatch) -> None:
    _failing(monkeypatch, console, STOCK_TOOL, TimeoutError("The read operation timed out"))
    out = console.say(f"check stock {CODE} x 3 {OTHER} x 2", stock(product(CODE, 3), product(OTHER, 2)))
    assert "could not fetch stock" in out, out
    assert "no stock" not in out.lower(), out
    assert "no incoming" not in out.lower(), out


def test_failed_incoming_read_claims_no_absence(console, monkeypatch) -> None:
    """The same ladder from the other side: a dead incoming read must not say "no stock"."""
    _failing(monkeypatch, console, INCOMING_TOOL, TimeoutError("The read operation timed out"))
    out = console.say(
        f"{CODE} incoming?",
        verdict(domain_hint="incoming", intent_hint="check_incoming", entities=[product(CODE)]),
    )
    assert INCOMING_TOOL in _tools(console), console.tool_calls
    assert "no stock" not in out.lower(), out
    assert "no incoming" not in out.lower(), out


def test_the_control_a_read_that_worked_and_found_nothing_still_says_no_stock(console) -> None:
    """The other side of the rule: a real zero is a measured absence and must still be said."""
    out = console.say(f"check stock {CODE} x 3", stock(product(CODE, 3)))
    assert "No stock and no incoming" in out, out
    assert "could not fetch" not in out.lower(), out
