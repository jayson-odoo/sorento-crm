"""The PO / document reader takes its model from System Settings, not from the env.

The bug this pins, hit in production on 29 Oct 2026: the reader's model came only from
`DOCUMENT_AI_MODEL`, default `gemini-2.5-flash`. The prod Gemini key belongs to a new
Google account, which gets `404 ... no longer available to new users` on that model, so
every page failed and the panel said only "No page of this document could be read" -
while photo reading, whose model is picked in System Settings, read fine on
`gemini-3.5-flash`.

Each test drives the real `extract_document` with `get_provider` recorded, so it asserts
the model the provider was actually built with. The document is a one page image, so
nothing rasterises and no network call is made.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest

from app.config import Settings, settings as app_settings
from app.models.user import SystemSetting
from app.services import document_extraction, llm_provider
from app.services.document_extraction import (
    extract_document,
    is_model_unavailable,
    page_failure_reason,
)
from app.services.llm_provider import ChatResult

from ._pg_fixture import blank_session

PAGE = b"ZZT-not-really-a-png"
NOT_FOUND = (
    "Gemini call failed (404): This model models/gemini-2.5-flash is no longer "
    "available to new users."
)


class _Recorder:
    def __init__(self, raises: str | None = None):
        self.calls: list[tuple[str, str | None]] = []
        self.raises = raises

    def __call__(self, provider_name, api_key, model=None, *_a, **_k):  # noqa: ANN001
        self.calls.append((provider_name, model))
        return _Provider(provider_name, self.raises)


class _Provider:
    def __init__(self, name: str, raises: str | None):
        self.name = name
        self.raises = raises

    def chat(self, _messages, **_k):  # noqa: ANN001
        if self.raises:
            raise RuntimeError(self.raises)
        return ChatResult(content='{"lines": []}', prompt_tokens=1, completion_tokens=1, total_tokens=2)


@pytest.fixture
def env(monkeypatch):
    """The env still names the model that 404s on prod, so a test that passes proves the
    setting won over it."""
    monkeypatch.setattr(app_settings, "document_ai_provider", "gemini", raising=False)
    monkeypatch.setattr(app_settings, "document_ai_model", "ZZT-env-model", raising=False)
    monkeypatch.setattr(app_settings, "gemini_api_key", "ZZT-gemini-key", raising=False)
    monkeypatch.setattr(app_settings, "openai_api_key", "ZZT-openai-key", raising=False)
    return monkeypatch


def _record(monkeypatch, raises: str | None = None) -> _Recorder:
    rec = _Recorder(raises)
    monkeypatch.setattr(document_extraction, "get_provider", rec)
    return rec


def _settings_row(db, **columns) -> SystemSetting:
    row = SystemSetting(**columns)
    db.add(row)
    db.flush()
    return row


def _extract(db):
    return extract_document(db, PAGE, "image/png", prompt_key="po_extractor")


def test_the_model_saved_in_system_settings_is_the_one_the_reader_uses(env):
    rec = _record(env)
    with blank_session() as db:
        _settings_row(db, document_ai_provider="gemini", document_ai_model="ZZT-setting-model")

        result = _extract(db)

    assert rec.calls == [("gemini", "ZZT-setting-model")]
    assert result.model == "gemini/ZZT-setting-model"


def test_the_saved_provider_wins_over_the_env_provider(env):
    rec = _record(env)
    with blank_session() as db:
        _settings_row(db, document_ai_provider="openai", document_ai_model="ZZT-openai-model")

        _extract(db)

    assert rec.calls == [("openai", "ZZT-openai-model")]


def test_a_saved_provider_with_no_model_uses_that_providers_default_not_the_env_model(env):
    """The env model is a Gemini id; posting it to OpenAI would 404 like an outage."""
    rec = _record(env)
    with blank_session() as db:
        _settings_row(db, document_ai_provider="openai", document_ai_model=None)

        _extract(db)

    assert rec.calls == [("openai", llm_provider.default_model_for("openai"))]


def test_a_saved_model_with_no_saved_provider_is_ignored(env):
    """A model id means nothing without its provider; pairing it with the env provider
    is how a `gpt-4o` gets posted to Google."""
    rec = _record(env)
    with blank_session() as db:
        _settings_row(db, document_ai_provider=None, document_ai_model="gpt-4o")

        _extract(db)

    assert rec.calls == [("gemini", "ZZT-env-model")]


def test_the_env_is_only_a_fallback_when_no_setting_is_saved(env):
    rec = _record(env)
    with blank_session() as db:
        _settings_row(db, document_ai_provider=None, document_ai_model=None)

        _extract(db)

    assert rec.calls == [("gemini", "ZZT-env-model")]


def test_with_no_settings_row_at_all_the_env_still_reads(env):
    rec = _record(env)
    with blank_session() as db:
        assert db.query(SystemSetting).count() == 0

        _extract(db)

    assert rec.calls == [("gemini", "ZZT-env-model")]


def test_a_model_not_found_answer_is_the_page_error_and_is_logged_naming_the_model(env, caplog):
    _record(env, raises=NOT_FOUND)
    with blank_session() as db:
        _settings_row(db, document_ai_provider="gemini", document_ai_model="gemini-2.5-flash")

        with caplog.at_level(logging.WARNING, logger=document_extraction.logger.name):
            result = _extract(db)

    assert not result.ok_pages
    assert "no longer available" in result.pages[0].error
    lines = [r.getMessage() for r in caplog.records if "model not available" in r.getMessage()]
    assert len(lines) == 1, lines
    assert "gemini/gemini-2.5-flash" in lines[0]
    assert "System Settings" in lines[0]


def test_a_context_length_error_is_not_read_as_a_missing_model():
    """`404` only as a whole word: 140452 tokens is not a 404."""
    assert not is_model_unavailable(
        "This model's maximum context length is 128000 tokens. However, your messages "
        "resulted in 140452 tokens."
    )
    assert is_model_unavailable(NOT_FOUND)
    assert is_model_unavailable("Error code: 404 - The model `gpt-9` does not exist")


def test_a_key_fragment_in_a_provider_error_never_reaches_the_panel():
    sentence = page_failure_reason(
        [None, "Error code: 401 - Incorrect API key provided: sk-proj-****abcd."]
    )

    assert "sk-proj" not in sentence
    assert "Incorrect API key provided: [key]" in sentence
    assert "System Settings" not in sentence  # not a model problem


def test_a_missing_model_reason_names_where_to_fix_it():
    sentence = page_failure_reason([NOT_FOUND, NOT_FOUND])

    assert sentence.startswith(" Reason: Gemini call failed (404)")
    assert sentence.count("no longer available") == 1
    assert sentence.endswith("System Settings > Chatbot Media.")


# ------------------------------------------------------------ no 2.5 default left


def test_no_gemini_2_5_default_is_left():
    assert llm_provider.default_model_for("gemini") == "gemini-3.5-flash"
    assert Settings.model_fields["document_ai_model"].default == "gemini-3.5-flash"
    assert llm_provider.GeminiProvider("k").default_model == "gemini-3.5-flash"


def test_no_gemini_2_5_model_id_is_hard_coded_in_app_code():
    """A string literal, not a comment: the comments explaining the 404 stay."""
    app_dir = Path(__file__).resolve().parents[1] / "app"
    literal = re.compile(r"""["']gemini-2\.5[^"']*["']""")
    offenders = [
        f"{path.relative_to(app_dir)}:{n}"
        for path in app_dir.rglob("*.py")
        for n, line in enumerate(path.read_text().splitlines(), start=1)
        if literal.search(line.split("#", 1)[0])
    ]
    assert offenders == []
