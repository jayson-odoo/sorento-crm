"""DEALER-ACCESS-PORTAL UAC F2: the `tool_choice` passthrough on each provider. "required" forces a tool call (the
agent's dealer-access flow); anything else keeps the provider's default. The SDK / HTTP call is stubbed as in
tests/test_llm_provider_json_schema.py and tests/test_llm_provider.py."""
from __future__ import annotations

import sys
import types

from app.services.llm_provider import AnthropicProvider, GeminiProvider, OpenAIProvider
from tests.test_llm_provider import _GeminiTransport, _gemini_text_response, _install
from tests.test_llm_provider_json_schema import _StubAnthropicClient, _StubOpenAIClient

TOOLS = [{
    "type": "function",
    "function": {"name": "zzt_tool", "description": "zzt", "parameters": {"type": "object", "properties": {}}},
}]
MESSAGES = [{"role": "user", "content": "hi"}]


def test_openai_sends_required_when_asked_and_auto_otherwise(monkeypatch):
    stub = _StubOpenAIClient("{}")
    monkeypatch.setattr("openai.OpenAI", lambda api_key=None: stub)
    provider = OpenAIProvider("k", default_model="gpt-4o-mini")

    provider.chat(MESSAGES, tools=TOOLS, tool_choice="required")
    assert stub.last_kwargs["tool_choice"] == "required"
    provider.chat(MESSAGES, tools=TOOLS)
    assert stub.last_kwargs["tool_choice"] == "auto"


def test_gemini_sends_mode_any_only_when_required(monkeypatch):
    t = _install(monkeypatch, _GeminiTransport(_gemini_text_response()))
    provider = GeminiProvider("k", default_model="gemini-2.5-flash")

    provider.chat(MESSAGES, tools=TOOLS, tool_choice="required")
    assert t.body.get("toolConfig") == {"functionCallingConfig": {"mode": "ANY"}}
    provider.chat(MESSAGES, tools=TOOLS)
    assert "toolConfig" not in t.body


def _anthropic(monkeypatch) -> _StubAnthropicClient:
    stub = _StubAnthropicClient({"x": 1})
    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=lambda api_key=None, **kw: stub))
    return stub


def test_anthropic_sends_any_only_when_required_and_not_thinking(monkeypatch):
    stub = _anthropic(monkeypatch)
    provider = AnthropicProvider("k", default_model="claude-sonnet-4-5")

    provider.chat(MESSAGES, tools=TOOLS, tool_choice="required")
    assert stub.last_kwargs.get("tool_choice") == {"type": "any"}
    provider.chat(MESSAGES, tools=TOOLS)
    assert "tool_choice" not in stub.last_kwargs
    provider.chat(MESSAGES, tools=TOOLS, tool_choice="required", reasoning_effort="high")
    assert "thinking" in stub.last_kwargs
    assert "tool_choice" not in stub.last_kwargs
