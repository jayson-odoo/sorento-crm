"""AI-KEY-PER-PROVIDER: every LLM caller hands its provider the key resolved for the
CONFIGURED provider (`llm_provider.resolve_api_key`), never `api_key_ciphertext or
settings.openai_api_key`.

The owner's set-up (31 Oct 2026): provider gemini, the key only in the gemini slot, no OpenAI key
anywhere. Before the fix the extractor ran with no usable key, returned an empty extraction and
the capture turn asked for the idea again.

Plan: documentation/plans/ideation/PLAN-ai-key-per-provider-31oct.md
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.services.ai_assistant_service import AIAssistantConfigService
from app.services.llm_provider import ChatResult
from tests._pg_fixture import blank_session

GEMINI_KEY = "gemini-slot-key"


@pytest.fixture
def gemini_only(monkeypatch) -> Session:
    """Provider gemini, key only in the gemini slot, no generic key, no env keys."""
    from app.config import settings

    monkeypatch.setattr(settings, "openai_api_key", "", raising=False)
    monkeypatch.setattr(settings, "gemini_api_key", "", raising=False)
    with blank_session() as db:
        cfg = AIAssistantConfigService(db).get()
        cfg.provider = "gemini"
        cfg.model = "gemini-2.5-flash"
        cfg.api_key_ciphertext = None
        cfg.openai_api_key_ciphertext = None
        cfg.gemini_api_key_ciphertext = GEMINI_KEY
        cfg.is_enabled = True
        db.commit()
        yield db


class _Recorder:
    """`get_provider` stand-in: records (provider, key) and answers `content`."""

    def __init__(self, content: str = "{}"):
        self.calls: list[tuple[str, str]] = []
        self._content = content

    def __call__(self, provider, api_key, model=None):  # noqa: ANN001
        self.calls.append((provider, api_key))
        content = self._content

        class _P:
            def chat(self, *_a, **_k):
                return ChatResult(content=content, prompt_tokens=1, completion_tokens=1, total_tokens=2)

        return _P()


def test_ideation_extractor_uses_the_gemini_slot_key(gemini_only):
    from app.services.ideation_extractor import extract_ideate_turn

    payload = {"fields": [{"key": "problem", "value": "Price tags hide the promo"}], "has_idea": True}
    rec = _Recorder(json.dumps(payload))
    with patch("app.services.ideation_extractor.get_provider", rec):
        out = extract_ideate_turn(gemini_only, message_text="price tags should show the promo price")
    assert rec.calls == [("gemini", GEMINI_KEY)]
    assert out.fields.get("problem") == "Price tags hide the promo"
    assert out.failed is False


def test_ideation_extractor_marks_a_provider_error_as_failed(gemini_only):
    from app.services.ideation_extractor import extract_ideate_turn

    def _boom(*_a, **_k):
        raise RuntimeError("gemini 400")

    with patch("app.services.ideation_extractor.get_provider", _boom):
        out = extract_ideate_turn(gemini_only, message_text="price tags should show the promo price")
    assert out.failed is True
    assert out.fields == {}


def test_ideation_extractor_marks_no_key_as_failed(gemini_only):
    from app.services.ideation_extractor import extract_ideate_turn

    cfg = AIAssistantConfigService(gemini_only).get()
    cfg.gemini_api_key_ciphertext = None
    gemini_only.commit()
    rec = _Recorder()
    with patch("app.services.ideation_extractor.get_provider", rec):
        out = extract_ideate_turn(gemini_only, message_text="price tags should show the promo price")
    assert rec.calls == []
    assert out.failed is True


def test_ideation_extractor_empty_message_is_not_a_failure(gemini_only):
    from app.services.ideation_extractor import extract_ideate_turn

    assert extract_ideate_turn(gemini_only, message_text="   ").failed is False


def test_ideate_denial_reply_uses_the_gemini_slot_key(gemini_only):
    from app.services.ideation_turn_service import _call_ideate_reply_llm

    rec = _Recorder("You need Ideas access for that.")
    with patch("app.services.ideation_turn_service.get_provider", rec):
        out = _call_ideate_reply_llm(gemini_only, user_message="hi")
    assert rec.calls == [("gemini", GEMINI_KEY)]
    assert out == "You need Ideas access for that."


def test_ticket_intake_draft_uses_the_gemini_slot_key(gemini_only):
    from app.services.ticket_intake_service import TicketIntakeService

    content = json.dumps(
        {
            "title": "Login bug",
            "priority": "high",
            "category": "bug",
            "description_html": "<p>Cannot login</p>",
            "description_text": "Cannot login",
        }
    )
    rec = _Recorder(content)
    with patch("app.services.ticket_intake_service.get_provider", rec):
        preview = TicketIntakeService(gemini_only)._draft_via_llm("I cannot login")
    assert rec.calls == [("gemini", GEMINI_KEY)]
    assert preview.title == "Login bug"


def test_scm_explainer_uses_the_gemini_slot_key(gemini_only):
    from app.services.scm import explainer_service

    rec = _Recorder()
    with patch.object(explainer_service, "get_provider", rec):
        provider, model = explainer_service._provider_and_model(gemini_only)
    assert provider is not None
    assert model == "gemini-2.5-flash"
    assert rec.calls == [("gemini", GEMINI_KEY)]
