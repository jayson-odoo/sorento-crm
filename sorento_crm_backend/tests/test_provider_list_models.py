"""What each adapter offers a picker, and what it refuses to offer.

A provider's list is one flat catalogue covering jobs this system does not use:
OpenAI mixes speech, images and embeddings in with chat, and Gemini answers
`generateContent` on TTS and image models. Offering one of those in a model
picker offers a model that fails at the only work the picker is for.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from app.services.llm_provider import (
    AnthropicProvider,
    GeminiProvider,
    OpenAIProvider,
)


class _StubHTTPResponse:
    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def test_openai_offers_chat_families_and_drops_the_rest(monkeypatch):
    listed = [
        "gpt-5.4-mini",
        "gpt-4o",
        "o3-mini",
        "gpt-4o-mini-tts",
        "gpt-4o-transcribe",
        "text-embedding-3-large",
        "dall-e-3",
        "omni-moderation-latest",
        "whisper-1",
    ]
    provider = OpenAIProvider(api_key="k")
    monkeypatch.setattr(
        provider,
        "_client",
        lambda: SimpleNamespace(
            models=SimpleNamespace(
                list=lambda: SimpleNamespace(
                    data=[SimpleNamespace(id=model_id) for model_id in listed]
                )
            )
        ),
    )

    values = [m.value for m in provider.list_models()]

    assert set(values) == {"gpt-5.4-mini", "gpt-4o", "o3-mini"}


def test_anthropic_keeps_the_display_name_the_api_already_ships(monkeypatch):
    provider = AnthropicProvider(api_key="k")
    monkeypatch.setattr(
        provider,
        "_client",
        lambda: SimpleNamespace(
            models=SimpleNamespace(
                list=lambda limit: SimpleNamespace(
                    data=[
                        SimpleNamespace(id="claude-sonnet-4-6", display_name="Claude Sonnet 4.6"),
                        SimpleNamespace(id="claude-haiku-4-5", display_name=None),
                    ]
                )
            )
        ),
    )

    models = provider.list_models()

    assert (models[0].value, models[0].label) == ("claude-sonnet-4-6", "Claude Sonnet 4.6")
    # No display name is not an empty label: the id is what an operator can act on.
    assert (models[1].value, models[1].label) == ("claude-haiku-4-5", "claude-haiku-4-5")


def test_gemini_filters_on_generate_content_and_then_on_being_able_to_read(monkeypatch):
    payload = {
        "models": [
            {
                "name": "models/gemini-3.5-flash-lite",
                "displayName": "Gemini 3.5 Flash Lite",
                "supportedGenerationMethods": ["generateContent"],
            },
            {
                "name": "models/gemini-embedding-001",
                "supportedGenerationMethods": ["embedContent"],
            },
            {
                # Answers generateContent, cannot read a photo into JSON.
                "name": "models/gemini-2.5-flash-preview-tts",
                "supportedGenerationMethods": ["generateContent"],
            },
            {
                "name": "models/gemini-3-pro-image",
                "supportedGenerationMethods": ["generateContent"],
            },
        ]
    }
    monkeypatch.setattr(
        "httpx.request", lambda method, url, **kwargs: _StubHTTPResponse(payload)
    )

    models = GeminiProvider(api_key="k").list_models()

    assert [(m.value, m.label) for m in models] == [
        ("gemini-3.5-flash-lite", "Gemini 3.5 Flash Lite")
    ]
