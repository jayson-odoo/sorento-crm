"""Media intake INSIDE the chatbot turn (PLAN-chatbot-media-into-turn.md, S2).

A photo or voice note attached to an inbound message used to leave `run_turn`
entirely - `sub-media-intake` (n8n) decided, metered, extracted and patched the
transcript back onto the message BEFORE `/chat/turn` ever ran, so the turn engine
never touched a `MediaProcessRequest` at all. That is gone: this module runs the
SAME decide/meter/enqueue/wait pipeline `/external/media/process` runs
(`app.api.v1.external.media._decide_meter_record_and_enqueue`, reused verbatim,
never re-implemented), from inside `engine.py::_run_stages`, in the no-DB-session
window the parser call already uses.

`detect()` is a pure, envelope-only predicate - the same shape n8n's own
`detect-media` node tested. `run()` does the real work: one short session to
decide+meter+enqueue (mirrors `/external/media`'s own fast path), then a
synchronous poll (the sync twin of that route's `_await_job`, since the engine is
not async) bounded by `media_sync_wait_seconds`.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from app.services.chatbot import jsc
from app.services.media_extract import wording

# The attachment `type` values this step reads, mapped to the ledger's own modality
# vocabulary (`image | voice` - `ContactMediaUsage.modality`). `voice`/`ptt` are
# WhatsApp's own alternate names for a voice note (review round S7 - n8n's
# `detect-media` node reads both). A document, a video, or a sticker falls through
# unchanged regardless of url: the caption still reaches the parser via
# `build_latest_user_message`'s existing `attachment.description` fallback (AC-1804).
_ATTACHMENT_KIND_TO_MODALITY = {"image": "image", "audio": "voice", "voice": "voice", "ptt": "voice"}

TERMINAL_STATUSES = ("completed", "failed")

# How often the synchronous wait re-reads the job row. Mirrors
# `external/media.py::_POLL_INTERVAL_SECONDS` / `console_service._MEDIA_POLL_
# INTERVAL_SECONDS` - short enough not to pad a fast extraction, long enough not
# to spin. Security review item 7: 0.5s (was 0.25s) - this poll runs on a request
# thread inside `/chat/turn`, not a background worker, so halving how often it
# spins matters for how many of those threads one slow extraction can pin.
POLL_INTERVAL_SECONDS = 0.5

# Security review item 7: an in-turn synchronous wait blocks a REQUEST thread, not a
# background one - unlike `/external/media/process`'s own wait, which is this same
# pipeline's `_await_job` on a route the caller expects to be async. Bounded so a
# burst of media turns cannot pin every request thread on a slow provider at once;
# a turn that cannot acquire a slot immediately takes the SAME timeout arm a real
# wait timeout takes ("I could not read that photo in time...") rather than queueing
# behind the ones already waiting. A constant, not a setting - no measurement yet
# justifies making it operator-tunable (see PRINCIPLES.md "simplest thing").
_CONCURRENT_WAIT_LIMIT = 8
_wait_slots = threading.BoundedSemaphore(_CONCURRENT_WAIT_LIMIT)

# AC-1814: the sentence when the job outlives the sync wait. Two words differ by
# modality; everything else is the plan's own wording, verbatim.
_TIMEOUT_SENTENCE = {
    "image": "I could not read that photo in time. Please send it again or type the codes.",
    "voice": "I could not listen to that voice note in time. Please send it again or type your message.",
}

# AC-1819: capped at 160 characters with an ellipsis.
_VOICE_PREFIX_MAX_CHARS = 160


@dataclass
class MediaIntakeOutcome:
    """What the intake step decided, for the engine to act on and trace.

    `stops_here` is true for every denial, failure and timeout (AC-1810 to
    AC-1814): the turn never reaches the parser and closes on this outcome
    alone. `False` means intake completed and `rendered_text` is what the
    parser should read instead of the envelope's own text.
    """

    modality: str
    decision: str
    status: str  # "completed" | "failed" | "pending"
    stops_here: bool
    turn_status: str = "done"  # "done" (an answered denial) | "failed" (broke)
    reply_text: str | None = None
    rendered_text: str | None = None
    job_id: str | None = None
    elapsed_ms: int = 0
    result: dict[str, Any] = field(default_factory=dict)
    notices: list[dict[str, Any]] = field(default_factory=list)
    attachment_id: str | None = None
    attachment_error: str | None = None
    max_entities: int = 10
    # The extraction job's OWN error string (`MediaExtractionJob.error`), never shown
    # to the customer - `reply_text` is the friendly wording for that. Read by the
    # console's diagnostic `media_error` field only (`console_service.py`); a real
    # WhatsApp turn has no equivalent surface and never reads this.
    extraction_error: str | None = None


def _modality_of(attachment: dict[str, Any]) -> str | None:
    """`attachment`'s modality by `type`, falling back to a `mimeType` prefix the same
    way n8n's own `detect-media` node does (review round S7) - a caller that sends the
    right mime but an unexpected/missing `type` string still gets intaked. A `sticker`
    is excluded from the mime fallback on purpose: it is never this step's concern
    even when Respond.io happens to attach an `image/webp` mime to one.
    """
    attachment_type = jsc.get(attachment, "type")
    modality = _ATTACHMENT_KIND_TO_MODALITY.get(attachment_type)
    if modality:
        return modality
    if attachment_type == "sticker":
        return None
    mime = (jsc.js_string(jsc.get(attachment, "mimeType")) or "").lower()
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("audio/"):
        return "voice"
    return None


def detect(inner_message: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """Whether `inner_message` (`ctx.text.message.message`) carries media this
    step should intake, and the modality it carries.

    Returns `(modality, attachment)` - `modality` is `"image"` or `"voice"`,
    `attachment` is the raw, NON-empty attachment dict (with or without a `url`
    key - see `no_url_outcome()` for the no-url case). `None` when nothing here is
    this step's concern at all - a document, a video, a sticker, or a plain text
    message. The transition-window "already patched" signal is a SEPARATE, envelope-
    level check (`patched_upstream()` below, review round S3) - this function no
    longer reads an inner `_media` marker at all.

    An image/audio attachment with NO url is still detected here, deliberately
    (AC-107/H5, restated for this pipeline, captain ruling 23 Sep 2026): it is
    UNREADABLE, not a plain-text turn - `engine.py` tells this apart from a normal
    attachment by whether its own `url` is falsy, and answers with `no_url_outcome()`
    below instead of ever calling `run()` - no ledger row, no job, no worker call,
    since there is nothing to fetch.
    """
    attachment = jsc.get(inner_message, "attachment") or {}
    modality = _modality_of(attachment)
    if modality:
        return modality, attachment
    return None


def patched_upstream(envelope: Any) -> str | None:
    """AC-1805, restated (review round S3 + security item 4): n8n's OWN media
    pipeline sometimes still runs UPSTREAM of `/chat/turn` during the cutover window
    and hands this route an envelope whose top-level `media` key already carries what
    it decided - `{envelope: {..., message, media: <patched item>}}` - rather than
    leaving that decision for this module to make.

    The old reading of AC-1805 (an inner `_media` marker nested inside the message,
    handled through the SAME `run()` call as a live attachment) double-metered a
    message n8n's own pipeline had already decided, metered and recorded once itself.
    The correct rule is simpler: `envelope.media` present means NO intake runs here at
    all - no `decide_and_record`, no job, nothing added to the ledger - because
    upstream already did every part of that job. Returns the modality n8n's own patch
    carried (`envelope.media._media.modality`), or `None` on every other envelope.
    """
    media = getattr(envelope, "media", None)
    if not isinstance(media, dict):
        return None
    marker = media.get("_media")
    if not isinstance(marker, dict):
        return None
    modality = marker.get("modality")
    return "image" if modality == "image" else "voice" if modality == "voice" else None


def no_url_outcome(modality: str) -> MediaIntakeOutcome:
    """AC-107/H5, restated for this pipeline (captain ruling 23 Sep 2026): an
    image/audio attachment that DECLARES its type but carries no url never
    reaches decide/meter/enqueue - there is nothing to fetch, so no ledger row,
    no job, no worker call. Same terminal shape as a completed job that failed
    the extraction (AC-1813): `media_denied`, turn failed, Retry.
    """
    return MediaIntakeOutcome(
        modality=modality,
        decision="no_url",
        status="failed",
        stops_here=True,
        turn_status="failed",
        reply_text=wording.nothing_read() if modality == "image" else wording.voice_unclear(),
    )


def _build_request(
    *,
    respond_io_id: str,
    message_id: str | None,
    modality: str,
    attachment: dict[str, Any],
    caption: str | None,
    turn_id: str,
    source: str = "chat-turn",
):
    from app.schemas.external.media import MediaProcessRequest

    duration_ms = jsc.get(attachment, "duration")
    size = jsc.get(attachment, "size")
    return MediaProcessRequest(
        respond_io_id=respond_io_id,
        message_id=message_id or f"no-message-id-{turn_id}",
        modality=modality,
        media_url=jsc.js_string(jsc.get(attachment, "url")) if jsc.truthy(jsc.get(attachment, "url")) else "",
        mime_type=jsc.js_string(jsc.get(attachment, "mimeType")) or None,
        caption=caption or None,
        duration_ms=int(duration_ms) if isinstance(duration_ms, (int, float)) else None,
        bytes=int(size) if isinstance(size, (int, float)) else None,
        turn_id=str(turn_id),
        # `source` (review round, note a): "console" tells `_store_media_bytes` this
        # job's bytes are ALREADY stored under `chatbot-console/` by
        # `console_service._upload_console_media`, so it must not store a second copy.
        context={"source": source},
    )


def _poll(job_id: str, timeout_seconds: float, session_factory) -> dict[str, Any] | None:
    """Wait for the worker, bounded - `None` on timeout, never an exception.

    The sync twin of `external/media.py::_await_job`: the engine is not async,
    so this blocks the thread rather than the event loop, which is the same
    trade `console_service._poll_media_job` (retired by this change, S2's
    "one path") already made. A fresh session per read, never the caller's:
    that one may be mid-transaction, and re-reading a row another process is
    writing through it would only ever see this transaction's own snapshot.
    """
    from app.models.media import MediaExtractionJob

    deadline = time.monotonic() + timeout_seconds
    while True:
        db = session_factory()
        try:
            row = db.query(MediaExtractionJob).filter(MediaExtractionJob.id == job_id).first()
            if row is not None and row.status in TERMINAL_STATUSES:
                return {"status": row.status, "result": row.result, "error": row.error}
        finally:
            db.close()
        if time.monotonic() >= deadline:
            return None
        time.sleep(POLL_INTERVAL_SECONDS)


def await_existing_job(job_id: str, *, timeout_seconds: float, session_factory) -> str | None:
    """The same bounded wait `run` takes, on a job that already exists: its terminal
    status, or None when it outlived the wait (or every wait slot is taken).

    For the send-order pre-step (issue #1262): a photo n8n is still extracting is only
    answered ahead once it has actually been read.
    """
    if not _wait_slots.acquire(blocking=False):
        return None
    try:
        snapshot = _poll(job_id, timeout_seconds, session_factory)
    finally:
        _wait_slots.release()
    return snapshot["status"] if snapshot is not None else None


def run(
    *,
    respond_io_id: str,
    message_id: str | None,
    modality: str,
    attachment: dict[str, Any],
    caption: str | None,
    turn_id: str,
    session_factory,
    source: str = "chat-turn",
) -> MediaIntakeOutcome:
    """Decide, meter, record, enqueue and (bounded) wait - the real pipeline,
    called from inside the turn instead of from n8n.

    No DB session is held across the wait (AC-1803): the fast path opens and
    closes its own short session (mirroring `/external/media`'s own
    `_decide_meter_record_and_enqueue`, reused verbatim so the gate/quota/burst
    logic that already has its own test suite keeps running for real), and the
    poll below opens a fresh one per read.
    """
    from app.api.v1.external.media import _decide_meter_record_and_enqueue
    from app.services.media_access_service import resolve_media_settings

    started = time.perf_counter()
    request = _build_request(
        respond_io_id=respond_io_id,
        message_id=message_id,
        modality=modality,
        attachment=attachment,
        source=source,
        caption=caption,
        turn_id=turn_id,
    )
    db = session_factory()
    try:
        fast = _decide_meter_record_and_enqueue(db, request)
        # Read alongside the decision, on the same still-open session: the reply
        # prefix's truncated-note (AC-1818/AC-1821) needs the CAP by number, which
        # the job's own result only reports as a bool.
        max_entities = resolve_media_settings(db).max_entities
    finally:
        db.close()

    elapsed_ms = int((time.perf_counter() - started) * 1000)

    if fast.job_id is None:
        # AC-1810/AC-1811/AC-1812: denied_gate, denied_quota, denied_duration, or
        # denied_burst - accepted=False, nothing queued. The reply is whichever
        # notice the decision produced, verbatim (never recomposed here): empty
        # when there is none, which is exactly the silent burst-repeat arm.
        reply_text = " ".join(n.get("text") or "" for n in fast.notices).strip()
        return MediaIntakeOutcome(
            modality=modality,
            decision=fast.decision,
            status="failed",
            stops_here=True,
            turn_status="done",
            reply_text=reply_text,
            job_id=None,
            elapsed_ms=elapsed_ms,
            notices=fast.notices,
        )

    # Always a FRESH read, never `fast.job_status`/`fast.job_result` - those were
    # captured off the pre-enqueue ORM object, and `_enqueue`'s own commit can leave
    # it holding a stale snapshot from before the worker (or, in a test harness that
    # runs the "queue" inline and synchronously, an already-finished extraction)
    # wrote its result. `_poll`'s first read is a plain query on its own session, so
    # an already-terminal job returns on the very first iteration - no real latency
    # added over trusting the snapshot, and no staleness either.
    #
    # Bounded (security review item 7): this wait blocks a REQUEST thread, not a
    # background one. A burst past `_CONCURRENT_WAIT_LIMIT` concurrent waits takes
    # the timeout arm immediately rather than queueing behind the ones already
    # holding a slot.
    if _wait_slots.acquire(blocking=False):
        try:
            snapshot = _poll(fast.job_id, fast.sync_wait_seconds, session_factory)
        finally:
            _wait_slots.release()
    else:
        snapshot = None

    if snapshot is None:
        # AC-1814: outlived the wait. The job keeps running; its later completion
        # sends nothing (nobody is waiting on it any more).
        return MediaIntakeOutcome(
            modality=modality,
            decision=fast.decision,
            status="pending",
            stops_here=True,
            turn_status="failed",
            reply_text=_TIMEOUT_SENTENCE.get(modality, _TIMEOUT_SENTENCE["image"]),
            job_id=fast.job_id,
            elapsed_ms=elapsed_ms,
        )

    if snapshot["status"] == "failed":
        # AC-1813.
        reply_text = wording.nothing_read() if modality == "image" else wording.voice_unclear()
        return MediaIntakeOutcome(
            modality=modality,
            decision=fast.decision,
            status="failed",
            stops_here=True,
            turn_status="failed",
            reply_text=reply_text,
            job_id=fast.job_id,
            elapsed_ms=elapsed_ms,
            extraction_error=snapshot.get("error"),
        )

    result = snapshot.get("result") or {}
    # `result` is the LIVE extractor's own body (`build_image_result_body` /
    # `build_voice_result_body`, `media_extract/service.py`), whatever a real
    # worker or (in a test harness) a stubbed `run_media_extraction` wrote into
    # `job.result` - never a value this module invents. `rendered_text` should
    # never be null here after the 23 Sep service.py fix (it is ALWAYS rendered
    # whenever there is a caption or an entity to join), but the fallback below
    # still joins the raws directly rather than ever handing the parser an empty
    # string - belt, not the buckle, for a result shape this module does not own.
    entities = result.get("entities") or []
    raws_fallback = ", ".join(
        e.get("raw") for e in entities if isinstance(e, dict) and e.get("raw")
    )
    rendered_text = (
        result.get("rendered_text") or result.get("transcript") or raws_fallback or ""
    )
    return MediaIntakeOutcome(
        modality=modality,
        decision=fast.decision,
        status="completed",
        stops_here=False,
        rendered_text=rendered_text,
        job_id=fast.job_id,
        elapsed_ms=elapsed_ms,
        result=result,
        notices=fast.notices,
        attachment_id=result.get("attachment_id"),
        attachment_error=result.get("attachment_error"),
        max_entities=max_entities,
    )


# --------------------------------------------------------------------------- #
# Reply prefix (AC-1817 to AC-1821) - one line, media turns only, prepended
# once wherever the turn's reply is sealed.
# --------------------------------------------------------------------------- #


def reply_prefix(outcome: MediaIntakeOutcome) -> str:
    """"I read A, B and C from that photo." / "I heard: <transcript>" - never a
    count, never "+N more" (owner ruling Q2)."""
    if outcome.modality == "voice":
        transcript = (outcome.rendered_text or "").strip()
        if len(transcript) > _VOICE_PREFIX_MAX_CHARS:
            transcript = transcript[:_VOICE_PREFIX_MAX_CHARS] + "..."
        return f"I heard: {transcript}"

    entities = outcome.result.get("entities") or []
    raws = [e.get("raw") for e in entities if isinstance(e, dict) and e.get("raw")]
    prefix = f"I read {wording.join_phrase(raws)} from that photo." if raws else wording.nothing_read()
    if outcome.result.get("truncated"):
        prefix = f"{prefix} {wording.truncated_note(outcome.max_entities)}"
    return prefix


def notice_texts(outcome: MediaIntakeOutcome) -> list[str]:
    """AC-1815: the accept-time notices (e.g. `warn_80`) an answered media turn's
    reply appends, once."""
    return [n.get("text") or "" for n in outcome.notices if n.get("text")]
