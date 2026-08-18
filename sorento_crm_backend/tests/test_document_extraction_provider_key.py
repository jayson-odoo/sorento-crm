"""Document extraction takes the key an operator saved in the UI, not only the env.

The bug this pins, hit in production: a Gemini key entered on the AI assistant
settings page was ignored, because `extract_document` read `settings.gemini_api_key`
directly instead of the shared `resolve_api_key` ladder every other model caller
uses. Every upload came back "extraction unavailable" while a perfectly good key
sat in the database, and the error named only GEMINI_API_KEY, which sent whoever
read it to look at the one place that was NOT the problem.

Each test drives the real `extract_document` with `get_provider` recorded, so it
asserts the key the provider was actually built with rather than a source shape.
The document is a one page image (`image/png`), so nothing rasterises and no
network call is made.
"""
from __future__ import annotations

import pytest

from app.config import settings as app_settings
from app.models.ai_assistant import AIAssistantConfig
from app.services import document_extraction
from app.services.document_extraction import ExtractionUnavailable, extract_document
from app.services.llm_provider import ChatResult

from ._pg_fixture import blank_session

PAGE = b"ZZT-not-really-a-png"


class _Recorder:
    """Stands in for `get_provider`, keeping what it was asked to build."""

    def __init__(self):
        self.calls: list[tuple[str, str, str | None]] = []

    def __call__(self, provider_name, api_key, model=None, *_a, **_k):  # noqa: ANN001
        self.calls.append((provider_name, api_key, model))
        return _AnsweringProvider(provider_name)


class _AnsweringProvider:
    def __init__(self, name: str):
        self.name = name

    def chat(self, _messages, **_k):  # noqa: ANN001
        return ChatResult(
            content='{"lines": []}',
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
        )


@pytest.fixture
def recorder(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(document_extraction, "get_provider", rec)
    monkeypatch.setattr(app_settings, "document_ai_provider", "gemini", raising=False)
    monkeypatch.setattr(app_settings, "gemini_api_key", "", raising=False)
    monkeypatch.setattr(app_settings, "anthropic_api_key", "", raising=False)
    monkeypatch.setattr(app_settings, "openai_api_key", "", raising=False)
    return rec


def _seed_config(db, **columns) -> AIAssistantConfig:
    """The install's one assistant config row, with only what the test needs set."""
    cfg = AIAssistantConfig(
        provider=columns.pop("provider", "openai"),
        model="gpt-4o-mini",
        temperature=0,
        system_prompt="",
        enabled_tools=[],
        **columns,
    )
    db.add(cfg)
    db.flush()
    return cfg


def _extract(db):
    return extract_document(db, PAGE, "image/png", prompt_key="po_extractor")


def test_the_key_saved_on_the_settings_page_is_the_one_the_provider_gets(recorder):
    with blank_session() as db:
        _seed_config(db, gemini_api_key_ciphertext="ZZT-gemini-column-key")

        result = _extract(db)

    assert recorder.calls, "extraction never built a provider"
    assert recorder.calls[0][1] == "ZZT-gemini-column-key"
    assert result.ok_pages, "the page never answered"


def test_the_environment_key_still_works_when_nothing_is_saved(recorder, monkeypatch):
    """No regression: an install that only ever set GEMINI_API_KEY keeps reading."""
    monkeypatch.setattr(app_settings, "gemini_api_key", "ZZT-gemini-env-key", raising=False)

    with blank_session() as db:
        _seed_config(db)

        _extract(db)

    assert recorder.calls[0][1] == "ZZT-gemini-env-key"


def test_the_saved_key_wins_over_the_environment(recorder, monkeypatch):
    """`resolve_api_key`'s documented order: the column first, the env last."""
    monkeypatch.setattr(app_settings, "gemini_api_key", "ZZT-gemini-env-key", raising=False)

    with blank_session() as db:
        _seed_config(db, gemini_api_key_ciphertext="ZZT-gemini-column-key")

        _extract(db)

    assert recorder.calls[0][1] == "ZZT-gemini-column-key"


def test_with_no_assistant_row_at_all_the_environment_key_still_extracts(recorder, monkeypatch):
    """A database that has never saved assistant settings is a legitimate state:
    the resolver must read `None` as "no columns set", not raise."""
    monkeypatch.setattr(app_settings, "gemini_api_key", "ZZT-gemini-env-key", raising=False)

    with blank_session() as db:
        assert db.query(AIAssistantConfig).count() == 0

        result = _extract(db)

    assert recorder.calls[0][1] == "ZZT-gemini-env-key"
    assert result.ok_pages


def test_with_no_key_anywhere_the_message_names_both_places(recorder):
    with blank_session() as db:
        _seed_config(db)

        with pytest.raises(ExtractionUnavailable) as excinfo:
            _extract(db)

    message = str(excinfo.value)
    assert "AI Assistant" in message
    assert "GEMINI_API_KEY" in message
    assert "The document is stored and can be completed by hand." in message
    assert not recorder.calls, "a provider was built without a key"


def test_the_key_is_resolved_for_the_configured_document_provider(recorder, monkeypatch):
    """`document_ai_provider` is switchable, and the key must follow it: resolving
    'gemini' while building an Anthropic client posts a Google key to Anthropic."""
    monkeypatch.setattr(app_settings, "document_ai_provider", "Anthropic", raising=False)
    monkeypatch.setattr(app_settings, "gemini_api_key", "ZZT-gemini-env-key", raising=False)

    with blank_session() as db:
        _seed_config(
            db,
            anthropic_api_key_ciphertext="ZZT-anthropic-column-key",
            gemini_api_key_ciphertext="ZZT-gemini-column-key",
        )

        _extract(db)

    assert recorder.calls[0][0] == "anthropic"
    assert recorder.calls[0][1] == "ZZT-anthropic-column-key"


def test_an_unset_provider_key_for_that_provider_is_the_one_reported(recorder, monkeypatch):
    """The message names the env variable of the provider actually in use."""
    monkeypatch.setattr(app_settings, "document_ai_provider", "anthropic", raising=False)
    monkeypatch.setattr(app_settings, "gemini_api_key", "ZZT-gemini-env-key", raising=False)

    with blank_session() as db:
        _seed_config(db, gemini_api_key_ciphertext="ZZT-gemini-column-key")

        with pytest.raises(ExtractionUnavailable) as excinfo:
            _extract(db)

    assert "ANTHROPIC_API_KEY" in str(excinfo.value)
