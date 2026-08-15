"""`app/services/media_extract/service.py` (`MediaExtractService`, the result
body builders) and `app/services/media_extract/transcribe.py`.

Contract: UAC S4-01, S4-02, S4-09, S4-10 (rendering, PLAN 4.5's table), S5-01,
S5-02, S5-03, S5-04, S5-05, S5-06 (voice), and PLAN section 12.2 item 1/2/4
(lane dispatch by `job.modality`, the entity/attribute split enforced in code,
`response_format: json` + tri-state language parsing).

No paid provider call anywhere in this file. The three seams stubbed, exactly
as specified:
  - `app.services.media_extract.service.fetch_media_bytes` (module-level, so
    tests monkeypatch the name the service module looks up, not `httpx`).
  - the provider resolution inside `MediaExtractService`
    (`MediaExtractService._resolve_image_provider` for the image lane,
    `MediaExtractService._api_key` for the voice lane's key lookup).
  - `app.services.media_extract.transcribe._post_transcription` for the voice
    lane's HTTP call, plus a direct `httpx.post` stub for the one test that
    exercises `_post_transcription`'s own error-mapping code (there is no
    other way to reach that branch without a real request).

The `MediaExtractService.extract()` tests run on Postgres via
`tests._pg_fixture.blank_session` (never sqlite) because `_log_usage` and
`_stamp_usage_cost` write real rows (`ai_assistant_usage_logs`,
`contact_media_usage`) with FK targets that must exist - a marker-prefixed
`RespondContact` + `ContactMediaUsage` chain is seeded per test, never
borrowed.

AC ids covered: S4-01, S4-02, S4-09, S4-10, S5-01, S5-02, S5-03, S5-04, S5-05,
S5-06.
"""
from __future__ import annotations

import json
import uuid

import pytest

from app.services.media_extract import transcribe as transcribe_module
from app.services.media_extract.schema import MediaEntity, MediaExtraction, empty_result_body
from app.services.media_extract.service import (
    MediaExtractService,
    MediaJobInput,
    build_image_result_body,
    build_voice_result_body,
)
from app.services.media_extract.transcribe import TranscriptionError
from app.services.media_extract.wording import (
    clarification,
    confirmation,
    nothing_read,
    truncated_note,
    voice_confirmation,
    voice_language_unsure,
    voice_unclear,
)
from tests._pg_fixture import blank_session


# --------------------------------------------------------------------------- #
# PLAN 4.5's rendered-text table, pure function - no DB                       #
# --------------------------------------------------------------------------- #


def _entity(raw: str, confident: bool = True) -> MediaEntity:
    return MediaEntity(raw=raw, hint="product", current_message=True, confident=confident)


def test_caption_plus_confident_entities_renders_caption_with_raws_appended():
    """PLAN 4.5 row 1."""
    extraction = MediaExtraction(entities=[_entity("SRTKS6647")])
    body = build_image_result_body(
        extraction, caption="check stock for these", max_entities=10
    )

    assert body["rendered_text"] == "check stock for these: SRTKS6647"
    assert body["needs_clarification"] is False
    assert body["confirmation_message"] == confirmation(extraction.entities, [], [])


def test_no_caption_renders_null_and_asks_even_when_the_model_said_otherwise():
    """PLAN 4.5 row 2 - and the load-bearing part: `needs_clarification` is
    forced True by the ABSENCE of a caption regardless of what the model's own
    `needs_clarification` flag said (S4-08 is enforced in code, not trusted to
    the prompt)."""
    extraction = MediaExtraction(entities=[_entity("SRTKS6647")], needs_clarification=False)
    body = build_image_result_body(extraction, caption=None, max_entities=10)

    assert body["rendered_text"] is None
    assert body["needs_clarification"] is True
    assert body["confirmation_message"] is None
    assert body["clarification_message"] == clarification(extraction.entities, [])
    assert "SRTKS6647" in body["clarification_message"], (
        "the clarification must name what was actually read"
    )


def test_unclear_caption_intent_renders_null_and_asks():
    """PLAN 4.5 row 3."""
    extraction = MediaExtraction(entities=[_entity("SRTKS6647")], needs_clarification=True)
    body = build_image_result_body(
        extraction, caption="hmm what is this", max_entities=10
    )

    assert body["rendered_text"] is None
    assert body["needs_clarification"] is True
    assert body["clarification_message"] is not None


def test_nothing_extracted_degrades_to_captions_alone():
    """PLAN 4.5 row 4 / S4-09: identical to today's behaviour when nothing is
    legible - caption alone, plain 'nothing read' confirmation."""
    extraction = MediaExtraction()
    body = build_image_result_body(extraction, caption="check stock", max_entities=10)

    assert body["rendered_text"] == "check stock"
    assert body["needs_clarification"] is False
    assert body["confirmation_message"] == nothing_read()


def test_truncation_note_is_appended_to_the_confirmation():
    """S4-10: truncation is stated, not silent."""
    extraction = MediaExtraction(entities=[_entity("P1")], truncated=True)
    body = build_image_result_body(extraction, caption="check", max_entities=3)

    assert body["truncated"] is True
    assert body["confirmation_message"].endswith(truncated_note(3))


# --------------------------------------------------------------------------- #
# One result shape - the key set is identical across image/voice/empty        #
# --------------------------------------------------------------------------- #


def test_result_body_key_set_is_identical_across_image_voice_and_empty():
    """PLAN section 3.5: one result shape, three transports. Verified here at
    the narrower but more fundamental level - the three body BUILDERS agree
    on the key set, so no consumer written against one is surprised by the
    others."""
    empty = empty_result_body("hi")
    image = build_image_result_body(
        MediaExtraction(entities=[_entity("P1")]), caption="hi", max_entities=10
    )
    voice = build_voice_result_body(transcript="hi there", languages_detected=["en"])

    assert set(empty) == set(image) == set(voice)


# --------------------------------------------------------------------------- #
# Voice result body - S5-03's tri-state (pure, no DB)                        #
# --------------------------------------------------------------------------- #


def test_voice_result_body_empty_language_list_is_unsure_not_silence():
    body = build_voice_result_body(transcript="hello there", languages_detected=[])

    assert body["languages_detected"] == []
    assert body["confirmation_message"] == voice_language_unsure("hello there")


def test_voice_result_body_none_language_list_uses_the_plain_confirmation():
    body = build_voice_result_body(transcript="hello there", languages_detected=None)

    assert body["languages_detected"] is None
    assert body["confirmation_message"] == voice_confirmation("hello there")


def test_voice_result_body_empty_transcript_asks_for_clarification():
    body = build_voice_result_body(transcript="", languages_detected=None)

    assert body["rendered_text"] is None
    assert body["needs_clarification"] is True
    assert body["clarification_message"] == voice_unclear()


# --------------------------------------------------------------------------- #
# transcribe.py - build_request_data for pinned / hints / auto (S5-01)        #
# --------------------------------------------------------------------------- #


def test_build_request_data_pinned_sends_a_single_language():
    data = transcribe_module.build_request_data(
        {"mode": "pinned", "language": "en"}, model="whisper-1"
    )
    assert data == {"model": "whisper-1", "response_format": "json", "language": "en"}


def test_build_request_data_pinned_with_no_language_sends_none():
    """An operator who blanked the pinned language asked for auto-detect, not
    a 400 from an empty `language` field."""
    data = transcribe_module.build_request_data(
        {"mode": "pinned", "language": ""}, model="whisper-1"
    )
    assert "language" not in data


def test_build_request_data_hints_sends_a_language_list():
    data = transcribe_module.build_request_data(
        {"mode": "hints", "languages": ["en", "ms", "zh"]}, model="gpt-4o-transcribe"
    )
    assert data == {
        "model": "gpt-4o-transcribe",
        "response_format": "json",
        "languages": ["en", "ms", "zh"],
    }


def test_build_request_data_hints_with_no_languages_sends_none():
    data = transcribe_module.build_request_data(
        {"mode": "hints", "languages": []}, model="gpt-4o-transcribe"
    )
    assert "languages" not in data


def test_build_request_data_auto_sends_neither():
    data = transcribe_module.build_request_data({"mode": "auto"}, model="whisper-1")
    assert data == {"model": "whisper-1", "response_format": "json"}


def test_build_request_data_with_no_strategy_falls_back_to_pinned_default():
    """S5-02: a fresh install / untouched settings row is pinned/en - this is
    what an unwritten `strategy` (None) must reproduce."""
    data = transcribe_module.build_request_data(None, model="whisper-1")
    assert data == {"model": "whisper-1", "response_format": "json"}


# --------------------------------------------------------------------------- #
# transcribe.py - filename_for (S5-06)                                        #
# --------------------------------------------------------------------------- #


def test_filename_for_known_mime_types():
    assert transcribe_module.filename_for("audio/ogg") == "voice-note.ogg"
    assert transcribe_module.filename_for("audio/mpeg") == "voice-note.mp3"


def test_filename_for_falls_back_to_the_url_extension_when_mime_is_unknown():
    assert (
        transcribe_module.filename_for(None, "https://cdn.example/note.wav")
        == "voice-note.wav"
    )


def test_filename_for_falls_back_to_ogg_when_nothing_identifies_the_clip():
    """WhatsApp voice notes are Ogg/Opus - the honest guess when neither the
    mime type nor the url extension says anything."""
    assert transcribe_module.filename_for(None, None) == "voice-note.ogg"
    assert (
        transcribe_module.filename_for("audio/x-totally-unknown", "https://cdn.example/note")
        == "voice-note.ogg"
    )


# --------------------------------------------------------------------------- #
# transcribe.py - parse_languages tri-state (S5-03)                           #
# --------------------------------------------------------------------------- #


def test_parse_languages_populated_list():
    assert transcribe_module.parse_languages({"languages": ["en", "ms"]}) == ["en", "ms"]


def test_parse_languages_present_but_empty_is_the_unsure_signal():
    assert transcribe_module.parse_languages({"languages": []}) == []


def test_parse_languages_explicit_none_is_also_the_unsure_signal():
    assert transcribe_module.parse_languages({"languages": None}) == []


def test_parse_languages_single_language_field():
    assert transcribe_module.parse_languages({"language": "en"}) == ["en"]


def test_parse_languages_absent_means_the_model_said_nothing():
    assert transcribe_module.parse_languages({}) is None


# --------------------------------------------------------------------------- #
# transcribe() end to end (pure - stubs `_post_transcription`) (S5-06)        #
# --------------------------------------------------------------------------- #


def test_transcribe_pinned_mode_request_shape_and_result(monkeypatch):
    captured = {}

    def fake_post(data, *, filename, mime_type, fields, api_key, timeout):
        captured["fields"] = fields
        captured["filename"] = filename
        return {"text": "check stock please", "language": "en"}

    monkeypatch.setattr(transcribe_module, "_post_transcription", fake_post)

    result = transcribe_module.transcribe(
        b"clip-bytes",
        model="whisper-1",
        strategy={"mode": "pinned", "language": "en"},
        api_key="test-key",
        mime_type="audio/ogg",
    )

    assert captured["fields"] == {
        "model": "whisper-1",
        "response_format": "json",
        "language": "en",
    }
    assert result.text == "check stock please"
    assert result.languages_detected == ["en"]


def test_transcribe_hints_mode_request_shape(monkeypatch):
    captured = {}

    def fake_post(data, *, filename, mime_type, fields, api_key, timeout):
        captured["fields"] = fields
        return {"text": "hello", "languages": ["en", "ms"]}

    monkeypatch.setattr(transcribe_module, "_post_transcription", fake_post)

    result = transcribe_module.transcribe(
        b"clip-bytes",
        model="gpt-4o-transcribe",
        strategy={"mode": "hints", "languages": ["en", "ms", "zh"]},
        api_key="test-key",
    )

    assert captured["fields"]["languages"] == ["en", "ms", "zh"]
    assert result.languages_detected == ["en", "ms"]


def test_transcribe_auto_mode_request_shape(monkeypatch):
    captured = {}

    def fake_post(data, *, filename, mime_type, fields, api_key, timeout):
        captured["fields"] = fields
        return {"text": "bonjour", "languages": []}

    monkeypatch.setattr(transcribe_module, "_post_transcription", fake_post)

    result = transcribe_module.transcribe(
        b"clip-bytes", model="whisper-1", strategy={"mode": "auto"}, api_key="test-key"
    )

    assert "language" not in captured["fields"]
    assert "languages" not in captured["fields"]
    assert result.languages_detected == [], "an empty list is the unsure signal, propagated"


def test_transcribe_with_no_api_key_raises_before_any_http_call(monkeypatch):
    called = []
    monkeypatch.setattr(
        transcribe_module, "_post_transcription", lambda *a, **kw: called.append(1)
    )

    with pytest.raises(TranscriptionError):
        transcribe_module.transcribe(
            b"clip-bytes", model="whisper-1", strategy={"mode": "auto"}, api_key=""
        )
    assert called == []


def test_transcribe_with_zero_bytes_raises_before_any_http_call(monkeypatch):
    called = []
    monkeypatch.setattr(
        transcribe_module, "_post_transcription", lambda *a, **kw: called.append(1)
    )

    with pytest.raises(TranscriptionError):
        transcribe_module.transcribe(
            b"", model="whisper-1", strategy={"mode": "auto"}, api_key="test-key"
        )
    assert called == []


# --------------------------------------------------------------------------- #
# A provider 4xx surfaces the PROVIDER's own message (S5-06)                  #
# --------------------------------------------------------------------------- #


class _FakeHttpResponse:
    def __init__(self, status_code: int, json_body=None, text: str = ""):
        self.status_code = status_code
        self._json_body = json_body
        self.text = text
        self.headers: dict = {}

    def json(self):
        if self._json_body is None:
            raise ValueError("no json body")
        return self._json_body


def test_a_provider_4xx_response_raises_with_the_providers_own_message(monkeypatch):
    """This is the one test in this file that exercises `_post_transcription`
    itself rather than stubbing past it - there is no other way to reach its
    status-code/error-message mapping without a real HTTP call, and the
    stub here (`httpx.post`) makes zero network requests."""
    import httpx

    def fake_http_post(url, headers=None, files=None, data=None, timeout=None):
        return _FakeHttpResponse(
            400,
            json_body={
                "error": {"message": "Opus in Ogg is not supported by this model."}
            },
        )

    monkeypatch.setattr(httpx, "post", fake_http_post)

    with pytest.raises(TranscriptionError) as excinfo:
        transcribe_module.transcribe(
            b"clip-bytes",
            model="whisper-1",
            strategy={"mode": "pinned", "language": "en"},
            api_key="test-key",
        )

    assert "Opus in Ogg is not supported by this model." in str(excinfo.value)


# --------------------------------------------------------------------------- #
# MediaExtractService.extract() - the two lanes, wired end to end             #
# --------------------------------------------------------------------------- #


def _seed_usage(db, modality: str):
    """A minimal, marker-prefixed contact + ledger row for `_log_usage` /
    `_stamp_usage_cost` to attach to. Returns the usage row (already flushed
    and committed, so its id is stable)."""
    from app.models.access import RespondContact
    from app.models.media import ContactMediaUsage

    unique = f"ZZT-mediaextract-{uuid.uuid4().hex[:10]}"
    contact = RespondContact(
        id=str(uuid.uuid4()), phone_number=f"+1555{unique}", respond_io_id=unique
    )
    db.add(contact)
    db.flush()
    usage = ContactMediaUsage(
        id=str(uuid.uuid4()),
        respond_io_id=unique,
        contact_id=contact.id,
        modality=modality,
        message_id=f"{unique}-m1",
        period_key="2026-08",
        outcome="accepted",
        tier="standard",
    )
    db.add(usage)
    db.commit()
    return usage


def test_image_lane_produces_the_confirmation_and_stamps_the_ledger_cost(monkeypatch):
    """S4-01/S4-02 wired end to end through the real service, and PLAN 4.1's
    promise that `_log_usage` stamps cost onto the ledger row 'best-effort, in
    the same pass'."""
    with blank_session() as db:
        usage = _seed_usage(db, "image")

        job = MediaJobInput(
            job_id=str(uuid.uuid4()),
            modality="image",
            tier="standard",
            media_url="https://cdn.respond.io/x.jpg",
            mime_type="image/jpeg",
            caption="check stock for these",
            usage_id=usage.id,
        )

        monkeypatch.setattr(
            "app.services.media_extract.service.fetch_media_bytes",
            lambda url: (b"fake-image-bytes", "image/jpeg"),
        )

        canned = json.dumps(
            {
                "image_kind": "label",
                "entities": [
                    {"raw": "SRTKS6647", "hint": "product", "confident": True}
                ],
                "attributes": [
                    {
                        "kind": "batch_number",
                        "raw": "YG2539",
                        "entity_raw": None,
                        "confident": True,
                    }
                ],
                "conflicts": [],
                "needs_clarification": False,
                "truncated": False,
                "notes": None,
            }
        )

        from app.services.llm_provider import ChatResult

        class _StubProvider:
            def chat(self, **kwargs):
                return ChatResult(
                    content=canned, prompt_tokens=120, completion_tokens=40, total_tokens=160
                )

        monkeypatch.setattr(
            MediaExtractService,
            "_resolve_image_provider",
            lambda self, tier, settings: (_StubProvider(), "openai", "gpt-4o"),
        )

        outcome = MediaExtractService(db).extract(job)

        assert outcome.result["entities"] == [
            {
                "raw": "SRTKS6647",
                "hint": "product",
                "current_message": True,
                "confident": True,
            }
        ]
        assert "SRTKS6647" in outcome.result["confirmation_message"]
        assert "YG2539" in outcome.result["confirmation_message"]
        assert outcome.prompt_tokens == 120
        assert outcome.completion_tokens == 40

        db.refresh(usage)
        assert usage.provider == "openai"
        assert usage.model == "gpt-4o"
        assert usage.prompt_tokens == 120
        assert usage.completion_tokens == 40


def test_voice_lane_transcribes_and_defaults_to_the_pinned_english_strategy(
    monkeypatch,
):
    """S5-02: an untouched settings row (nothing seeded in this blank schema)
    resolves to pinned/`en`, matching today's behaviour exactly - and the
    strategy actually reaches the transcription request, not just the
    resolver."""
    with blank_session() as db:
        usage = _seed_usage(db, "voice")

        job = MediaJobInput(
            job_id=str(uuid.uuid4()),
            modality="voice",
            tier="standard",
            media_url="https://cdn.respond.io/x.ogg",
            mime_type="audio/ogg",
            caption=None,
            usage_id=usage.id,
        )

        monkeypatch.setattr(
            "app.services.media_extract.service.fetch_media_bytes",
            lambda url: (b"fake-audio-bytes", "audio/ogg"),
        )
        monkeypatch.setattr(
            MediaExtractService, "_api_key", staticmethod(lambda cfg, provider_name: "test-key")
        )

        captured = {}

        def fake_post(data, *, filename, mime_type, fields, api_key, timeout):
            captured["fields"] = fields
            return {"text": "check stock please", "language": "en"}

        monkeypatch.setattr(
            "app.services.media_extract.transcribe._post_transcription", fake_post
        )

        outcome = MediaExtractService(db).extract(job)

        assert captured["fields"] == {
            "model": "whisper-1",
            "response_format": "json",
            "language": "en",
        }
        assert outcome.result["transcript"] == "check stock please"
        assert outcome.result["rendered_text"] == "check stock please"
        assert outcome.result["confirmation_message"] == voice_confirmation(
            "check stock please"
        )
        assert outcome.result["languages_detected"] == ["en"]


def test_voice_lane_empty_transcript_asks_for_clarification_end_to_end(monkeypatch):
    with blank_session() as db:
        job = MediaJobInput(
            job_id=str(uuid.uuid4()),
            modality="voice",
            tier="standard",
            media_url="https://cdn.respond.io/x.ogg",
            mime_type="audio/ogg",
            caption=None,
            usage_id=None,  # no ledger row -> _stamp_usage_cost / _log_usage no-op
        )

        monkeypatch.setattr(
            "app.services.media_extract.service.fetch_media_bytes",
            lambda url: (b"fake-audio-bytes", "audio/ogg"),
        )
        monkeypatch.setattr(
            MediaExtractService, "_api_key", staticmethod(lambda cfg, provider_name: "test-key")
        )
        monkeypatch.setattr(
            "app.services.media_extract.transcribe._post_transcription",
            lambda *a, **kw: {"text": "", "language": None},
        )

        outcome = MediaExtractService(db).extract(job)

        assert outcome.result["transcript"] is None
        assert outcome.result["needs_clarification"] is True
        assert outcome.result["clarification_message"] == voice_unclear()


def test_lane_dispatch_is_by_modality_alone_and_rejects_anything_else(monkeypatch):
    """PLAN section 12.2 item 1: `job.modality` is the only dispatch."""
    from app.services.media_extract.service import MediaExtractionError

    with blank_session() as db:
        job = MediaJobInput(
            job_id=str(uuid.uuid4()),
            modality="carrier_pigeon",
            tier=None,
            media_url=None,
            mime_type=None,
            caption=None,
            usage_id=None,
        )
        with pytest.raises(MediaExtractionError):
            MediaExtractService(db).extract(job)


# --------------------------------------------------------------------------- #
# The degraded tier reaches the voice lane (PLAN 16.1)                        #
# --------------------------------------------------------------------------- #


def _voice_settings(**overrides):
    """The resolved-settings shape the voice lane reads, as a plain stub.

    Only the four fields `_extract_voice` touches, so this test cannot pass by
    accidentally depending on the whole `MediaSettings` dataclass.
    """
    from types import SimpleNamespace

    base = dict(
        transcribe_model="whisper-1",
        voice_degraded_model=None,
        extraction_timeout_seconds=45,
    )
    base.update(overrides)
    base.setdefault("language_strategy", lambda: {"mode": "pinned", "language": "en"})
    return SimpleNamespace(**base)


def test_resolve_voice_model_uses_the_degraded_model_only_at_the_degraded_tier():
    """S2-06 for voice. `job.tier` was ignored here, so an over-quota voice note
    was transcribed on the standard model while the contact was told accuracy
    had dropped - a warning label on a change that never happened."""
    resolve = MediaExtractService._resolve_voice_model
    settings = _voice_settings(voice_degraded_model="whisper-cheap")

    assert resolve("standard", settings) == "whisper-1"
    assert resolve(None, settings) == "whisper-1"
    assert resolve("degraded", settings) == "whisper-cheap"


def test_resolve_voice_model_never_borrows_the_image_degraded_model():
    """The blocker: one shared column degraded voice onto whatever the IMAGE
    tier named, which is not a transcription model at all."""
    resolve = MediaExtractService._resolve_voice_model
    settings = _voice_settings(voice_degraded_model=None)
    settings.image_degraded_model = "gpt-4o-mini"

    assert resolve("degraded", settings) == "whisper-1"


def test_voice_lane_sends_the_degraded_model_in_the_transcription_request(
    monkeypatch,
):
    """End to end through the real lane: the tier on the job row has to reach
    the multipart `model` field, not just the resolver."""
    with blank_session() as db:
        usage = _seed_usage(db, "voice")

        job = MediaJobInput(
            job_id=str(uuid.uuid4()),
            modality="voice",
            tier="degraded",
            media_url="https://cdn.respond.io/x.ogg",
            mime_type="audio/ogg",
            caption=None,
            usage_id=usage.id,
        )

        monkeypatch.setattr(
            "app.services.media_extract.service.fetch_media_bytes",
            lambda url: (b"fake-audio-bytes", "audio/ogg"),
        )
        monkeypatch.setattr(
            MediaExtractService, "_api_key", staticmethod(lambda cfg, provider_name: "test-key")
        )
        monkeypatch.setattr(
            "app.services.media_access_service.resolve_media_settings",
            lambda session: _voice_settings(voice_degraded_model="whisper-cheap"),
        )

        captured = {}

        def fake_post(data, *, filename, mime_type, fields, api_key, timeout):
            captured["fields"] = fields
            return {"text": "check stock please", "language": "en"}

        monkeypatch.setattr(
            "app.services.media_extract.transcribe._post_transcription", fake_post
        )

        outcome = MediaExtractService(db).extract(job)

        assert captured["fields"]["model"] == "whisper-cheap"
        # And the ledger records what was actually used, not what was configured
        # as standard - the cost attribution is the whole point of the column.
        assert outcome.model == "whisper-cheap"
        db.refresh(usage)
        assert usage.model == "whisper-cheap"


# --------------------------------------------------------------------------- #
# An abandoned extraction does not annotate the ledger (PLAN 16.5)            #
# --------------------------------------------------------------------------- #


def test_spend_after_a_timeout_is_logged_and_not_stamped_on_a_failed_row(caplog):
    """The orphaned thread outlives `_run_bounded`'s join, finishes its provider
    call, and used to write token counts onto a row the task had already marked
    `failed` - annotating it as a success it was not, while the spend itself was
    invisible."""
    import logging

    from app.services.media_extract.service import MediaExtractionOutcome

    with blank_session() as db:
        usage = _seed_usage(db, "image")
        from app.models.media import MediaExtractionJob

        job_row = MediaExtractionJob(
            id=str(uuid.uuid4()),
            usage_id=usage.id,
            status="failed",  # the task gave up on the wait
            modality="image",
            tier="standard",
            error="Extraction timed out after 45s",
        )
        db.add(job_row)
        db.commit()

        job = MediaJobInput(
            job_id=job_row.id,
            modality="image",
            tier="standard",
            media_url=None,
            mime_type=None,
            caption=None,
            usage_id=usage.id,
        )
        outcome = MediaExtractionOutcome(
            result={}, provider="openai", model="gpt-4o",
            prompt_tokens=2963, completion_tokens=180,
        )

        with caplog.at_level(logging.WARNING):
            MediaExtractService(db)._stamp_usage_cost(job, outcome)

        db.refresh(usage)
        assert usage.model is None, "a row the task failed must not read as a success"
        assert usage.prompt_tokens is None
        # The spend still happened, so it must be visible somewhere.
        assert any("2963" in record.getMessage() for record in caplog.records)
        assert any("gpt-4o" in record.getMessage() for record in caplog.records)


def test_a_still_running_job_stamps_normally(caplog):
    """The normal path: `_stamp_usage_cost` runs BEFORE the task writes
    `completed`, so the status it sees is `running` and nothing is skipped."""
    from app.services.media_extract.service import MediaExtractionOutcome

    with blank_session() as db:
        usage = _seed_usage(db, "image")
        from app.models.media import MediaExtractionJob

        job_row = MediaExtractionJob(
            id=str(uuid.uuid4()),
            usage_id=usage.id,
            status="running",
            modality="image",
            tier="standard",
        )
        db.add(job_row)
        db.commit()

        MediaExtractService(db)._stamp_usage_cost(
            MediaJobInput(
                job_id=job_row.id,
                modality="image",
                tier="standard",
                media_url=None,
                mime_type=None,
                caption=None,
                usage_id=usage.id,
            ),
            MediaExtractionOutcome(
                result={}, provider="openai", model="gpt-4o",
                prompt_tokens=2963, completion_tokens=180,
            ),
        )

        db.refresh(usage)
        assert usage.model == "gpt-4o"
        assert usage.prompt_tokens == 2963


# --------------------------------------------------------------------------- #
# Provider resolution for the image lane, Gemini included                      #
# --------------------------------------------------------------------------- #


def _media_settings(db, **overrides):
    """The resolved settings for this blank schema, with the image lane fields
    overridden - the settings page's own job, done without a request."""
    from dataclasses import replace

    from app.services.media_access_service import resolve_media_settings

    return replace(resolve_media_settings(db), **overrides)


def _seed_ai_config(db, **columns):
    from app.models.ai_assistant import AIAssistantConfig

    row = AIAssistantConfig(**columns)
    db.add(row)
    db.commit()
    return row


def test_image_lane_on_gemini_uses_the_gemini_key_column_and_its_own_default_model():
    """Selecting Gemini with no model named must not fall into the Anthropic
    default, and must read the dedicated Gemini key rather than the primary."""
    from app.services.llm_provider import GeminiProvider

    with blank_session() as db:
        _seed_ai_config(
            db,
            provider="openai",
            model="",
            api_key_ciphertext="ZZT-openai-key",
            gemini_api_key_ciphertext="ZZT-gemini-key",
        )

        settings = _media_settings(
            db, image_provider="gemini", image_model=None, image_degraded_model=None
        )
        provider, provider_name, model_name = MediaExtractService(
            db
        )._resolve_image_provider(None, settings)

        assert isinstance(provider, GeminiProvider)
        assert provider_name == "gemini"
        assert model_name == "gemini-2.5-flash"
        assert provider.api_key == "ZZT-gemini-key"


def test_image_lane_on_gemini_honours_an_explicit_model_and_the_degraded_tier():
    with blank_session() as db:
        _seed_ai_config(db, provider="openai", gemini_api_key_ciphertext="ZZT-gemini-key")

        settings = _media_settings(
            db,
            image_provider="gemini",
            image_model="gemini-2.5-pro",
            image_degraded_model="gemini-2.5-flash-lite",
        )
        service = MediaExtractService(db)

        assert service._resolve_image_provider(None, settings)[2] == "gemini-2.5-pro"
        assert (
            service._resolve_image_provider("degraded", settings)[2]
            == "gemini-2.5-flash-lite"
        )


def test_image_lane_on_gemini_borrows_the_primary_key_only_when_the_assistant_is_gemini():
    from app.services.llm_provider import GeminiProvider

    with blank_session() as db:
        _seed_ai_config(db, provider="gemini", model="", api_key_ciphertext="ZZT-primary-key")

        settings = _media_settings(
            db, image_provider="gemini", image_model=None, image_degraded_model=None
        )
        provider, _, _ = MediaExtractService(db)._resolve_image_provider(None, settings)

        assert isinstance(provider, GeminiProvider)
        assert provider.api_key == "ZZT-primary-key"


def test_image_lane_on_gemini_falls_back_to_the_env_key(monkeypatch):
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "gemini_api_key", "ZZT-env-gemini-key", raising=False)
    with blank_session() as db:
        settings = _media_settings(
            db, image_provider="gemini", image_model=None, image_degraded_model=None
        )
        provider, _, _ = MediaExtractService(db)._resolve_image_provider(None, settings)
        assert provider.api_key == "ZZT-env-gemini-key"


def test_image_lane_on_gemini_never_sends_another_providers_key_to_google(monkeypatch):
    """An OpenAI-configured assistant with no Gemini key must say so, not post
    the OpenAI key to Google and surface the 400 as a Gemini outage."""
    from app.config import settings as app_settings
    from app.services.media_extract.service import MediaExtractionError

    monkeypatch.setattr(app_settings, "gemini_api_key", None, raising=False)
    with blank_session() as db:
        _seed_ai_config(db, provider="openai", api_key_ciphertext="ZZT-openai-key")

        settings = _media_settings(
            db, image_provider="gemini", image_model=None, image_degraded_model=None
        )
        with pytest.raises(MediaExtractionError) as excinfo:
            MediaExtractService(db)._resolve_image_provider(None, settings)
        # The lane can run on a different provider than the assistant, so the
        # message names WHICH key is missing rather than sending an admin to
        # look at one that is already set.
        message = str(excinfo.value)
        assert "'gemini'" in message
        assert "No API key is configured" in message
        assert "System > AI Assistant" in message


def test_image_lane_missing_key_message_names_the_provider_it_needed(monkeypatch):
    from app.config import settings as app_settings
    from app.services.media_extract.service import MediaExtractionError

    monkeypatch.setattr(app_settings, "openai_api_key", None, raising=False)
    with blank_session() as db:
        settings = _media_settings(
            db, image_provider="openai", image_model=None, image_degraded_model=None
        )
        with pytest.raises(MediaExtractionError) as excinfo:
            MediaExtractService(db)._resolve_image_provider(None, settings)
        assert "'openai'" in str(excinfo.value)


def test_image_lane_default_model_per_provider_is_unchanged_for_openai_and_anthropic():
    with blank_session() as db:
        _seed_ai_config(
            db,
            provider="openai",
            model="",
            api_key_ciphertext="ZZT-openai-key",
            anthropic_api_key_ciphertext="ZZT-anthropic-key",
        )
        service = MediaExtractService(db)

        openai_settings = _media_settings(
            db, image_provider="openai", image_model=None, image_degraded_model=None
        )
        anthropic_settings = _media_settings(
            db, image_provider="anthropic", image_model=None, image_degraded_model=None
        )

        assert service._resolve_image_provider(None, openai_settings)[2] == "gpt-4o"
        assert (
            service._resolve_image_provider(None, anthropic_settings)[2]
            == "claude-sonnet-4-6"
        )
