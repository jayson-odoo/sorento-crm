"""LOOKUP-EMBED-CENTRAL slice 1 (AC-LEC-3), the part that imports the chatbot module: the lookup lists'
production embedder follows `resolve_embedder`. Split out of test_lookup_embed_central_slice1.py so only
tests/chatbot/ reaches into app.services.chatbot (tests/chatbot/test_import_boundary.py)."""
from __future__ import annotations

import pytest

from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


@pytest.mark.parametrize(
    "chosen, expect",
    [
        (("gemini", "gemini-embedding-zzt"), ("gemini_embedder", "gemini-embedding-zzt")),
        (("openai", "text-embedding-3-small"), ("provider_embedder", None)),
    ],
)
def test_ac_lec_3_lookup_lists_embedder_follows_resolve_embedder(db, monkeypatch, chosen, expect):
    """No production label is seeded, so only resolve_embedder can make the gemini case choose gemini."""
    from app.services import embedding_settings, llm_provider
    from app.services.ai_assistant_service import AIAssistantConfigService
    from app.services.chatbot.head import lookup_lists

    calls: list[tuple] = []
    monkeypatch.setattr(lookup_lists, "EMBED", lookup_lists.USE_PROVIDER)
    monkeypatch.setattr(embedding_settings, "resolve_embedder", lambda _db: chosen)
    if hasattr(lookup_lists, "resolve_embedder"):
        monkeypatch.setattr(lookup_lists, "resolve_embedder", lambda _db: chosen)
    monkeypatch.setattr(AIAssistantConfigService, "get", lambda self: object())
    monkeypatch.setattr(llm_provider, "resolve_api_key", lambda cfg, provider: "zzt-key")
    sentinel = object()

    def fake_gemini(key, model):
        calls.append(("gemini_embedder", model))
        return sentinel

    def fake_openai(key, *a, **k):
        calls.append(("provider_embedder", None))
        return sentinel

    monkeypatch.setattr(lookup_lists, "gemini_embedder", fake_gemini)
    monkeypatch.setattr(lookup_lists, "provider_embedder", fake_openai)

    assert lookup_lists.embedder(db) is sentinel
    assert calls == [expect]
