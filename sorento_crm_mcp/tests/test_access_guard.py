"""Tests for sorento_crm_mcp.access_guard."""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import pytest


class _FakeClient:
    def __init__(self, response: dict[str, Any]):
        self.response = response
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def post(self, url: str, *, json: dict[str, Any]) -> "_FakeClient":
        self.calls.append((url, json))
        return self

    def raise_for_status(self):  # pragma: no cover
        return None

    def json(self) -> dict[str, Any]:
        return self.response


@pytest.mark.asyncio
async def test_check_access_caches_within_ttl(monkeypatch):
    from sorento_crm_mcp import access_guard

    fake = _FakeClient({"allowed": True, "decision": "allow", "agent_name": "Sales"})

    async def fake_post(self, url, *, json):  # noqa: A002
        fake.calls.append((url, json))
        return type("R", (), {"raise_for_status": lambda self: None, "json": lambda self: fake.response})()

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    access_guard._cache.clear()  # type: ignore[attr-defined]

    g1 = await access_guard.check_access("tool_x", "rio_1", "ws_1", api_url="http://x", api_key="k")
    g2 = await access_guard.check_access("tool_x", "rio_1", "ws_1", api_url="http://x", api_key="k")
    assert g1.allowed is True
    assert g2.allowed is True
    assert len(fake.calls) == 1  # second call was cache hit


@pytest.mark.asyncio
async def test_check_access_deny_passes_through(monkeypatch):
    from sorento_crm_mcp import access_guard

    deny_response = {"allowed": False, "decision": "deny_no_access", "agent_name": "Sales"}

    async def fake_post(self, url, *, json):  # noqa: A002
        return type("R", (), {"raise_for_status": lambda self: None, "json": lambda self: deny_response})()

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    access_guard._cache.clear()  # type: ignore[attr-defined]

    out = await access_guard.check_access("tool_y", "rio_2", "ws_2", api_url="http://x", api_key="k")
    assert out.allowed is False
    assert out.decision == "deny_no_access"
    assert out.agent_name == "Sales"


def test_deny_payload_for_no_access():
    from sorento_crm_mcp.access_guard import deny_payload, AccessDecision

    out = deny_payload(AccessDecision(allowed=False, decision="deny_no_access", agent_name="Sales"))
    parsed = json.loads(out)
    assert parsed["error"] == "ACCESS_DENIED"
    assert parsed["code"] == "CONTACT_NOT_AUTHORIZED"
    assert parsed["message"] == "you are not allowed to access this function: Sales"
    assert parsed["agent_name"] == "Sales"


def test_deny_payload_for_tool_unlinked():
    from sorento_crm_mcp.access_guard import deny_payload, AccessDecision

    out = deny_payload(AccessDecision(allowed=False, decision="deny_tool_unlinked", agent_name=None))
    parsed = json.loads(out)
    assert parsed["code"] == "TOOL_NOT_LINKED"
    assert parsed["message"] == "the required tools are not linked to any supported agents in the system"
    assert parsed["agent_name"] is None
