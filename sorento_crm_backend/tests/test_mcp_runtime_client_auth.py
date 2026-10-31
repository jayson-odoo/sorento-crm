"""SEC-MCP-AUTH (UAC AUTH-7, SCOPE-4): the CRM's MCP client sends the bearer token, and only the
staff AI assistant marks its calls `X-MCP-Scope: staff`.

`MCPRuntimeClient` is the only in-repo MCP caller (AI assistant, chatbot business lane, ideate,
opportunity lane, agent loop), so the token is set there once. No database: the transport is an
httpx MockTransport, and the token store (`mcp_auth_token.current_token`, MCP-TOKEN-UI: set on
Settings > Integrations, no env) is replaced by `_token`. The chatbot callers are pinned in
`tests/chatbot/test_mcp_lane_client_auth.py`, because only `tests/chatbot/` may import the chatbot
package (`test_import_boundary.py`).
"""
from __future__ import annotations

import inspect
import json
import re

import httpx
import pytest

from app.services import ai_assistant_service, mcp_auth_token
from app.services.ai_assistant_service import MCPRuntimeClient

TOKEN = "x" * 40  # fake fixture, built at runtime so it never looks like a real key


def _token(monkeypatch, value):
    monkeypatch.setattr(mcp_auth_token, "current_token", lambda db=None: value)


@pytest.fixture(autouse=True)
def _no_token_by_default(monkeypatch):
    _token(monkeypatch, None)


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
    _token(monkeypatch, TOKEN)
    MCPRuntimeClient("http://mcp:8765/mcp").list_tools()
    assert seen[0].headers["authorization"] == f"Bearer {TOKEN}"


def test_no_token_configured_sends_no_header(monkeypatch, seen):
    _token(monkeypatch, None)
    MCPRuntimeClient("http://mcp:8765/mcp").call_tool("crm_x", {})
    assert "authorization" not in seen[0].headers


def test_the_token_is_no_longer_an_env_setting():
    from app.config import Settings

    assert "mcp_auth_token" not in Settings.model_fields


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
