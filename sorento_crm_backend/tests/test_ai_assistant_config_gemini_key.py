"""The Gemini key survives the round trip through the settings service.

`AIAssistantConfigService.to_response_dict` is a HAND-WRITTEN dict, not
`from_attributes` serialization, and `AIAssistantConfigUpdate` is a hand-written
write schema. A new key column that is added to the model and the migration but
missed in either builder produces exactly one symptom: the field always renders
empty in the settings form and the saved value is never seen again. That is the
same family as the `get_user` manual-dict rule in CLAUDE.md, so it gets a test
rather than a reviewer's memory.

Postgres, never sqlite: `ai_assistant_configs` is a real production singleton
and the point is the column round trip, so every test runs on a blank schema.
"""
from __future__ import annotations

from app.schemas.ai_assistant import AIAssistantConfigResponse, AIAssistantConfigUpdate
from app.services.ai_assistant_service import (
    AIAssistantChatService,
    AIAssistantConfigService,
)
from tests._pg_fixture import blank_session


def _payload(**overrides) -> AIAssistantConfigUpdate:
    fields = {
        "provider": "gemini",
        "model": "gemini-2.5-flash",
        "temperature": 0,
        "system_prompt": "",
        "enabled_tools": [],
        "rag_enabled": True,
        "is_enabled": True,
    }
    fields.update(overrides)
    return AIAssistantConfigUpdate(**fields)


def test_the_gemini_key_is_stored_and_returned_masked():
    with blank_session() as db:
        service = AIAssistantConfigService(db)
        row = service.update(
            _payload(gemini_api_key="ZZT-gemini-secret-key-1234"), user_id=None
        )

        assert row.gemini_api_key_ciphertext == "ZZT-gemini-secret-key-1234"

        body = service.to_response_dict(row)
        assert body["gemini_api_key_masked"] == "****1234"
        # The response schema must carry it too, or the FE never sees the field.
        assert (
            AIAssistantConfigResponse(**body).gemini_api_key_masked == "****1234"
        )


def test_a_blank_gemini_key_leaves_the_stored_one_alone():
    """The form posts the MASKED value back when the operator did not edit it;
    an empty or unchanged submission must never wipe a working key."""
    with blank_session() as db:
        service = AIAssistantConfigService(db)
        service.update(_payload(gemini_api_key="ZZT-gemini-secret-key-1234"), user_id=None)

        row = service.update(_payload(gemini_api_key="   "), user_id=None)
        assert row.gemini_api_key_ciphertext == "ZZT-gemini-secret-key-1234"

        row = service.update(_payload(gemini_api_key=None), user_id=None)
        assert row.gemini_api_key_ciphertext == "ZZT-gemini-secret-key-1234"


def test_the_three_provider_keys_are_stored_independently():
    """One key slot per provider is the whole reason the column exists: the
    assistant can run on one provider while the media image lane runs on
    another, so writing one must not disturb the others."""
    with blank_session() as db:
        service = AIAssistantConfigService(db)
        row = service.update(
            _payload(
                provider="openai",
                model="gpt-4o-mini",
                api_key="ZZT-openai-secret-key-1111",
                anthropic_api_key="ZZT-anthropic-secret-key-2222",
                gemini_api_key="ZZT-gemini-secret-key-3333",
            ),
            user_id=None,
        )

        body = service.to_response_dict(row)
        assert body["api_key_masked"] == "****1111"
        assert body["anthropic_api_key_masked"] == "****2222"
        assert body["gemini_api_key_masked"] == "****3333"


def test_the_embedder_never_receives_the_gemini_key(monkeypatch):
    """RAG embeddings are OpenAI-only, so they take an OpenAI key or none.

    `api_key_ciphertext` holds the key for whichever provider the assistant runs
    on. With Gemini selected it is a Google key, and posting it to OpenAI would
    surface as an embedding outage rather than a configuration mistake, so the
    env key is used instead.
    """
    from app.config import settings as app_settings
    from app.services import llm_provider

    monkeypatch.setattr(app_settings, "openai_api_key", "ZZT-openai-env-key", raising=False)
    seen: dict[str, str] = {}

    class _RecordingOpenAI:
        def __init__(self, api_key, model=None):
            seen["api_key"] = api_key
            seen["model"] = model

        def embed(self, _text):
            return [0.1, 0.2]

    monkeypatch.setattr(llm_provider, "OpenAIProvider", _RecordingOpenAI)

    with blank_session() as db:
        AIAssistantConfigService(db).update(
            _payload(gemini_api_key="ZZT-gemini-secret-key-1234", api_key="ZZT-gemini-primary"),
            user_id=None,
        )

        assert AIAssistantChatService(db)._embed_query("stock on hand") == [0.1, 0.2]

    assert seen["api_key"] == "ZZT-openai-env-key"
