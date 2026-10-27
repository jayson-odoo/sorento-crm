"""MEDIA-JSON-TOLERANT replay: prod turn #597a's shape through the real chain.

27 Oct: a photo captioned SRTKS6547 failed intake with "The vision model returned a
non-object JSON value." and the dealer was told to type the code they had already
typed. Here nothing in the media chain is stubbed except the vision provider's
answer and the image fetch: the real worker task, the real `MediaExtractService`
and `parse_provider_json`, the real job row, the real turn engine. The parser and
the CRM read are stubbed as everywhere in tests/chatbot.
"""
from __future__ import annotations

import json

from app.models.media import MediaExtractionJob
from app.services.chatbot import engine as engine_mod
from app.services.llm_provider import ChatResult
from app.services.media_extract import wording
from app.services.media_extract.service import MediaExtractService

from tests.chatbot.test_engine import _parser_output, stub_access, stub_parser  # noqa: F401
from tests.chatbot.test_media_intake_turn import (  # noqa: F401
    _fresh_contact_id,
    _image_envelope,
    _seed_media_contact,
    _seed_media_limit,
    _seed_settings,
    media_pipeline,
)

JPEG_HEAD = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 64


def _replay(monkeypatch, session_factory, stub_parser, stub_access, media_pipeline, *, content, caption):
    import app.database as database_mod
    from app.services.ai_assistant_service import MCPRuntimeClient

    monkeypatch.setattr(database_mod, "SessionLocal", session_factory)
    monkeypatch.setattr(
        "app.services.media_extract.service.fetch_media_bytes",
        lambda url: (JPEG_HEAD, "image/jpeg"),
    )

    class _Vision:
        def chat(self, **kwargs):
            return ChatResult(content=content, prompt_tokens=800, completion_tokens=20, total_tokens=820)

    monkeypatch.setattr(
        MediaExtractService,
        "_resolve_image_provider",
        lambda self, tier, settings: (_Vision(), "openai", "gpt-4o"),
    )
    tool_calls: list[str] = []
    monkeypatch.setattr(
        MCPRuntimeClient,
        "call_tool",
        lambda client, name, args: tool_calls.append(name) or json.dumps({"ok": True, "items": []}),
    )

    contact_id = _fresh_contact_id()
    _seed_media_contact(session_factory, contact_id)
    _seed_media_limit(session_factory, contact_id=contact_id, modality="image")
    _seed_settings(session_factory, media_sync_wait_seconds=5)
    blocks: list[str] = []
    stub_parser(
        _parser_output(
            intent_hint="check_stock",
            entities=[
                {"raw": "SRTKS6547", "hint": "product", "canonical_code": None, "current_message": True, "confident": True}
            ],
        ),
        on_call=blocks.append,
    )
    stub_access()
    result = engine_mod.run_turn(_image_envelope(caption=caption, contact_id=contact_id), session_factory=session_factory)
    job = (
        session_factory()
        .query(MediaExtractionJob)
        .order_by(MediaExtractionJob.created_at.desc())
        .first()
    )
    return result, blocks, tool_calls, job


def test_replay_list_wrapped_read_is_read_not_failed(
    monkeypatch, session_factory, stub_parser, stub_access, media_pipeline
):
    content = json.dumps([{"entities": [{"raw": "SRTKS6547", "hint": "product", "confident": True}]}])

    result, blocks, tool_calls, job = _replay(
        monkeypatch, session_factory, stub_parser, stub_access, media_pipeline, content=content, caption=None
    )

    assert job.status == "completed", job.error
    assert blocks and "SRTKS6547" in blocks[0]
    assert result.branch_kind != "media_denied"
    assert "I read SRTKS6547 from that photo." in (result.reply or {}).get("text", "")


def test_replay_unreadable_output_with_caption_answers_the_caption(
    monkeypatch, session_factory, stub_parser, stub_access, media_pipeline
):
    result, blocks, tool_calls, job = _replay(
        monkeypatch, session_factory, stub_parser, stub_access, media_pipeline, content="42", caption="SRTKS6547"
    )

    assert job.status == "failed"
    assert "Raw output: '42'" in job.error and "model=gpt-4o" in job.error, job.error
    assert blocks and "SRTKS6547" in blocks[0]
    assert tool_calls, "never reached the answering arm"
    assert result.branch_kind != "media_denied"
    reply = (result.reply or {}).get("text") or ""
    assert reply and wording.nothing_read() not in reply, reply


def test_replay_unreadable_output_without_caption_keeps_the_denial(
    monkeypatch, session_factory, stub_parser, stub_access, media_pipeline
):
    result, blocks, tool_calls, job = _replay(
        monkeypatch, session_factory, stub_parser, stub_access, media_pipeline, content="42", caption=None
    )

    assert job.status == "failed"
    assert blocks == [] and tool_calls == []
    assert result.branch_kind == "media_denied"
    assert (result.reply or {}).get("text") == wording.nothing_read()
