"""PROJECT-REGISTER-V2: the AI extract runs on its own prompt's model when one is set.

`AIExtractService._resolve_provider` used to read only the global `ai_assistant_configs`
row, so the extract could not be pointed at another provider than the chat assistant
(on the dev copy the global row is OpenAI with an exhausted key, so every extract 502d).
The per-prompt production label (`ai_prompt_labels.provider` / `.model`, read through
`ai_prompt_registry.agent_model`) now wins; without one the global row applies exactly as
before, which is what production has.
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.models.ai_assistant import AIAssistantConfig
from app.models.ai_prompt import AIPromptLabel
from app.services import ai_prompt_registry
from app.services.ai_extract import extract_service
from app.services.ai_extract.extract_service import AIExtractService, extract_prompt_key
from app.services.ai_prompt_seed import seed_prompt_registry
from tests._pg_fixture import blank_session

FORM_KEY = "portal.project_registration"


@pytest.fixture
def db() -> Session:
    with blank_session() as session:
        ai_prompt_registry.bust_cache()
        try:
            yield session
        finally:
            ai_prompt_registry.bust_cache()


@pytest.fixture
def seeded(db: Session) -> Session:
    seed_prompt_registry(db.get_bind())
    db.add(AIAssistantConfig(provider="openai", model="gpt-global-test"))
    db.flush()
    return db


@pytest.fixture
def built(monkeypatch):
    """Record what provider the service builds, without any key or network."""
    calls: list[tuple[str, str]] = []

    def fake_get_provider(name, api_key, model=None):
        calls.append((name, model))
        return object()

    monkeypatch.setattr(extract_service, "resolve_api_key", lambda cfg, name: "test-key")
    monkeypatch.setattr(extract_service, "get_provider", fake_get_provider)
    return calls


def _label(db: Session) -> AIPromptLabel:
    row = (
        db.query(AIPromptLabel)
        .filter(
            AIPromptLabel.name == extract_prompt_key(FORM_KEY),
            AIPromptLabel.label == "production",
        )
        .one()
    )
    return row


def test_the_extract_prompt_label_picks_the_provider_and_model(seeded: Session, built):
    row = _label(seeded)
    row.provider = "gemini"
    row.model = "gemini-3.5-flash-lite"
    seeded.flush()

    _provider, provider_name, model_name = AIExtractService(seeded)._resolve_provider(FORM_KEY)

    assert (provider_name, model_name) == ("gemini", "gemini-3.5-flash-lite")
    assert built == [("gemini", "gemini-3.5-flash-lite")]


def test_without_a_label_model_the_global_assistant_row_applies_as_before(
    seeded: Session, built
):
    row = _label(seeded)
    assert row.provider is None and row.model is None  # what production has

    _provider, provider_name, model_name = AIExtractService(seeded)._resolve_provider(FORM_KEY)

    assert (provider_name, model_name) == ("openai", "gpt-global-test")
    assert built == [("openai", "gpt-global-test")]
