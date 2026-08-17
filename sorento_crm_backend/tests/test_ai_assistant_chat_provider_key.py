"""The three assistant chat paths hand `get_provider` the key that belongs to the
configured provider, resolved through the shared `resolve_api_key` ladder.

An assistant on Gemini whose key was entered only in the dedicated Gemini field
must not fall back to the OpenAI env key: that key reaches Google and every
turn 401s. Each test drives the real method with `get_provider` recorded, so it
asserts the key the provider was actually built with, not a source shape.
"""
from __future__ import annotations

import pytest

from app.services.ai_assistant_service import AIAssistantChatService, _TurnToolCache
from app.services.llm_provider import ChatResult
from tests._pg_fixture import blank_session


class _Recorder:
    def __init__(self):
        self.calls: list[tuple[str, str, str | None]] = []

    def __call__(self, provider_name, api_key, model=None, *_a, **_k):
        self.calls.append((provider_name, api_key, model))
        return _AnsweringProvider()


class _AnsweringProvider:
    def chat(self, _messages, **_k):  # noqa: ANN001
        return ChatResult(
            content='{"intent":"unknown","standalone_query":"q"}',
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            tool_calls=[],
        )


class _NoToolsMCP:
    def __init__(self, *_a, **_k):
        pass

    def list_tools_with_schema(self):
        return {}

    def call_tool(self, *_a, **_k):  # pragma: no cover - never reached
        raise AssertionError("no tool should be called")


@pytest.fixture
def gemini_config(monkeypatch):
    """A Gemini-configured assistant with the key ONLY in the Gemini column and a
    tempting OpenAI env key lying around."""
    import app.services.ai_assistant_service as svc_module
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "openai_api_key", "ZZT-openai-env-key", raising=False)
    monkeypatch.setattr(app_settings, "gemini_api_key", "", raising=False)
    recorder = _Recorder()
    monkeypatch.setattr(svc_module, "get_provider", recorder)
    monkeypatch.setattr(svc_module, "MCPRuntimeClient", _NoToolsMCP)

    with blank_session() as db:
        svc = AIAssistantChatService(db)
        cfg = svc.cfg.get()
        cfg.provider = "Gemini"
        cfg.model = "gemini-2.5-flash"
        cfg.api_key_ciphertext = ""
        cfg.gemini_api_key_ciphertext = "ZZT-gemini-column-key"
        cfg.is_enabled = True
        db.commit()
        yield svc, cfg, recorder


def test_the_semantic_parser_uses_the_configured_providers_own_key(gemini_config):
    svc, cfg, recorder = gemini_config

    svc._parse_turn(config=cfg, history=[], user_message="stock of SRTKS6647?")

    assert recorder.calls, "the parser never built a provider"
    assert recorder.calls[0][1] == "ZZT-gemini-column-key"


def test_the_agent_loop_uses_the_configured_providers_own_key(gemini_config):
    svc, cfg, recorder = gemini_config

    svc._run_agent_loop(
        config=cfg,
        history=[],
        user_message="what stock do we hold?",
        standalone_query="what stock do we hold?",
        selected_tools=[],
        sources=[],
        turn_cache=_TurnToolCache(
            user_id="95709c37-0fb4-5c00-8686-536c019e6fb7",
            conversation_id="conv-1",
            turn_id="turn-1",
        ),
    )

    assert recorder.calls, "the agent loop never built a provider"
    assert recorder.calls[0][1] == "ZZT-gemini-column-key"


def test_the_record_answer_uses_the_configured_providers_own_key(gemini_config):
    svc, cfg, recorder = gemini_config

    svc._render_record_answer(
        config=cfg,
        history=[],
        user_message="what is the status?",
        record_ctx={"entity_type": "complaint", "status": "submitted"},
    )

    assert recorder.calls, "the record answer never built a provider"
    assert recorder.calls[0][1] == "ZZT-gemini-column-key"


def test_a_capitalised_openai_provider_still_hands_the_embedder_its_generic_key(monkeypatch):
    """`update()` strips but never lowercases the provider, so `"OpenAI"` is a
    stored value; the generic key column then IS an OpenAI key and the embedder
    must take it rather than fall through to the env key."""
    from app.config import settings as app_settings
    from app.services import llm_provider

    monkeypatch.setattr(app_settings, "openai_api_key", "ZZT-openai-env-key", raising=False)
    seen: dict[str, str] = {}

    class _RecordingOpenAI:
        def __init__(self, api_key, model=None):
            seen["api_key"] = api_key

        def embed(self, _text):
            return [0.1]

    monkeypatch.setattr(llm_provider, "OpenAIProvider", _RecordingOpenAI)

    with blank_session() as db:
        svc = AIAssistantChatService(db)
        cfg = svc.cfg.get()
        cfg.provider = "OpenAI"
        cfg.api_key_ciphertext = "ZZT-openai-column-key"
        db.commit()

        assert svc._embed_query("stock") == [0.1]

    assert seen["api_key"] == "ZZT-openai-column-key"
