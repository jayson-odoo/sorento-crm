"""`resolve_openai_api_key` - the fix for the prod 401 (turn 387e4b4a): every
OpenAI-only call site (embeddings, RAG search, the chatbot business lane's tool
search, ...) used to read `OPENAI_API_KEY` alone, so a key entered on System
Management > AI Assistant never reached them. One helper, the AI Assistant
config row first, the environment second - same order `resolve_api_key` already
uses for the chat paths.
"""
from __future__ import annotations

from app.services.llm_provider import resolve_openai_api_key
from tests._pg_fixture import blank_session


def test_the_row_key_wins_when_the_environment_is_empty(monkeypatch):
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "openai_api_key", "", raising=False)

    with blank_session() as db:
        from app.services.ai_assistant_service import AIAssistantConfigService

        cfg = AIAssistantConfigService(db).get()
        cfg.provider = "openai"
        cfg.api_key_ciphertext = "ZZT-openai-row-key"
        db.commit()

        assert resolve_openai_api_key(db) == "ZZT-openai-row-key"


def test_the_environment_key_is_used_when_the_row_has_none(monkeypatch):
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "openai_api_key", "ZZT-openai-env-key", raising=False)

    with blank_session() as db:
        from app.services.ai_assistant_service import AIAssistantConfigService

        cfg = AIAssistantConfigService(db).get()
        cfg.provider = "openai"
        cfg.api_key_ciphertext = ""
        db.commit()

        assert resolve_openai_api_key(db) == "ZZT-openai-env-key"


def test_neither_configured_resolves_to_empty_string(monkeypatch):
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "openai_api_key", "", raising=False)

    with blank_session() as db:
        from app.services.ai_assistant_service import AIAssistantConfigService

        cfg = AIAssistantConfigService(db).get()
        cfg.provider = "openai"
        cfg.api_key_ciphertext = ""
        db.commit()

        assert resolve_openai_api_key(db) == ""


def test_a_row_configured_for_a_different_provider_still_falls_back_to_the_openai_env_key(monkeypatch):
    """The row's generic column belongs to whatever `provider` it is set to, so a
    Gemini-configured assistant must not hand its Gemini key to OpenAI just
    because a row exists at all."""
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "openai_api_key", "ZZT-openai-env-key", raising=False)

    with blank_session() as db:
        from app.services.ai_assistant_service import AIAssistantConfigService

        cfg = AIAssistantConfigService(db).get()
        cfg.provider = "gemini"
        cfg.api_key_ciphertext = "ZZT-generic-gemini-owned-key"
        cfg.gemini_api_key_ciphertext = "ZZT-gemini-column-key"
        db.commit()

        assert resolve_openai_api_key(db) == "ZZT-openai-env-key"
