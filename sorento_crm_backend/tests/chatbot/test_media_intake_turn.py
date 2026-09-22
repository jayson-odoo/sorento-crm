"""S2 (PLAN-chatbot-media-into-turn.md): image/voice intake INSIDE `run_turn`.

AC-1800 to AC-1816 (UAC section A). Written FIRST - every test here is expected to fail
today because `engine.py::_run_stages` has no media-intake step at all: an image
attachment falls through to being parsed on its caption text (`build_latest_user_message`'s
existing `attachment.description` fallback) and a voice attachment dies at the existing
`AUDIO_NOT_PATCHED_ERROR` block. The RIGHT red reason for every test below is "no
`media_intake` trace stage was ever recorded" / "no `MediaProcessRequest` was ever built" -
never an import error or a fixture bug.

Seams stubbed, same technique `tests/chatbot/test_console_media_turn.py` and
`tests/test_media_process_endpoint.py` already use for the real media pipeline:

* `app.api.v1.external.media.decide_and_record` - a spy WRAPPING the real function (never
  replaced), so the gate/quota/burst logic that already has its own test suite
  (`tests/test_media_process_endpoint.py`) keeps running for real and this file only reads
  what it decided.
* `app.api.v1.external.media.enqueue_job` - runs the "RQ" job INLINE, synchronously,
  against this test's own blank-schema session (never a real Redis/worker).
* `app.tasks.media_tasks.SessionLocal` - repointed at the same blank-schema
  `session_factory`, so the inline job commits into the same transaction this test reads
  back.
* `app.tasks.media_tasks.run_media_extraction` - a canned result body, never a real
  vision/transcription provider call.

None of this asserts anything about the EXTRACTION itself (S3.5's own shapes, already
covered by `tests/test_media_process_endpoint.py` and `tests/test_media_job_lifecycle.py`);
it only proves the ENGINE calls the real pipeline, on the real `chatbot.turns.id`, with no
DB session held across the wait, and reacts correctly to every decision/status the
pipeline can return.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from sqlalchemy import text

from app.models.chatbot_turn import ChatbotTurn
from app.models.media import ContactMediaLimit, ContactMediaUsage, MediaExtractionJob
from app.models.user import SystemSetting
from app.services.chatbot import engine as engine_mod

from tests.chatbot.test_engine import (
    CONTACT_ID,
    _envelope,
    _parser_output,
    seeded,  # noqa: F401
    stub_access,  # noqa: F401
    stub_parser,  # noqa: F401
)


# --------------------------------------------------------------------------- #
# Envelope builders - the Respond.io shapes named in the plan/UAC verbatim.
# --------------------------------------------------------------------------- #


def _attachment_envelope(
    *,
    kind: str,
    url: str = "https://cdn.example/x.jpg",
    mime_type: str = "image/jpeg",
    description: str | None = None,
    size: int = 98641,
    duration_ms: int | None = None,
) -> Any:
    envelope = _envelope()
    attachment: dict[str, Any] = {"type": kind, "url": url, "mimeType": mime_type, "size": size}
    if description is not None:
        attachment["description"] = description
    if duration_ms is not None:
        attachment["duration"] = duration_ms
    envelope.message["message"]["message"] = {"type": "attachment", "attachment": attachment}
    return envelope


def _image_envelope(caption: str | None = None) -> Any:
    return _attachment_envelope(kind="image", description=caption)


def _voice_envelope() -> Any:
    return _attachment_envelope(
        kind="audio", mime_type="audio/ogg", url="https://cdn.example/v.ogg", duration_ms=4500
    )


def _document_envelope() -> Any:
    return _attachment_envelope(
        kind="document", url="https://cdn.example/doc.pdf", mime_type="application/pdf"
    )


def _already_patched_envelope(rendered_text: str = "please check stock for A") -> Any:
    """n8n's transition-window shape: `type:"text"` plus a `_media` marker the old
    sub-media-intake used to stamp on. Exact key TBD by the coder; `_media` is the
    plan's own name for it (module docstring, "already carries n8n's patched
    `type:"text"` + `_media`")."""
    envelope = _envelope()
    envelope.message["message"]["message"] = {
        "type": "text",
        "text": rendered_text,
        "_media": {"modality": "image", "already_patched": True},
    }
    return envelope


# --------------------------------------------------------------------------- #
# Pipeline seams
# --------------------------------------------------------------------------- #


def _contact_uuid(session_factory) -> str:
    db = session_factory()
    return db.execute(
        text("SELECT id FROM respond_contacts WHERE respond_io_id = :c"), {"c": str(CONTACT_ID)}
    ).scalar()


def _seed_media_limit(session_factory, *, modality: str = "image", allowed: bool = True) -> None:
    db = session_factory()
    db.add(
        ContactMediaLimit(contact_id=_contact_uuid(session_factory), modality=modality, is_allowed=allowed)
    )
    db.commit()


def _seed_settings(session_factory, **overrides: Any) -> None:
    db = session_factory()
    row = db.query(SystemSetting).first()
    if row is None:
        row = SystemSetting()
        db.add(row)
    for key, value in overrides.items():
        setattr(row, key, value)
    db.commit()


@pytest.fixture()
def media_pipeline(monkeypatch, session_factory):
    """Wires the real gate/ledger through a spy, runs the "worker" inline, and lets the
    test hand back a canned extraction result. Returns a small controller object.
    """
    import app.api.v1.external.media as media_route
    import app.tasks.media_tasks as media_tasks_mod
    from app.services.media_access_service import decide_and_record as real_decide_and_record

    calls: list[Any] = []

    def _spy_decide_and_record(db, request, **kwargs):
        calls.append(request)
        return real_decide_and_record(db, request, **kwargs)

    monkeypatch.setattr(media_route, "decide_and_record", _spy_decide_and_record)

    def _inline_enqueue(func, *args, **kwargs):
        func(*args)
        return type("FakeJob", (), {"id": "fake-rq-job"})()

    monkeypatch.setattr(media_route, "enqueue_job", _inline_enqueue)
    monkeypatch.setattr(media_tasks_mod, "SessionLocal", session_factory)

    class _Controller:
        def set_result(self, result: dict[str, Any] | None = None, *, error: Exception | None = None) -> None:
            def _run(job):
                if error is not None:
                    raise error
                return result if result is not None else {}

            monkeypatch.setattr(media_tasks_mod, "run_media_extraction", _run)

        def never_runs(self) -> None:
            """The job stays QUEUED forever - simulates outliving the sync wait."""
            monkeypatch.setattr(media_route, "enqueue_job", lambda *a, **k: type("FakeJob", (), {"id": "never"})())

        @property
        def calls(self) -> list[Any]:
            return calls

    return _Controller()


def _trace_of(session_factory, turn_id: str) -> list[dict[str, Any]]:
    row = session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).first()
    assert row is not None, f"no chatbot.turns row for {turn_id}"
    return row.trace or []


def _media_intake_stage(trace: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((r for r in trace if r.get("stage") == "media_intake"), None)


def _usage_rows(session_factory) -> list[ContactMediaUsage]:
    return (
        session_factory()
        .query(ContactMediaUsage)
        .filter(ContactMediaUsage.respond_io_id == str(CONTACT_ID))
        .all()
    )


IMAGE_RESULT = {
    "rendered_text": "Check stock: A, B",
    "confirmation_message": "I read A and B from that photo. Is that right?",
    "entities": [{"raw": "A"}, {"raw": "B"}],
    "attributes": [],
    "notes": None,
    "truncated": False,
    "needs_clarification": False,
}


class TestImageIntakeStage:
    """AC-1800."""

    def test_image_envelope_records_media_intake_stage(
        self, session_factory, seeded, stub_parser, stub_access, media_pipeline
    ):
        _seed_media_limit(session_factory, modality="image")
        _seed_settings(session_factory, media_sync_wait_seconds=5)
        media_pipeline.set_result(IMAGE_RESULT)
        stub_parser()
        stub_access()

        result = engine_mod.run_turn(_image_envelope(caption="Check stock"), session_factory=session_factory)

        trace = _trace_of(session_factory, result.turn_id)
        stage = _media_intake_stage(trace)
        assert stage is not None, (
            "no media_intake trace stage was recorded - the engine does not yet run "
            "image intake inside run_turn (S2 not implemented)"
        )
        facts = stage.get("facts") or {}
        assert facts.get("modality") == "image"
        assert facts.get("decision") == "accepted"
        assert facts.get("status") == "completed"
        assert facts.get("job_id")
        assert "elapsed_ms" in facts


class TestVoiceIntakeStage:
    """AC-1801: modality voice, duration_ms forwarded."""

    def test_voice_envelope_records_media_intake_stage(
        self, session_factory, seeded, stub_parser, stub_access, media_pipeline
    ):
        _seed_media_limit(session_factory, modality="voice")
        _seed_settings(session_factory, media_sync_wait_seconds=5)
        media_pipeline.set_result({"transcript": "stock for SRTWB1455", "confirmation_message": "ok"})
        stub_parser()
        stub_access()

        result = engine_mod.run_turn(_voice_envelope(), session_factory=session_factory)

        trace = _trace_of(session_factory, result.turn_id)
        stage = _media_intake_stage(trace)
        assert stage is not None, "no media_intake stage - voice intake not implemented"
        facts = stage.get("facts") or {}
        assert facts.get("modality") == "voice"
        assert facts.get("status") == "completed"

        assert media_pipeline.calls, "decide_and_record was never called for the voice envelope"
        assert media_pipeline.calls[0].duration_ms == 4500


class TestTurnIdAndContext:
    """AC-1802: `MediaProcessRequest.turn_id` == `chatbot.turns.id`; `context.source ==
    "chat-turn"`; `contact_media_usage.turn_id` carries the same id."""

    def test_turn_id_and_context_source(
        self, session_factory, seeded, stub_parser, stub_access, media_pipeline
    ):
        _seed_media_limit(session_factory, modality="image")
        _seed_settings(session_factory, media_sync_wait_seconds=5)
        media_pipeline.set_result(IMAGE_RESULT)
        stub_parser()
        stub_access()

        result = engine_mod.run_turn(_image_envelope(caption="Check stock"), session_factory=session_factory)

        assert media_pipeline.calls, "media_intake never built a MediaProcessRequest"
        request = media_pipeline.calls[0]
        assert str(request.turn_id) == str(result.turn_id)
        assert (request.context or {}).get("source") == "chat-turn"

        usage_rows = _usage_rows(session_factory)
        assert len(usage_rows) == 1
        assert usage_rows[0].turn_id == str(result.turn_id)


class TestNoSessionHeldAcrossTheWait:
    """AC-1803: no DB session is open while the intake call is in flight; the wait is
    bounded by `media_sync_wait_seconds`.

    Mirrors `test_engine.py::TestSessionDiscipline` exactly - the extraction callable
    stands in for "the wait" the same way the parser stub stands in for the LLM call in
    that file: both are the one seam a real network/worker round trip happens behind.
    """

    def test_no_session_open_while_the_extraction_runs(
        self, counting_session_factory, session_factory, seeded, stub_parser, stub_access, monkeypatch
    ):
        _seed_media_limit(session_factory, modality="image")
        _seed_settings(session_factory, media_sync_wait_seconds=5)
        stub_parser()
        stub_access()

        import app.api.v1.external.media as media_route
        import app.tasks.media_tasks as media_tasks_mod
        from app.services.media_access_service import decide_and_record as real_decide_and_record

        def _spy(db, request, **kwargs):
            return real_decide_and_record(db, request, **kwargs)

        monkeypatch.setattr(media_route, "decide_and_record", _spy)

        def _inline_enqueue(func, *args, **kwargs):
            func(*args)
            return type("FakeJob", (), {"id": "fake-rq-job"})()

        monkeypatch.setattr(media_route, "enqueue_job", _inline_enqueue)
        monkeypatch.setattr(media_tasks_mod, "SessionLocal", counting_session_factory)

        observed: list[int] = []

        def _run(job):
            observed.append(counting_session_factory.state["open"])
            return IMAGE_RESULT

        monkeypatch.setattr(media_tasks_mod, "run_media_extraction", _run)

        engine_mod.run_turn(_image_envelope(caption="Check stock"), session_factory=counting_session_factory)

        assert observed, (
            "run_media_extraction was never called - media intake is not wired into "
            "run_turn yet"
        )
        assert observed == [0], (
            "a DB session was held open across the media extraction wait"
        )


class TestNonImageAttachmentsNotIntaked:
    """AC-1804: a document is not intake and the turn runs on its caption text.

    NOTE FOR THE CAPTAIN (flagged, not silently resolved): a bare "no media_intake
    stage" assertion is TRUE today for every envelope, image included, because no intake
    exists at all yet - so this test alone does not fail for the media feature's absence.
    It is paired here with a positive assertion (the caption text reaches the parser,
    today's existing `attachment.description` fallback) so the test is still meaningful,
    but it will not go red before the coder's change the way the other tests in this file
    do. Recorded rather than deleted because it is a real regression guard once S2 lands.
    """

    def test_document_attachment_is_not_intaked(self, session_factory, seeded, stub_parser, stub_access):
        blocks: list[str] = []
        stub_parser(_parser_output(), on_call=blocks.append)
        stub_access()

        envelope = _document_envelope()
        envelope.message["message"]["message"]["attachment"]["description"] = "here is the price list"
        result = engine_mod.run_turn(envelope, session_factory=session_factory)

        trace = _trace_of(session_factory, result.turn_id)
        assert _media_intake_stage(trace) is None
        assert "here is the price list" in blocks[0]


class TestAlreadyPatchedEnvelopeNotIntakedTwice:
    """AC-1805."""

    def test_one_usage_row_per_message(
        self, session_factory, seeded, stub_parser, stub_access, media_pipeline
    ):
        _seed_media_limit(session_factory, modality="image")
        _seed_settings(session_factory, media_sync_wait_seconds=5)
        media_pipeline.set_result(IMAGE_RESULT)
        stub_parser()
        stub_access()

        envelope = _already_patched_envelope()
        engine_mod.run_turn(envelope, session_factory=session_factory)

        rows = _usage_rows(session_factory)
        assert len(rows) == 1, (
            f"expected exactly one contact_media_usage row for an already-patched "
            f"envelope, found {len(rows)}"
        )


class TestAudioDeadEndRemoved:
    """AC-1806: `AUDIO_NOT_PATCHED_ERROR` is gone - a raw voice envelope never fails
    with the old "media intake did not transcribe" wording."""

    def test_voice_envelope_never_hits_the_retired_error(
        self, session_factory, seeded, stub_parser, stub_access, media_pipeline
    ):
        _seed_media_limit(session_factory, modality="voice")
        _seed_settings(session_factory, media_sync_wait_seconds=5)
        media_pipeline.set_result({"transcript": "stock for SRTWB1455"})
        stub_parser()
        stub_access()

        result = engine_mod.run_turn(_voice_envelope(), session_factory=session_factory)

        assert result.reply is None or "did not transcribe" not in (result.reply or {}).get("text", "")
        row = session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).first()
        assert row.error is None or "did not transcribe" not in row.error


class TestParserInputShapes:
    """AC-1807/AC-1808/AC-1809: what the parser is actually handed."""

    def test_caption_and_raws_joined(self, session_factory, seeded, stub_access, media_pipeline):
        blocks: list[str] = []

        def _fake_parse(config, user_block):
            blocks.append(user_block)
            return _parser_output()

        import app.services.chatbot.head.parser as parser_mod

        def fake_resolve_config(db, *, current_date, override_version_id=None):
            return parser_mod.ParserConfig(
                system_prompt="stub", prompt_version=1, provider="openai", model="gpt-test", api_key="sk-test",
            )

        import pytest as _pytest  # local import avoids a module-level dependency loop
        _ = _pytest

        from unittest.mock import patch as _patch

        with _patch.object(parser_mod, "resolve_config", fake_resolve_config), _patch.object(
            parser_mod, "parse", _fake_parse
        ):
            _seed_media_limit(session_factory, modality="image")
            _seed_settings(session_factory, media_sync_wait_seconds=5)
            media_pipeline.set_result(IMAGE_RESULT)
            stub_access()

            engine_mod.run_turn(_image_envelope(caption="Check stock"), session_factory=session_factory)

        assert blocks, "the parser was never called"
        assert "Check stock: A, B" in blocks[0], blocks[0]

    def test_no_caption_still_renders_the_raws(self, session_factory, seeded, stub_parser, stub_access, media_pipeline):
        _seed_media_limit(session_factory, modality="image")
        _seed_settings(session_factory, media_sync_wait_seconds=5)
        media_pipeline.set_result(
            {
                "rendered_text": "A, B",
                "entities": [{"raw": "A"}, {"raw": "B"}],
                "needs_clarification": True,
                "confirmation_message": "I read A and B. What would you like me to do with it?",
            }
        )
        blocks: list[str] = []
        stub_parser(on_call=blocks.append)
        stub_access()

        engine_mod.run_turn(_image_envelope(caption=None), session_factory=session_factory)

        assert blocks, "no-caption image never reached the parser"
        assert "A, B" in blocks[0], blocks[0]

    def test_voice_transcript_reaches_the_parser_verbatim(
        self, session_factory, seeded, stub_access, media_pipeline
    ):
        blocks: list[str] = []
        import app.services.chatbot.head.parser as parser_mod
        from unittest.mock import patch as _patch

        def fake_resolve_config(db, *, current_date, override_version_id=None):
            return parser_mod.ParserConfig(
                system_prompt="stub", prompt_version=1, provider="openai", model="gpt-test", api_key="sk-test",
            )

        with _patch.object(parser_mod, "resolve_config", fake_resolve_config), _patch.object(
            parser_mod, "parse", lambda config, user_block: blocks.append(user_block) or _parser_output()
        ):
            _seed_media_limit(session_factory, modality="voice")
            _seed_settings(session_factory, media_sync_wait_seconds=5)
            media_pipeline.set_result({"transcript": "stock for SRTWB1455"})
            stub_access()

            engine_mod.run_turn(_voice_envelope(), session_factory=session_factory)

        assert blocks
        assert "stock for SRTWB1455" in blocks[0], blocks[0]


class TestDenialArms:
    """AC-1810/AC-1811/AC-1812: gate/quota/duration/burst denials are ordinary turn
    replies with the existing notice wording, branch_kind `media_denied`, zero parser
    calls (except the silent burst-repeat arm, which answers empty)."""

    def test_denied_gate_replies_with_not_enabled_wording_and_no_parser_call(
        self, session_factory, seeded, stub_access, monkeypatch
    ):
        # No ContactMediaLimit row at all == denied_gate (absence is denial).
        _seed_settings(session_factory, media_sync_wait_seconds=5)
        parser_calls: list[str] = []
        import app.services.chatbot.head.parser as parser_mod
        from unittest.mock import patch as _patch

        from app.services.media_extract import wording

        stub_access()
        with _patch.object(parser_mod, "parse", lambda *a, **k: parser_calls.append(1) or {}):
            result = engine_mod.run_turn(_image_envelope(caption="Check stock"), session_factory=session_factory)

        assert result.branch_kind == "media_denied", (
            f"expected branch_kind 'media_denied', got {result.branch_kind!r} - denial "
            "arm not implemented"
        )
        assert result.reply is not None
        assert wording.not_enabled("image") in result.reply.get("text", "")
        assert not parser_calls, "the parser must not be called on a media denial"

        row = session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).first()
        assert row.status == "done"

    def test_denied_burst_already_shown_answers_empty_with_no_actions(
        self, session_factory, seeded, stub_access, media_pipeline
    ):
        """AC-1812. The gate's own burst-notice-once-per-window rule means the SECOND
        media message inside the same window is the one under test here."""
        import app.services.chatbot.head.parser as parser_mod
        from unittest.mock import patch as _patch

        _seed_media_limit(session_factory, modality="image")
        _seed_settings(session_factory, media_sync_wait_seconds=5, media_burst_limit=1)
        media_pipeline.set_result(IMAGE_RESULT)
        stub_access()

        with _patch.object(parser_mod, "parse", lambda *a, **k: {}):
            # First image: consumes the burst allowance (accepted).
            first_envelope = _image_envelope(caption="Check stock")
            first_envelope.message["message"]["messageId"] = "ZZT-media-burst-1"
            engine_mod.run_turn(first_envelope, session_factory=session_factory)

            # Second image, same window: denied_burst, notice already shown.
            second_envelope = _image_envelope(caption="Check stock")
            second_envelope.message["message"]["messageId"] = "ZZT-media-burst-2"
            result = engine_mod.run_turn(second_envelope, session_factory=session_factory)

        assert result.branch_kind == "media_denied"
        assert (result.reply or {}).get("text") == ""
        assert result.actions == []


class TestFailedAndPendingArms:
    """AC-1813/AC-1814."""

    def test_failed_extraction_replies_nothing_read(
        self, session_factory, seeded, stub_access, media_pipeline
    ):
        from app.services.media_extract import wording
        import app.services.chatbot.head.parser as parser_mod
        from unittest.mock import patch as _patch

        _seed_media_limit(session_factory, modality="image")
        _seed_settings(session_factory, media_sync_wait_seconds=5)
        media_pipeline.set_result(error=RuntimeError("provider timed out"))
        stub_access()

        with _patch.object(parser_mod, "parse", lambda *a, **k: {}):
            result = engine_mod.run_turn(_image_envelope(caption="Check stock"), session_factory=session_factory)

        assert (result.reply or {}).get("text") == wording.nothing_read()
        row = session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).first()
        assert row.status == "failed"

    def test_pending_after_the_wait_replies_the_timeout_sentence(
        self, session_factory, seeded, stub_access, media_pipeline
    ):
        import app.services.chatbot.head.parser as parser_mod
        from unittest.mock import patch as _patch

        _seed_media_limit(session_factory, modality="image")
        _seed_settings(session_factory, media_sync_wait_seconds=5)  # floored to 5s
        media_pipeline.never_runs()
        stub_access()

        with _patch.object(parser_mod, "parse", lambda *a, **k: {}):
            result = engine_mod.run_turn(_image_envelope(caption="Check stock"), session_factory=session_factory)

        assert (result.reply or {}).get("text") == (
            "I could not read that photo in time. Please send it again or type the codes."
        )
        row = session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).first()
        assert row.status == "failed"


class TestQuotaWarnNoticeAppended:
    """AC-1815."""

    def test_warn_notice_appended_once(self, session_factory, seeded, stub_parser, stub_access, media_pipeline):
        _seed_media_limit(session_factory, modality="image")
        # limit=1, warn threshold low enough that the FIRST accepted item already warns.
        _seed_settings(
            session_factory,
            media_sync_wait_seconds=5,
            media_image_monthly_limit=1,
            media_warn_threshold_percent=1,
        )
        media_pipeline.set_result(IMAGE_RESULT)
        stub_parser()
        stub_access()

        result = engine_mod.run_turn(_image_envelope(caption="Check stock"), session_factory=session_factory)

        text_reply = (result.reply or {}).get("text") or ""
        assert text_reply.count("resets") <= 1  # sanity: not appended twice
        usage = _usage_rows(session_factory)
        assert usage and usage[0].notices, "expected a warn_80 notice recorded on the ledger row"
        assert any(n.get("kind") == "warn_80" for n in usage[0].notices)
        assert any(n.get("text") in text_reply for n in usage[0].notices if n.get("kind") == "warn_80")


class TestConsoleBuildsTheSameEnvelope:
    """AC-1816: the console path builds the SAME attachment envelope and calls
    `run_turn` - `_run_console_media_turn`'s own poll+turn code is deleted."""

    def test_poll_media_job_helper_is_gone(self) -> None:
        from app.services.chatbot import console_service

        assert not hasattr(console_service, "_poll_media_job"), (
            "console_service._poll_media_job still exists - S2's collapse to "
            "'build an envelope, call run_turn' has not happened yet"
        )

    def test_console_calls_run_turn_with_an_attachment_envelope(self, monkeypatch, session_factory):
        """Whatever the console's new implementation looks like, it must call the ONE
        `run_turn` seam with an envelope carrying `message.message.attachment`, not the
        retired `run_console_turn(text=...)` shape."""
        from app.services.chatbot import console_service

        captured: list[Any] = []

        def _fake_run_turn(envelope, *, session_factory):
            captured.append(envelope)
            raise NotImplementedError("stop here - only the call shape is under test")

        monkeypatch.setattr(console_service, "run_turn", _fake_run_turn, raising=False)

        with pytest.raises(Exception):
            console_service._run_console_media_turn(
                session_factory(),
                contact_respond_id=str(CONTACT_ID),
                caption="",
                session_vars=None,
                prompt_version_id=None,
                run_id=f"ZZT-console-{uuid.uuid4().hex[:8]}",
                media={"kind": "image", "filename": "p.jpg", "mime": "image/jpeg", "content_base64": "Zm9v"},
            )

        assert captured, (
            "console_service.run_turn was never called - _run_console_media_turn has "
            "not been collapsed to build-envelope-and-call-run_turn yet"
        )
        envelope = captured[0]
        inner = envelope.message["message"]["message"] if hasattr(envelope, "message") else envelope["message"]["message"]["message"]
        assert inner.get("attachment", {}).get("type") == "image"
