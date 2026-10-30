"""SEC-MCP-AUTH (UAC AUTH-7, SCOPE-4): the CRM's MCP client sends the bearer token, and only the
staff AI assistant marks its calls `X-MCP-Scope: staff`.

`MCPRuntimeClient` is the only in-repo MCP caller (AI assistant, chatbot business lane, ideate,
opportunity lane, agent loop), so the token is set there once. No database: the transport is an
httpx MockTransport.
"""
from __future__ import annotations

import inspect
import json
import re

import httpx
import pytest

from app.config import settings
from app.services import ai_assistant_service
from app.services.ai_assistant_service import MCPRuntimeClient

TOKEN = "x" * 40  # fake fixture, built at runtime so it never looks like a real key


@pytest.fixture
def seen(monkeypatch):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = json.loads(request.content)
        result = {"tools": [], "content": [{"type": "text", "text": "{}"}]}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})

    real_client = httpx.Client

    def client_with_mock(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(ai_assistant_service.httpx, "Client", client_with_mock)
    return requests


def test_sends_the_bearer_token(monkeypatch, seen):
    monkeypatch.setattr(settings, "mcp_auth_token", TOKEN)
    MCPRuntimeClient("http://mcp:8765/mcp").list_tools()
    assert seen[0].headers["authorization"] == f"Bearer {TOKEN}"


def test_no_token_configured_sends_no_header(monkeypatch, seen):
    monkeypatch.setattr(settings, "mcp_auth_token", "")
    MCPRuntimeClient("http://mcp:8765/mcp").call_tool("crm_x", {})
    assert "authorization" not in seen[0].headers


def test_the_token_setting_defaults_blank():
    from app.config import Settings

    assert Settings.model_fields["mcp_auth_token"].default == ""


def test_a_token_with_a_trailing_newline_is_stripped(monkeypatch, seen):
    monkeypatch.setattr(settings, "mcp_auth_token", TOKEN + "\n")
    MCPRuntimeClient("http://mcp:8765/mcp").list_tools()
    assert seen[0].headers["authorization"] == f"Bearer {TOKEN}"


def test_default_client_sends_no_staff_marker(seen):
    MCPRuntimeClient("http://mcp:8765/mcp").call_tool("crm_x", {})
    assert "x-mcp-scope" not in seen[0].headers


def test_staff_client_sends_the_staff_marker(seen):
    MCPRuntimeClient("http://mcp:8765/mcp", staff=True).call_tool("crm_x", {})
    assert seen[0].headers["x-mcp-scope"] == "staff"


def _constructions(module) -> list[str]:
    src = inspect.getsource(module)
    return re.findall(r"MCPRuntimeClient\((.*?)\)\n", src, flags=re.S)


def test_every_ai_assistant_client_is_staff():
    calls = _constructions(ai_assistant_service)
    assert len(calls) >= 5
    for args in calls:
        assert "staff=True" in args, args


def test_no_chatbot_lane_client_is_staff():
    from app.services.chatbot.agent import loop
    from app.services.chatbot.lanes import ideate, opportunity
    from app.services.chatbot.lanes.business import services

    for module in (ideate, services, opportunity, loop):
        calls = _constructions(module)
        assert calls, module.__name__
        for args in calls:
            assert "staff" not in args, (module.__name__, args)


# Callers added after the gate (#1982 agent loop, #1864 opportunity lane) build their own
# MCPRuntimeClient; each must still send the bearer and never the staff marker.


def test_agent_loop_catalogue_fetch_sends_the_bearer_token(monkeypatch, seen):
    from app.services.chatbot.agent import loop

    monkeypatch.setattr(settings, "mcp_auth_token", TOKEN)
    monkeypatch.setattr(loop, "_CATALOG_CACHE", {})
    loop._fetch_catalog()
    assert seen[0].headers["authorization"] == f"Bearer {TOKEN}"
    assert "x-mcp-scope" not in seen[0].headers


def test_agent_loop_tool_call_sends_the_bearer_token_and_the_contact(monkeypatch, seen):
    """The loop's production builder is `services._mcp_call(db, timeout_seconds=...)`. That the
    agent's tool runner fills contact_id/space_id from the turn is pinned in
    tests/chatbot/agent/test_agent_tools.py; here they must reach the wire with the bearer."""
    import inspect as _inspect

    from app.services.chatbot.agent import loop
    from app.services.chatbot.lanes.business.fetch import CHATBOT_READ_ONLY_TOOLS
    from app.services.chatbot.lanes.business.services import _mcp_call

    assert "_mcp_call(db, timeout_seconds=seconds)" in _inspect.getsource(loop)
    monkeypatch.setattr(settings, "mcp_auth_token", TOKEN)
    tool = sorted(CHATBOT_READ_ONLY_TOOLS)[0]
    _mcp_call(None, timeout_seconds=7)(tool, {"contact_id": "c-1", "space_id": "s-1"})
    assert seen[0].headers["authorization"] == f"Bearer {TOKEN}"
    assert "x-mcp-scope" not in seen[0].headers
    sent = json.loads(seen[0].content)["params"]["arguments"]
    assert (sent["contact_id"], sent["space_id"]) == ("c-1", "s-1")


def test_opportunity_lane_sends_the_bearer_token(monkeypatch, seen):
    from app.services.chatbot.lanes.opportunity import call_opportunity_tool

    monkeypatch.setattr(settings, "mcp_auth_token", TOKEN)
    call_opportunity_tool("crm_x", {"contact_id": "c-1", "space_id": "s-1"})
    assert seen[0].headers["authorization"] == f"Bearer {TOKEN}"
    assert "x-mcp-scope" not in seen[0].headers
