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


# ---------------------------------------------------------------------- the function itself
#
# Crew's independent read of the path (origin/main 5ab31ead29): a failed read keeps `error` on
# the envelope (`turn_runtime.envelope_of`), is never a miss (`turn/fetch.py::envelope_missed`),
# and `engine` hands it to `apply_crossdomain_hit`, which reads only the reply text and the
# empty figures.


def _ladder_over(envelope: dict[str, Any]) -> tuple[str, list[str]]:
    from types import SimpleNamespace

    from app.services.chatbot import answer_bridge
    from app.services.chatbot.lanes.business.services import AnswerServices
    from app.services.chatbot.turn import compose as turn_compose
    from app.services.chatbot.turn.state import Profile

    probed: list[str] = []

    def incoming_has_no_rows(tool: str, args: dict[str, Any]) -> dict[str, Any]:
        probed.append(tool)
        return {"answers": [], "has_result": False}

    row = {"entity_type": "product", "uuid": "11111111-2222-4333-8444-555555555555", "canonical_code": CODE}
    answer = answer_bridge.apply_crossdomain_hit(
        turn_compose.Answer(text="I could not fetch stock just now, please try again."),
        envelope=envelope,
        parser={"message_type": "business_query", "domain_hint": "inventory", "entities": [product(CODE)]},
        resolved={"tokens": [CODE], "intersection": [row]},
        entities_names=[],
        crossdomain_ladder={},
        ctx=SimpleNamespace(),
        services=AnswerServices(mcp_probe=incoming_has_no_rows, family_fetch=lambda query: None),
        contact_id="900000001",
        space_id=None,
        profile=Profile(tier="dealer"),
    )
    return answer.text, probed


def test_the_ladder_claims_no_absence_over_an_envelope_that_carries_an_error() -> None:
    text, probed = _ladder_over({"domain": "inventory", "error": "timeout", "figures": []})
    assert "No stock and no incoming" not in text, text
    assert text == "I could not fetch stock just now, please try again."
    assert probed == []


def test_the_control_the_same_call_without_the_error_does_reach_the_absence_line() -> None:
    """Without this the test above could pass for the wrong reason: a call that never gets
    as far as the line."""
    text, probed = _ladder_over({"domain": "inventory", "figures": []})
    assert f"No stock and no incoming for {CODE}" in text, text
    assert probed == [INCOMING_TOOL]


# ------------------------------------------------------------------ the CRM itself is unreachable
#
# Review of round 1: the MCP server answers a dropped CRM connection with a body that carries
# `error` and no `status_code`. The presenter only knows `status_code >= 400`, so it rendered an
# ordinary empty result, and the engine then told the customer there was no stock.


def _wire_answer_when_the_crm(tool: str, handler: Any, **settings_overrides: Any) -> str:
    """What the chatbot receives, built by the real MCP client, sanitizer and presenter."""
    import asyncio

    import httpx
    from sorento_crm_mcp.http_client import CRMClient
    from sorento_crm_mcp.presenters import present_response
    from sorento_crm_mcp.server import _sanitize_tool_response
    from sorento_crm_mcp.settings import Settings

    async def read() -> str:
        settings = Settings(crm_base_url="http://crm.test", external_api_key="k", **settings_overrides)
        crm = CRMClient(settings, transport=httpx.MockTransport(handler))
        try:
            return await crm.get("/api/v1/external/stock", tool_name=tool)
        finally:
            await crm.aclose()

    return present_response(tool, _sanitize_tool_response(tool, asyncio.run(read())))


def _connection_refused(request: Any) -> Any:
    import httpx

    raise httpx.ConnectError("connection refused", request=request)


def _not_utf8(request: Any) -> Any:
    import httpx

    return httpx.Response(200, content=b"\xff\xfe\xfa")


def _too_large(request: Any) -> Any:
    import httpx

    return httpx.Response(200, content=b"x" * 64)


CRM_FAILURES = {
    "connection_refused": (_connection_refused, {}),
    "not_utf8": (_not_utf8, {}),
    "too_large": (_too_large, {"max_response_bytes": 8}),
}


@pytest.mark.parametrize("handler, overrides", CRM_FAILURES.values(), ids=CRM_FAILURES.keys())
def test_the_crm_failing_behind_the_mcp_server_says_could_not_fetch(
    console, monkeypatch, handler, overrides
) -> None:
    _failing(monkeypatch, console, STOCK_TOOL, _wire_answer_when_the_crm(STOCK_TOOL, handler, **overrides))
    out = console.say(f"check stock {CODE} x 3", stock(product(CODE, 3)))
    assert out == COULD_NOT_FETCH_STOCK


def test_the_crm_failing_on_an_incoming_ask_claims_no_absence(console, monkeypatch) -> None:
    _failing(monkeypatch, console, INCOMING_TOOL, _wire_answer_when_the_crm(INCOMING_TOOL, _connection_refused))
    out = console.say(
        f"{CODE} incoming?",
        verdict(domain_hint="incoming", intent_hint="check_incoming", entities=[product(CODE)]),
    )
    assert "could not fetch" in out, out
    assert "no incoming" not in out.lower() and "no stock" not in out.lower(), out


# ------------------------------------------------------------------ a later rung of the ladder


@pytest.mark.parametrize(
    "po_answer",
    [
        {"error": "GET /api/v1/external/po returned HTTP 500", "answers": [], "has_result": False},
        "Internal Server Error",
        {"unknown": "shape"},
    ],
    ids=["error_envelope", "plain_text", "no_envelope"],
)
def test_a_failed_po_rung_never_says_nothing_on_order(po_answer: Any) -> None:
    """Stock and incoming were read and are empty, so those two absences stand. The PO read
    failed, so "nothing on order" would be a claim nobody measured."""
    from tests.chatbot.test_crossdomain_ladder import _LADDER_WITH_PO, _run

    result, _ = _run(
        ladder=_LADDER_WITH_PO,
        incoming_response={"answers": [], "has_result": False},
        po_response=po_answer,
    )
    block = result["render"]["_xdBlock"]["block"]
    assert "nothing on order" not in block, block
    assert "No stock and no incoming for SRTWC8517" in block, block


# ------------------------------------------------------------------ the multi-ask line


@pytest.mark.parametrize("measure", ["stock", "incoming"])
def test_a_plain_text_answer_is_no_zero_on_a_multi_ask_line(measure: str) -> None:
    from app.services.chatbot.label_catalog import IDENTITY
    from app.services.chatbot.turn import sub_asks

    run = sub_asks.Run(
        call=lambda name, args: "Internal Server Error",
        localizer=IDENTITY,
        grants=frozenset({"purchase_orders.placed"}),
        contact_id="900000001",
        space_id="900001",
    )
    calls = sub_asks._Calls(run)
    lines = sub_asks._lines(run, calls, {"measure": measure}, ["11111111-2222-4333-8444-555555555555"], None)
    assert calls.failures, lines
    assert not any(line.rstrip().endswith(": 0") for line in lines), lines
