"""NO-OPENAI: the clarifier's model falls back to the label / AI assistant config, never to an OpenAI name.

`resolve_clarifier_config` used to pair the configured provider with a hard-coded
`gpt-4.1-mini` whenever the `chatbot_clarifier` label named no model, so an assistant set to
Gemini posted an OpenAI model id to Google. It now resolves the model the way every other reader
does (`llm_provider.resolve_model`): the label's model, else the config's model when the config
runs on the same provider, else that provider's own default.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import ai_assistant_service, ai_prompt_registry
from app.services.chatbot.lanes import casual
from app.services.llm_provider import default_model_for

# The real resolver, not the tree-wide clarifier stub (tests/chatbot/conftest.py `_stub_casual_llm`).
pytestmark = pytest.mark.real_casual_llm


def _config(provider: str, model: str):
    return SimpleNamespace(
        provider=provider,
        model=model,
        api_key_ciphertext=f"{provider}-generic-key",
        openai_api_key_ciphertext="openai-key",
        gemini_api_key_ciphertext="gemini-key",
        anthropic_api_key_ciphertext="anthropic-key",
    )


@pytest.fixture
def wire(monkeypatch):
    def _wire(config, label=(None, None)):
        monkeypatch.setattr(ai_prompt_registry, "render", lambda db, name, **_: ("system", "v1"))
        monkeypatch.setattr(ai_prompt_registry, "agent_model", lambda db, name, label_="production": label)
        monkeypatch.setattr(
            ai_assistant_service.AIAssistantConfigService, "get", lambda self: config
        )
        return casual.resolve_clarifier_config(object())

    return _wire


def test_blank_label_on_gemini_uses_the_configured_gemini_model(wire):
    got = wire(_config("gemini", "gemini-3.5-flash-lite"))
    assert (got.provider, got.model, got.api_key) == ("gemini", "gemini-3.5-flash-lite", "gemini-key")


def test_blank_label_on_openai_uses_the_configured_openai_model(wire):
    got = wire(_config("openai", "gpt-4o"))
    assert (got.provider, got.model) == ("openai", "gpt-4o")


def test_label_provider_without_model_gets_that_providers_default_not_the_configs(wire):
    got = wire(_config("openai", "gpt-4o"), label=("gemini", None))
    assert (got.provider, got.model, got.api_key) == ("gemini", default_model_for("gemini"), "gemini-key")


def test_label_model_without_provider_runs_on_the_configured_provider(wire):
    got = wire(_config("gemini", "gemini-3.5-flash-lite"), label=(None, "gemini-3.5-flash"))
    assert (got.provider, got.model) == ("gemini", "gemini-3.5-flash")


def test_label_provider_and_model_win(wire):
    got = wire(_config("gemini", "gemini-3.5-flash-lite"), label=("anthropic", "claude-haiku-4-5"))
    assert (got.provider, got.model, got.api_key) == ("anthropic", "claude-haiku-4-5", "anthropic-key")


def test_no_openai_model_name_is_hard_coded_in_the_clarifier():
    assert not hasattr(casual, "DEFAULT_MODEL")
