"""Red tests for W4 (#1277) - offered images ride the chatbot's existing
`send_attachments` action, the same path every other outbound chatbot media uses.

Contract: `documentation/plans/ideation/PLAN-ideation-chat-reply-format.md` (W4),
`ideation-chat-reply-format-acceptance-criteria.md` AC-6/AC-8.

Engine harness matches `tests/chatbot/test_s3_canned_and_ideate.py::
TestIdeateBranchCallsMcpTool` - the same fixtures (imported by name from
`tests.chatbot.test_engine`), the same `_seed_completed_lanes` helper (imported
from `test_s3_canned_and_ideate`), and the same
`app.services.chatbot.lanes.ideate.call_ideation_tool` monkeypatch seam. Nothing
here reaches an LLM, n8n, respond.io or a live MCP server.
"""
from __future__ import annotations

from typing import Any

from app.services.chatbot import engine as engine_mod
from app.services.chatbot.contracts import Envelope

from tests.chatbot.test_engine import (  # noqa: F401 - fixtures reused by name
    CONTACT_ID,
    _envelope,
    _parser_output,
    seeded,
    stub_access,
    stub_parser,
)
from tests.chatbot.test_s3_canned_and_ideate import _seed_completed_lanes

IDEATE_RESULT_WITH_MEDIA: dict[str, Any] = {
    "status": "collecting",
    "reply_text": "Got it - which of these relate to your idea?",
    "link": None,
    "session_vars": {"ideation": {"draft_id": "ZZT-draft-1", "status": "collecting"}},
    # Menu order: image at 1, a non-image at 2 (kept in the text list, never
    # sent as an attachment), image at 3.
    "offered_media": [
        {"position": 1, "kind": "image", "url": "https://respond/1.jpg", "filename": "mockup.jpg"},
        {"position": 2, "kind": "file", "url": "https://respond/2.pdf", "filename": "spec.pdf"},
        {"position": 3, "kind": "image", "url": "https://respond/3.jpg", "filename": "sketch.jpg"},
    ],
}


def _stub_ideate_tool(monkeypatch, session_factory, system_settings_row, result: dict[str, Any]) -> list[dict[str, Any]]:
    from app.services.chatbot.lanes import ideate as ideate_mod

    _seed_completed_lanes(session_factory, system_settings_row)
    calls: list[dict[str, Any]] = []

    def _fake_call(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return dict(result)

    monkeypatch.setattr(ideate_mod, "call_ideation_tool", _fake_call)
    return calls


def _ideate_parser_overrides() -> dict[str, Any]:
    return _parser_output(
        message_type="business_query",
        intent_hint="submit_idea",
        domain_hint="ideate",
        escalation={"is_escalation_confirmation": False, "company_pick": None},
    )


def _ideate_envelope(*, is_test: bool = False) -> Envelope:
    envelope = _envelope()
    if is_test:
        envelope = Envelope(**{**envelope.model_dump(mode="json"), "is_test": True})
    return envelope


class TestOfferedMediaSendsAttachments:
    def test_two_images_become_one_send_attachments_action(
        self, session_factory, seeded, system_settings_row, stub_parser, stub_access, monkeypatch
    ):
        _stub_ideate_tool(monkeypatch, session_factory, system_settings_row, IDEATE_RESULT_WITH_MEDIA)
        stub_parser(_ideate_parser_overrides())
        stub_access()

        result = engine_mod.run_turn(_ideate_envelope(), session_factory=session_factory)

        assert len(result.actions) == 2, result.actions
        send_message, send_attachments = result.actions
        assert send_message["kind"] == "send_message"
        assert send_attachments["kind"] == "send_attachments"

        atts = send_attachments["attachments_src"]
        assert len(atts) == 2
        assert [a["attachmentType"] for a in atts] == ["image", "image"]
        assert [a["caption"] for a in atts] == ["1", "3"]
        assert atts[0]["url"] == "https://respond/1.jpg"
        assert atts[1]["url"] == "https://respond/3.jpg"
        assert all(a["mimeType"].startswith("image/") for a in atts)
        assert send_attachments["dry_run"] is False

    def test_dry_run_console_turn_carries_dry_run_true(
        self, session_factory, seeded, system_settings_row, stub_parser, stub_access, monkeypatch
    ):
        _stub_ideate_tool(monkeypatch, session_factory, system_settings_row, IDEATE_RESULT_WITH_MEDIA)
        stub_parser(_ideate_parser_overrides())
        stub_access()

        result = engine_mod.run_turn(_ideate_envelope(is_test=True), session_factory=session_factory)

        send_attachments = next(a for a in result.actions if a["kind"] == "send_attachments")
        assert send_attachments["dry_run"] is True

    def test_no_offered_media_no_send_attachments_action(
        self, session_factory, seeded, system_settings_row, stub_parser, stub_access, monkeypatch
    ):
        result_no_media = {**IDEATE_RESULT_WITH_MEDIA, "offered_media": []}
        _stub_ideate_tool(monkeypatch, session_factory, system_settings_row, result_no_media)
        stub_parser(_ideate_parser_overrides())
        stub_access()

        result = engine_mod.run_turn(_ideate_envelope(), session_factory=session_factory)

        assert [a["kind"] for a in result.actions] == ["send_message"]

    def test_offered_media_absent_no_send_attachments_action(
        self, session_factory, seeded, system_settings_row, stub_parser, stub_access, monkeypatch
    ):
        result_no_key = {k: v for k, v in IDEATE_RESULT_WITH_MEDIA.items() if k != "offered_media"}
        _stub_ideate_tool(monkeypatch, session_factory, system_settings_row, result_no_key)
        stub_parser(_ideate_parser_overrides())
        stub_access()

        result = engine_mod.run_turn(_ideate_envelope(), session_factory=session_factory)

        assert [a["kind"] for a in result.actions] == ["send_message"]


def test_lane_run_reply_extras_attachments_src_none_without_images(monkeypatch):
    """Unit test of `lanes.ideate.run` in isolation, no DB/engine: `reply_extras
    ["attachments_src"]` is `None` when the tool offers nothing image-shaped."""
    from app.services.chatbot.lanes import ideate as ideate_mod

    monkeypatch.setattr(
        ideate_mod,
        "call_ideation_tool",
        lambda **kwargs: {
            "status": "collecting",
            "reply_text": "ok",
            "link": None,
            "session_vars": {"ideation": None},
        },
    )
    ctx = {
        "parse": {"output": {}},
        "session": {"session_vars": {}},
        "text": {"message": {"message": {"text": "hi"}}},
        "contact": {"id": 12345},
    }
    out = ideate_mod.run(ctx, {}, dry_run=False)
    assert out["reply_extras"]["attachments_src"] is None
