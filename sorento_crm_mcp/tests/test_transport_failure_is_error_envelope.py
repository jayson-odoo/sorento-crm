"""A CRM read that failed on the way must reach the chatbot as an error, not as an empty result.

`present_response` turns a body with `status_code >= 400` into the error envelope. The bodies
`CRMClient` builds itself when the CRM could not be read carried no such status, so they rendered
as an ordinary empty answer: the chatbot told a customer "No stock and no incoming" over a dropped
connection, and a report tool printed "Total RM 0.00" (owner, 1 Nov 2026: "when the stock lookup
fails, the bot shouldnt say no stock").
"""
from __future__ import annotations

import json

import httpx
import pytest

from sorento_crm_mcp.http_client import CRMClient
from sorento_crm_mcp.presenters import present_response
from sorento_crm_mcp.server import _sanitize_tool_response
from sorento_crm_mcp.settings import Settings

TOOLS = [
    "crm_inventory_stock_balance_list",
    "crm_incoming_stock_list",
    "crm_report_ask",
    "crm_sales_report",
    "crm_sales_target_progress",
]


def _refused(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


def _dropped(request: httpx.Request) -> httpx.Response:
    raise httpx.RemoteProtocolError("Server disconnected without sending a response", request=request)


def _timed_out(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("The read operation timed out", request=request)


def _not_utf8(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=b"\xff\xfe\xfa")


def _too_large(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=b"x" * 64)


FAILURES = {
    "refused": (_refused, {}, "request_failed"),
    "dropped": (_dropped, {}, "request_failed"),
    "timed_out": (_timed_out, {}, "request_failed"),
    "not_utf8": (_not_utf8, {}, "invalid_utf8"),
    "too_large": (_too_large, {"max_response_bytes": 8}, "response_too_large"),
}


async def _read(tool: str, handler, overrides: dict) -> str:
    settings = Settings(crm_base_url="http://crm.test", external_api_key="k", **overrides)
    crm = CRMClient(settings, transport=httpx.MockTransport(handler))
    try:
        return await crm.get("/api/v1/external/thing", tool_name=tool)
    finally:
        await crm.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", TOOLS)
@pytest.mark.parametrize("handler, overrides, reason", FAILURES.values(), ids=FAILURES.keys())
async def test_a_failed_read_reaches_the_chatbot_as_an_error(tool, handler, overrides, reason):
    raw = _sanitize_tool_response(tool, await _read(tool, handler, overrides))
    envelope = json.loads(present_response(tool, raw))
    assert envelope.get("error") == reason, envelope
    assert envelope.get("has_result") is False, envelope
    assert not envelope.get("response"), envelope
    assert envelope.get("status_code", 0) >= 400, envelope


@pytest.mark.asyncio
async def test_the_control_a_real_empty_answer_stays_empty_and_is_no_error():
    tool = "crm_inventory_stock_balance_list"

    def empty(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [], "pagination": {"total": 0, "page": 1, "limit": 50}})

    envelope = json.loads(present_response(tool, _sanitize_tool_response(tool, await _read(tool, empty, {}))))
    assert not envelope.get("error"), envelope
    assert envelope.get("has_result") is False, envelope
