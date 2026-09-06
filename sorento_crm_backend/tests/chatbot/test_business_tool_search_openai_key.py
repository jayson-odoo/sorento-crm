"""The chatbot business lane's tool-search embed reads the AI Assistant config
row before the environment, the same fix as `resolve_openai_api_key` (turn
387e4b4a on prod: `tool search failed: Error code: 401 ... invalid_api_key`
because `_embed` read `settings.openai_api_key` alone and prod's env has none).
"""
from __future__ import annotations

from app.services.chatbot.lanes.business.services import fetch_services
from tests._pg_fixture import blank_session


class _Recorder:
    def __init__(self):
        self.calls: list[tuple[str, str, str | None]] = []

    def __call__(self, provider_name, api_key, model=None, *_a, **_k):
        self.calls.append((provider_name, api_key, model))
        return _EmbeddingProvider()


class _EmbeddingProvider:
    def embed(self, _text):
        return [0.1, 0.2, 0.3]


def test_tool_search_embed_uses_the_configured_row_key_over_the_environment(monkeypatch):
    import app.services.llm_provider as llm_provider_mod
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "openai_api_key", "ZZT-openai-env-key", raising=False)
    recorder = _Recorder()
    monkeypatch.setattr(llm_provider_mod, "get_provider", recorder)

    with blank_session() as db:
        from app.services.ai_assistant_service import AIAssistantConfigService

        cfg = AIAssistantConfigService(db).get()
        cfg.provider = "openai"
        cfg.api_key_ciphertext = "ZZT-openai-row-key"
        db.commit()

        services = fetch_services(db)
        vector = services.embed("stock of SRTKS6647")

    assert vector == [0.1, 0.2, 0.3]
    assert recorder.calls, "tool search never built a provider"
    assert recorder.calls[0] == ("openai", "ZZT-openai-row-key", None)
