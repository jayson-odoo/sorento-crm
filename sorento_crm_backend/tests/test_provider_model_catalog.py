"""The model catalogue: what a provider offers, and whether one of them works.

Written against the failure that produced it. On 2026-08-22 every over-quota
photo in the chatbot media lane came back "I could not read anything from that
photo". The degraded model was `gemini-2.5-flash-lite`, picked from a valid
list, on the matching provider - and Google answered `404 ... no longer
available to new users` on the first real call. Google's own ListModels still
returns that model.

So the two halves are tested as two different questions: listing is allowed to
be optimistic and must never take the settings page down, while the probe is the
thing that has to tell the truth.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.services import provider_model_catalog as catalog
from app.services.llm_provider import ProviderModel


class _Cfg:
    """Stand-in for the AIAssistantConfig row `_resolve_key` reads."""


@pytest.fixture(autouse=True)
def _clean_cache():
    catalog.clear_cache()
    yield
    catalog.clear_cache()


def _with_key(monkeypatch, key: str | None) -> None:
    monkeypatch.setattr(catalog, "_resolve_key", lambda db, provider: key)


def _configured_provider(monkeypatch, name: str) -> None:
    """What the AI assistant row says, which a blank provider inherits."""
    monkeypatch.setattr(catalog, "_config", lambda db: SimpleNamespace(provider=name))


class _Provider:
    def __init__(self, models=None, error: Exception | None = None, reply: str = "OK") -> None:
        self._models = models or []
        self._error = error
        self._reply = reply
        self.calls: list[dict[str, Any]] = []

    def list_models(self):
        if self._error:
            raise self._error
        return list(self._models)

    def chat(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        if self._error:
            raise self._error

        class _Result:
            content = self._reply

        return _Result()


def _install_provider(monkeypatch, provider: _Provider) -> list[tuple]:
    seen: list[tuple] = []

    def _get(name, api_key, model=None):
        seen.append((name, api_key, model))
        return provider

    monkeypatch.setattr(catalog, "get_provider", _get)
    return seen


# ---- listing --------------------------------------------------------------


def test_a_live_list_is_served_and_labelled_live(monkeypatch):
    _with_key(monkeypatch, "k")
    _install_provider(monkeypatch, _Provider([ProviderModel("gemini-3.5-flash", "Gemini 3.5 Flash")]))

    result = catalog.list_models(None, "gemini")

    assert result.source == "live"
    assert catalog.model_choices(result) == [
        {"value": "gemini-3.5-flash", "label": "Gemini 3.5 Flash"}
    ]
    assert result.message is None


def test_an_unreachable_provider_falls_back_instead_of_failing_the_page(monkeypatch):
    """A settings page that 500s stops the operator fixing the broken setting."""
    _with_key(monkeypatch, "k")
    _install_provider(monkeypatch, _Provider(error=RuntimeError("connection refused")))

    result = catalog.list_models(None, "openai")

    assert result.source == "fallback"
    assert result.models == catalog.FALLBACK_MODELS["openai"]
    assert "connection refused" in (result.message or "")


def test_no_key_says_so_rather_than_pretending_the_list_is_live(monkeypatch):
    _with_key(monkeypatch, None)

    result = catalog.list_models(None, "anthropic")

    assert result.source == "fallback"
    assert "No API key" in (result.message or "")


def test_an_empty_upstream_list_is_a_fallback_not_an_empty_picker(monkeypatch):
    _with_key(monkeypatch, "k")
    _install_provider(monkeypatch, _Provider([]))

    result = catalog.list_models(None, "gemini")

    assert result.source == "fallback"
    assert result.models == catalog.FALLBACK_MODELS["gemini"]


def test_an_unknown_provider_is_named_rather_than_guessed(monkeypatch):
    result = catalog.list_models(None, "not-a-provider")

    assert result.models == []
    assert "not-a-provider" in (result.message or "")


def test_the_second_read_inside_the_ttl_does_not_call_the_provider_again(monkeypatch):
    _with_key(monkeypatch, "k")
    provider = _Provider([ProviderModel("gpt-5.4", "gpt-5.4")])
    seen = _install_provider(monkeypatch, provider)

    catalog.list_models(None, "openai", now=1000.0)
    catalog.list_models(None, "openai", now=1000.0 + catalog.CACHE_TTL_SECONDS - 1)

    assert len(seen) == 1


def test_the_cache_expires_and_a_rotated_key_is_never_served_the_old_list(monkeypatch):
    provider = _Provider([ProviderModel("gpt-5.4", "gpt-5.4")])
    seen = _install_provider(monkeypatch, provider)

    _with_key(monkeypatch, "key-one")
    catalog.list_models(None, "openai", now=1000.0)
    catalog.list_models(None, "openai", now=1000.0 + catalog.CACHE_TTL_SECONDS + 1)
    assert len(seen) == 2

    _with_key(monkeypatch, "key-two")
    catalog.list_models(None, "openai", now=1000.0)
    assert len(seen) == 3


# ---- probing --------------------------------------------------------------


def test_the_probe_reports_the_providers_own_words_on_a_retired_model(monkeypatch):
    """The sentence an operator can act on is Google's, not one we invent."""
    _with_key(monkeypatch, "k")
    _install_provider(
        monkeypatch,
        _Provider(
            error=RuntimeError(
                "Gemini call failed (404): This model models/gemini-2.5-flash-lite is "
                "no longer available to new users."
            )
        ),
    )

    ok, message, _ = catalog.probe_model(None, "gemini", "gemini-2.5-flash-lite")

    assert ok is False
    assert "no longer available to new users" in message


def test_a_working_model_answers_ok(monkeypatch):
    _with_key(monkeypatch, "k")
    provider = _Provider(reply="OK")
    _install_provider(monkeypatch, provider)

    ok, message, latency_ms = catalog.probe_model(None, "gemini", "gemini-3.5-flash-lite")

    assert (ok, message) == (True, "OK")
    assert latency_ms >= 0
    # The probe goes through `chat`, so it carries whatever generation config the
    # real lane carries - a hand-rolled request would have passed on a model our
    # own thinking budget was breaking.
    assert provider.calls[0]["model"] == "gemini-3.5-flash-lite"
    assert provider.calls[0]["max_tokens"] == catalog.PROBE_MAX_TOKENS


def test_an_empty_answer_is_a_failure_because_the_lane_parses_the_content(monkeypatch):
    _with_key(monkeypatch, "k")
    _install_provider(monkeypatch, _Provider(reply="   "))

    ok, message, _ = catalog.probe_model(None, "gemini", "gemini-2.5-flash")

    assert ok is False
    assert "empty" in message.lower()


def test_the_probe_refuses_before_calling_when_there_is_no_key(monkeypatch):
    _with_key(monkeypatch, None)
    seen = _install_provider(monkeypatch, _Provider())

    ok, message, _ = catalog.probe_model(None, "openai", "gpt-4o")

    assert ok is False
    assert "No API key" in message
    assert seen == []


def test_an_unnamed_model_is_refused_without_a_call(monkeypatch):
    seen = _install_provider(monkeypatch, _Provider())

    ok, message, _ = catalog.probe_model(None, "openai", "  ")

    assert ok is False
    assert message == "No model named."
    assert seen == []


# ---- a blank provider inherits rather than failing ------------------------


def test_a_blank_provider_resolves_to_the_assistants_own(monkeypatch):
    """Blank is what the media settings page saves for "inherit"."""
    _configured_provider(monkeypatch, "gemini")
    _with_key(monkeypatch, "k")
    seen = _install_provider(
        monkeypatch, _Provider([ProviderModel("gemini-3.5-flash", "Gemini 3.5 Flash")])
    )

    result = catalog.list_models(None, "")

    assert result.provider == "gemini"
    assert seen[0][0] == "gemini"


def test_a_blank_provider_with_no_config_row_lands_on_openai(monkeypatch):
    monkeypatch.setattr(catalog, "_config", lambda db: None)
    _with_key(monkeypatch, None)

    assert catalog.list_models(None, None).provider == "openai"


def test_the_probe_inherits_the_same_way(monkeypatch):
    _configured_provider(monkeypatch, "anthropic")
    _with_key(monkeypatch, "k")
    seen = _install_provider(monkeypatch, _Provider(reply="OK"))

    catalog.probe_model(None, "", "claude-haiku-4-5")

    assert seen[0][0] == "anthropic"


# ---- the probe has to certify the job the field is for ---------------------


def test_an_image_probe_actually_sends_an_image(monkeypatch):
    """A text-only model answers the plain probe and fails on every photo.

    `gpt-3.5-turbo` survives the OpenAI chat filter and Google's `gemma-*` models
    support generateContent, so both can be picked for the image lane. Only a call
    carrying an image tells them apart.
    """
    _with_key(monkeypatch, "k")
    provider = _Provider(reply="OK")
    _install_provider(monkeypatch, provider)

    catalog.probe_model(None, "openai", "gpt-4o", with_image=True)

    images = provider.calls[0]["images"]
    assert images and images[0].mime == "image/png"


def test_a_plain_probe_sends_no_image(monkeypatch):
    _with_key(monkeypatch, "k")
    provider = _Provider(reply="OK")
    _install_provider(monkeypatch, provider)

    catalog.probe_model(None, "openai", "gpt-4o")

    assert provider.calls[0]["images"] is None


def test_the_probe_budget_leaves_room_for_a_model_that_thinks_first():
    """Measured 2026-08-23: `o3-mini` returns an empty completion at 64 tokens and
    answers at this ceiling. A tight budget reports a working model as broken."""
    assert catalog.PROBE_MAX_TOKENS >= 512


# ---- a provider that is down is not re-asked on every render ---------------


def test_a_failure_is_cached_briefly_so_a_broken_provider_is_asked_once(monkeypatch):
    _with_key(monkeypatch, "k")
    seen = _install_provider(monkeypatch, _Provider(error=RuntimeError("boom")))

    first = catalog.list_models(None, "openai", now=1000.0)
    second = catalog.list_models(None, "openai", now=1000.0 + 5)

    assert len(seen) == 1
    assert (second.source, second.message) == ("fallback", first.message)
    assert second.models == catalog.FALLBACK_MODELS["openai"]


def test_the_failure_cache_expires_so_a_fixed_provider_recovers(monkeypatch):
    _with_key(monkeypatch, "k")
    seen = _install_provider(monkeypatch, _Provider(error=RuntimeError("boom")))

    catalog.list_models(None, "openai", now=1000.0)
    catalog.list_models(
        None, "openai", now=1000.0 + catalog.FAILURE_CACHE_TTL_SECONDS + 1
    )

    assert len(seen) == 2
