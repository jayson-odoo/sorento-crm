"""Unit tests for the LLM provider abstraction.

We monkey-patch the SDK client classes so no network calls happen.
"""
from __future__ import annotations

import json
import sys
import types
from typing import Any

import pytest

from app.services.llm_provider import (
    AnthropicProvider,
    ChatResult,
    OpenAIProvider,
    _convert_messages_to_anthropic,
    _convert_tools_to_anthropic,
    _split_system_messages,
    get_provider,
)


# ---- Stubs --------------------------------------------------------------


class _StubFn:
    def __init__(self, name: str, arguments: str) -> None:
        self.name = name
        self.arguments = arguments


class _StubToolCall:
    def __init__(self, id_: str, name: str, arguments: str) -> None:
        self.id = id_
        self.function = _StubFn(name, arguments)


class _StubMsg:
    def __init__(self, content: str | None = "", tool_calls: list[Any] | None = None) -> None:
        self.content = content
        self.tool_calls = tool_calls or []


class _StubChoice:
    def __init__(self, message: _StubMsg) -> None:
        self.message = message


class _StubUsage:
    def __init__(self, prompt: int, completion: int) -> None:
        self.prompt_tokens = prompt
        self.completion_tokens = completion
        self.total_tokens = prompt + completion


class _StubCompletion:
    def __init__(self, message: _StubMsg, usage: _StubUsage) -> None:
        self.choices = [_StubChoice(message)]
        self.usage = usage


class _StubOpenAIClient:
    """Minimal OpenAI client stub: client.chat.completions.create / client.embeddings.create."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key
        self.last_kwargs: dict[str, Any] | None = None

        class _Embeddings:
            def __init__(inner) -> None:
                inner.calls: list[Any] = []

            def create(inner, **kwargs):
                inner.calls.append(kwargs)
                obj = types.SimpleNamespace(
                    data=[types.SimpleNamespace(embedding=[0.1, 0.2, 0.3])]
                )
                return obj

        class _Completions:
            def __init__(inner) -> None:
                inner.calls: list[Any] = []
                inner._next_message = _StubMsg(content="hello", tool_calls=[])
                inner._next_usage = _StubUsage(5, 7)

            def create(inner, **kwargs):
                inner.calls.append(kwargs)
                self.last_kwargs = kwargs
                return _StubCompletion(inner._next_message, inner._next_usage)

        class _Chat:
            def __init__(inner) -> None:
                inner.completions = _Completions()

        self.chat = _Chat()
        self.embeddings = _Embeddings()


# Anthropic stubs ---------------------------------------------------------


class _AntTextBlock:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _AntToolUseBlock:
    def __init__(self, id_: str, name: str, input_: dict) -> None:
        self.type = "tool_use"
        self.id = id_
        self.name = name
        self.input = input_


class _AntUsage:
    def __init__(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _AntResponse:
    def __init__(self, content: list[Any], usage: _AntUsage) -> None:
        self.content = content
        self.usage = usage


class _StubAnthropicClient:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key
        self.last_kwargs: dict[str, Any] | None = None

        class _Messages:
            def __init__(inner) -> None:
                inner._next = _AntResponse(
                    content=[_AntTextBlock("ok-from-anthropic")],
                    usage=_AntUsage(3, 4),
                )

            def create(inner, **kwargs):
                self.last_kwargs = kwargs
                return inner._next

        self.messages = _Messages()


# ---- OpenAIProvider tests ------------------------------------------------


def test_openai_provider_chat_returns_normalized_result(monkeypatch):
    stub = _StubOpenAIClient()
    monkeypatch.setattr("openai.OpenAI", lambda api_key=None: stub)
    provider = OpenAIProvider("k", default_model="gpt-4o-mini")
    result = provider.chat([{"role": "user", "content": "hi"}], temperature=0.0)
    assert isinstance(result, ChatResult)
    assert result.content == "hello"
    assert result.prompt_tokens == 5
    assert result.completion_tokens == 7
    assert result.total_tokens == 12
    assert result.tool_calls == []
    assert stub.last_kwargs and stub.last_kwargs["model"] == "gpt-4o-mini"


def test_openai_provider_chat_normalizes_tool_calls(monkeypatch):
    stub = _StubOpenAIClient()
    stub.chat.completions._next_message = _StubMsg(
        content=None,
        tool_calls=[_StubToolCall("call_1", "do_thing", json.dumps({"x": 1}))],
    )
    monkeypatch.setattr("openai.OpenAI", lambda api_key=None: stub)
    provider = OpenAIProvider("k")
    result = provider.chat(
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "do_thing", "parameters": {}}}],
    )
    assert len(result.tool_calls) == 1
    call = result.tool_calls[0]
    assert call["id"] == "call_1"
    assert call["name"] == "do_thing"
    assert call["arguments"] == {"x": 1}
    assert stub.last_kwargs and stub.last_kwargs.get("tools")


def test_openai_provider_embed_returns_vector(monkeypatch):
    stub = _StubOpenAIClient()
    monkeypatch.setattr("openai.OpenAI", lambda api_key=None: stub)
    provider = OpenAIProvider("k")
    vec = provider.embed("hello")
    assert vec == [0.1, 0.2, 0.3]


def test_openai_test_connection_ok(monkeypatch):
    stub = _StubOpenAIClient()
    monkeypatch.setattr("openai.OpenAI", lambda api_key=None: stub)
    provider = OpenAIProvider("k")
    ok, message, latency = provider.test_connection()
    assert ok is True
    assert message == "OK"
    assert isinstance(latency, int) and latency >= 0


def test_openai_test_connection_failure(monkeypatch):
    class _Boom:
        class chat:
            class completions:
                @staticmethod
                def create(**_kwargs):
                    raise RuntimeError("nope")

        embeddings = None

    monkeypatch.setattr("openai.OpenAI", lambda api_key=None: _Boom())
    provider = OpenAIProvider("k")
    ok, message, latency = provider.test_connection()
    assert ok is False
    assert "nope" in message
    assert isinstance(latency, int)


# ---- AnthropicProvider tests --------------------------------------------


def test_anthropic_provider_chat_strips_system_and_returns_text(monkeypatch):
    stub = _StubAnthropicClient()
    fake_module = types.SimpleNamespace(Anthropic=lambda api_key=None: stub)
    monkeypatch.setitem(sys.modules, "anthropic", fake_module)
    provider = AnthropicProvider("k", default_model="claude-haiku-4-5")
    result = provider.chat(
        [
            {"role": "system", "content": "be terse"},
            {"role": "user", "content": "hi"},
        ],
        temperature=0.0,
    )
    assert result.content == "ok-from-anthropic"
    assert result.prompt_tokens == 3
    assert result.completion_tokens == 4
    assert result.total_tokens == 7
    assert stub.last_kwargs and stub.last_kwargs["system"] == "be terse"
    # system message should have been stripped from messages list
    assert all(m.get("role") != "system" for m in stub.last_kwargs["messages"])


def test_anthropic_chat_normalizes_tool_use_blocks(monkeypatch):
    stub = _StubAnthropicClient()
    stub.messages._next = _AntResponse(  # type: ignore[attr-defined]
        content=[
            _AntTextBlock("partial"),
            _AntToolUseBlock("toolu_1", "do_thing", {"x": 1}),
        ],
        usage=_AntUsage(2, 3),
    )
    fake_module = types.SimpleNamespace(Anthropic=lambda api_key=None: stub)
    monkeypatch.setitem(sys.modules, "anthropic", fake_module)
    provider = AnthropicProvider("k")
    result = provider.chat(
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "do_thing", "parameters": {}}}],
    )
    assert result.content == "partial"
    assert len(result.tool_calls) == 1
    call = result.tool_calls[0]
    assert call["id"] == "toolu_1"
    assert call["name"] == "do_thing"
    assert call["arguments"] == {"x": 1}


def test_anthropic_embed_falls_back_to_openai(monkeypatch):
    from app.config import settings as _settings

    monkeypatch.setattr(_settings, "openai_api_key", "fake-key", raising=False)
    stub = _StubOpenAIClient()
    monkeypatch.setattr("openai.OpenAI", lambda api_key=None: stub)
    provider = AnthropicProvider("k")
    vec = provider.embed("hi")
    assert vec == [0.1, 0.2, 0.3]


def test_anthropic_embed_raises_without_openai_key(monkeypatch):
    from app.config import settings as _settings

    monkeypatch.setattr(_settings, "openai_api_key", None, raising=False)
    provider = AnthropicProvider("k")
    with pytest.raises(RuntimeError):
        provider.embed("hi")


# ---- conversion helpers + factory ---------------------------------------


def test_convert_tools_to_anthropic_shape():
    tools = [
        {
            "type": "function",
            "function": {
                "name": "do_thing",
                "description": "does",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    out = _convert_tools_to_anthropic(tools)
    assert out == [
        {
            "name": "do_thing",
            "description": "does",
            "input_schema": {"type": "object", "properties": {}},
        }
    ]


def test_split_system_messages_concatenates():
    sys_text, rest = _split_system_messages(
        [
            {"role": "system", "content": "a"},
            {"role": "system", "content": "b"},
            {"role": "user", "content": "u"},
        ]
    )
    assert sys_text == "a\n\nb"
    assert rest == [{"role": "user", "content": "u"}]


def test_convert_messages_handles_tool_role():
    out = _convert_messages_to_anthropic(
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "tu_1",
                        "type": "function",
                        "function": {"name": "do_thing", "arguments": json.dumps({"x": 1})},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "tu_1", "content": "{\"ok\": true}"},
        ]
    )
    assert out[0]["role"] == "assistant"
    assert any(b["type"] == "tool_use" for b in out[0]["content"])
    assert out[1]["role"] == "user"
    assert out[1]["content"][0]["type"] == "tool_result"
    assert out[1]["content"][0]["tool_use_id"] == "tu_1"


def test_get_provider_factory():
    p1 = get_provider("openai", "k")
    assert isinstance(p1, OpenAIProvider)
    p2 = get_provider("anthropic", "k")
    assert isinstance(p2, AnthropicProvider)
    with pytest.raises(ValueError):
        get_provider("nope", "k")
