"""In-app chatbot console: one dry-run turn, in process (Slice D final, chatbot growth r1).

`run_console_turn` is what `POST /api/v1/system/chatbot/console/turn` calls: it borrows the
contact's most recent stored envelope (a turn reads that shape at `received`, and an
invented one fails there for a field it does not carry - the same reason
`scripts/chatbot_console_check.py::_base_envelope` borrows one instead of building one from
nothing), stamps this turn's text onto it, marks it a DRY RUN two ways (`is_test=True`,
`test_run_id=run_id` - D14: zero writes outside `chatbot.turns`), and calls `run_turn` IN
PROCESS - no HTTP hop, because the caller (the FastAPI route) and the engine are the same
process here. The ad-hoc script instead posts to a URL, because ITS whole point is grading
whichever backend PROCESS is actually serving traffic, local or remote - an in-process call
there would silently stop testing the thing it exists to test.

**Deliberately NOT shared code with `scripts/chatbot_console_check.py`.** The two modules'
shapes look alike - both borrow an envelope, both force the two lane switches on for one
call and restore them in a `finally`, both honour `previous_conversation_state` /
`prompt_overrides` - because both solve the same problem (a harness turn with no real
WhatsApp delivery), not because one wraps the other. `tests/chatbot/test_import_boundary.py`
(AC-002) does not list the script among the files allowed to import `app.services.chatbot`,
and that boundary is right for it: an in-process call would defeat the script's own stated
purpose ("a REAL turn through a REAL backend"). Folding the two together was considered and
rejected for that reason - see the coder's report on this change for where that is written
up. If the two ever need to agree on a THIRD behaviour, the shared piece belongs in
`contracts.py`, which both already read.

Every call flips `system_settings.chatbot_business_lane_enabled` and
`chatbot_completed_lanes` ON for the one turn and restores the PRIOR values in a `finally`,
the same rule the script's `_lanes_on` states: without it a turn whose branch is not in
`chatbot_completed_lanes` comes back with an empty reply (delegated to n8n), which would
grade the handoff rather than the answer - and a console with a permanently-empty reply
teaches nobody anything. Scoped to the single call, on a session of its own, never left
flipped for the next request even if the turn itself raises.
"""
from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.chatbot_turn import ChatbotTurn
from app.models.user import SystemSetting
from app.services.chatbot import run_turn
from app.services.chatbot.contracts import BRANCH_KINDS, TurnRequest
from app.services.error_handler import AppException

# S8a's own key (`ai_prompt_versions.name` for the chatbot's semantic parser), restated
# here rather than imported from `head.parser` for the same reason the script restates it:
# this is the module's own outward-facing constant, and `head.parser` is an internal one.
PARSER_PROMPT_KEY = "chatbot_semantic_parser"

# The two envelope fields excluded from `args_short` in the trace summary: neither is
# useful to an operator reading a console reply (an internal view flag and identifiers the
# reply already carries in its own shape), and `_diagnostics` is a debug bag the tool
# itself may attach. Mirrors the script's own `_trace_line` filter so the two present the
# same trace to a human either way it was run.
_TRACE_ARGS_DROPPED = ("view", "contact_id", "space_id", "_diagnostics")


class ConsoleContactUnknown(AppException):
    """No stored turn for this contact: there is no envelope shape to borrow."""

    def __init__(self, contact_respond_id: str) -> None:
        super().__init__(
            status_code=404,
            message="This contact has no chatbot turn to borrow a session from.",
            detail=(
                f"no chatbot.turns envelope exists yet for contact {contact_respond_id!r}. "
                "Send one real WhatsApp message from this contact first, or pick a "
                "different contact."
            ),
            code="CHATBOT_CONSOLE_NO_ENVELOPE",
        )


class ConsoleTurnResult:
    """What `run_console_turn` hands the route: exactly the shape `ConsoleTurnResponse`
    declares, kept as a plain object so the service stays free of the wire schema."""

    __slots__ = (
        "turn_id",
        "branch_kind",
        "reply_text",
        "quick_replies",
        "send_messages",
        "session_vars",
        "trace_summary",
        # Media (commit 2): all None on a plain text turn. `media_status` is one of
        # "pending" | "done" | "failed" only when a `media` attachment was sent.
        "media_status",
        "media_id",
        "media_text",
        "media_error",
    )

    def __init__(self, **kwargs: Any) -> None:
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))


def _borrow_envelope(db: Session, contact_respond_id: str) -> dict[str, Any]:
    """The contact's most recent stored envelope, as the shape to borrow.

    Raises rather than inventing one: a hand-built envelope missing a field the engine
    reads at `received` fails there, and a console whose failures are its own bug is worse
    than no console. The phone is filled in from `respond_contacts` when the borrowed
    envelope carries none, the same backfill `chatbot_console_check.py::_base_envelope`
    does - the escalation lane's assignee read is a 400 without it.

    **Through the ORM model, not raw SQL naming the `chatbot` schema.** A schema-qualified
    `FROM chatbot.turns` bypasses `search_path` entirely, so under a test's translated
    scratch schema (`tests/_pg_fixture.py`) it would silently read the REAL, shared
    `chatbot.turns` table instead of the isolated one - the same real-DB-read finding
    `test_chat_turn_endpoint.py::_turns_count` documents. `ChatbotTurn.__table_args__`
    carries `schema="chatbot"` as an ORM construct, which IS translated correctly.
    """
    row = (
        db.query(ChatbotTurn)
        .filter(ChatbotTurn.contact_respond_id == str(contact_respond_id), ChatbotTurn.envelope.isnot(None))
        .order_by(ChatbotTurn.created_at.desc())
        .first()
    )
    if row is None:
        raise ConsoleContactUnknown(contact_respond_id)
    phone = db.execute(
        sa_text("SELECT phone_number FROM respond_contacts WHERE respond_io_id = :c"),
        {"c": str(contact_respond_id)},
    ).scalar()
    envelope = dict(row.envelope)
    stored = envelope.get("contact") or {}
    if not stored.get("phone") and phone:
        envelope["contact"] = {**stored, "phone": phone}
    return envelope


def _build_envelope(
    base: dict[str, Any],
    *,
    contact_respond_id: str,
    message_text: str,
    run_id: str,
    session_vars: dict[str, Any] | None,
    prompt_version_id: str | None,
) -> dict[str, Any]:
    """The borrowed envelope with this turn's words in it. Never mutates `base`.

    Mirrors `chatbot_console_check.py::_envelope_for` field for field: same `is_test` /
    `test_run_id` markers (D14), the same `previous_conversation_state` MEMBERSHIP rule
    (`session_vars=None` omits the key so the engine falls back to the contact's stored
    session; `session_vars={}` says "this contact remembers nothing", which is what a
    console Reset sends), and the same `prompt_overrides` harness key the Prompts screen's
    "Run a turn" button uses (dry-run only by construction, `engine._prompt_override`).
    """
    envelope = json.loads(json.dumps(base))
    envelope["contact"] = {**(envelope.get("contact") or {}), "id": str(contact_respond_id)}
    envelope.setdefault("message", {})
    envelope["message"]["contact"] = {"id": str(contact_respond_id)}
    inner = envelope["message"].setdefault("message", {})
    inner["contactId"] = str(contact_respond_id)
    inner["messageId"] = f"console-{uuid.uuid4().hex[:12]}"
    inner["message"] = {"type": "text", "text": message_text}
    envelope["message"]["event_type"] = "message.received"
    envelope["is_test"] = True
    envelope["test_run_id"] = run_id
    envelope["ingress"] = "console"
    envelope["shadow_of"] = None
    if session_vars is not None:
        envelope["previous_conversation_state"] = session_vars
    else:
        envelope.pop("previous_conversation_state", None)
    if prompt_version_id:
        envelope["prompt_overrides"] = {PARSER_PROMPT_KEY: str(prompt_version_id)}
    else:
        envelope.pop("prompt_overrides", None)
    return envelope


def _read_switches(db: Session) -> tuple[bool, Any]:
    row = db.query(SystemSetting).first()
    if row is None:
        return False, []
    return bool(row.chatbot_business_lane_enabled), row.chatbot_completed_lanes


def _write_switches(db: Session, enabled: bool, lanes: Any) -> None:
    row = db.query(SystemSetting).first()
    if row is None:
        return
    row.chatbot_business_lane_enabled = enabled
    row.chatbot_completed_lanes = list(lanes or [])
    db.commit()


@contextmanager
def _lanes_on() -> Iterator[None]:
    """Business lane on and every branch answered FOR THIS ONE CALL, restored after.

    On a FRESH session per read/write, each closed immediately - never one session held
    open across the `yield`. `run_turn` opens and closes many of its own sessions on the
    same underlying test connection (`tests/_pg_fixture.py`'s savepoint-per-`Session`
    scheme); a session left idle-but-open here for the whole turn interleaves its
    save point with theirs and can lose a write the turn made, discovered when the D14
    zero-writes test for this endpoint undercounted `chatbot.turns` by exactly the row this
    context manager's own held-open session's savepoint had shadowed. Same restore rule as
    `chatbot_console_check.py::_lanes_on` otherwise, without that script's production
    refusal: this endpoint is gated by `system.chat_history.view` rather than an operator's
    own shell, so the permission system is what decides who may run a console turn at all.
    """
    db = SessionLocal()
    try:
        before_enabled, before_lanes = _read_switches(db)
    finally:
        db.close()
    db = SessionLocal()
    try:
        _write_switches(db, True, list(BRANCH_KINDS))
    finally:
        db.close()
    try:
        yield
    finally:
        db = SessionLocal()
        try:
            _write_switches(db, before_enabled, before_lanes or [])
        finally:
            db.close()


def _next_state(body: dict[str, Any]) -> dict[str, Any] | None:
    """What the NEXT turn remembers: the sealed reply's own `variables`."""
    patch = (body.get("reply") or {}).get("session_patch")
    if not isinstance(patch, dict):
        patch = body.get("session_patch")
    if not isinstance(patch, dict):
        return None
    variables = patch.get("variables")
    return variables if isinstance(variables, dict) else patch


def _customer_texts(body: dict[str, Any]) -> tuple[str, list[str]]:
    """`(reply_text, send_messages)`: the primary bubble, then any EXTRA ones.

    `actions` carries every `send_message` the turn composed, and on most lanes the first
    one is the SAME text as `reply.text` (the tail builds one from the other) - rendering
    both would show a customer's answer twice. The escalation lane is the exception
    (`includeResponse: false`): `reply.text` is empty and the two sentences live only in
    `actions`, so nothing is dropped there.
    """
    reply = body.get("reply") or {}
    reply_text = reply.get("text") or ""
    action_texts = [
        a.get("text")
        for a in (body.get("actions") or [])
        if isinstance(a, dict) and a.get("kind") == "send_message" and isinstance(a.get("text"), str) and a.get("text")
    ]
    if reply_text and action_texts and action_texts[0] == reply_text:
        action_texts = action_texts[1:]
    return reply_text, action_texts


def _quick_replies(body: dict[str, Any]) -> list[str]:
    """AC-507: `quick_replies` is a comma-joined string or null on the wire, never a list."""
    raw = (body.get("reply") or {}).get("quick_replies")
    if not raw or not isinstance(raw, str):
        return []
    return [chip.strip() for chip in raw.split(",") if chip.strip()]


def _trace_summary(db: Session, turn_id: str | None) -> dict[str, Any]:
    """The tool call, the cross-domain rungs and the dropped reveals, off the persisted
    trace (`TurnTrace.persisted()` interleaves stage records with the `tool` / `crossdomain`
    / `reveals` events `trace.add` writes). Same source `chatbot_console_check.py::
    _trace_line` reads for its one-line summary; this reshapes the same events for the
    console page's trace field instead of a printed string.
    """
    empty: dict[str, Any] = {
        "tool": None,
        "args_short": None,
        "crossdomain_rungs": [],
        "reveals_dropped": [],
    }
    if not turn_id:
        return empty
    # Through the ORM model, not raw SQL - see `_borrow_envelope`'s docstring for why a
    # schema-qualified `chatbot.turns` string is wrong under a test's translated schema.
    row = db.query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).first()
    events = [e for e in ((row.trace if row else None) or []) if isinstance(e, dict) and e.get("kind")]
    tool: str | None = None
    args_short: dict[str, Any] | None = None
    crossdomain_rungs: list[str] = []
    reveals_dropped: list[str] = []
    for event in events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if event["kind"] == "tool" and tool is None:
            tool = payload.get("name")
            args_short = {
                k: v for k, v in (payload.get("args") or {}).items() if k not in _TRACE_ARGS_DROPPED
            }
        elif event["kind"] == "crossdomain":
            crossdomain_rungs.append(str(payload.get("rung") or payload.get("tool") or ""))
        elif event["kind"] == "reveals":
            reveals_dropped.extend(str(d) for d in (payload.get("dropped") or []))
    return {
        "tool": tool,
        "args_short": args_short,
        "crossdomain_rungs": [r for r in crossdomain_rungs if r],
        "reveals_dropped": reveals_dropped,
    }


def _empty_trace_summary() -> dict[str, Any]:
    return {"tool": None, "args_short": None, "crossdomain_rungs": [], "reveals_dropped": []}


def run_console_turn(
    db: Session,
    *,
    contact_respond_id: str,
    text: str,
    session_vars: dict[str, Any] | None = None,
    prompt_version_id: str | None = None,
    run_id: str,
    media: dict[str, Any] | None = None,
) -> ConsoleTurnResult:
    """Run one dry-run turn for the in-app console page, in process.

    `db` is used only for the reads that never touch the engine's own sessions
    (borrowing the envelope, reading the trace back after, and - with `media` - the
    real media pipeline's ledger/job writes, section below). The engine opens and closes
    its own sessions around the turn, the same reason `/external/chat/turn` hands it
    `SessionLocal` rather than the request session.

    `media` (commit 2): `{kind, filename, mime, content_base64}`. Routes through
    `_run_console_media_turn`, which is the real `/external/media/process` decide-and-wait
    path, not a second extractor - see that function's own docstring for the shape and the
    D14 deviation it carries.
    """
    if media is not None:
        return _run_console_media_turn(
            db,
            contact_respond_id=contact_respond_id,
            caption=text,
            session_vars=session_vars,
            prompt_version_id=prompt_version_id,
            run_id=run_id,
            media=media,
        )

    base = _borrow_envelope(db, contact_respond_id)
    # Same rule `chat.py`'s `/turn` route states and applies before calling `run_turn`:
    # the read above left `db` mid-transaction, and holding that open for the whole turn
    # - which opens and closes several sessions of its OWN on `SessionLocal` - pins a
    # connection (and, under a test's shared-connection savepoint scheme, can shadow a
    # write one of those sessions made) for no reason once the read is done with.
    db.rollback()
    envelope_dict = _build_envelope(
        base,
        contact_respond_id=contact_respond_id,
        message_text=text,
        run_id=run_id,
        session_vars=session_vars,
        prompt_version_id=prompt_version_id,
    )
    envelope = TurnRequest(envelope=envelope_dict).envelope

    with _lanes_on():
        result = run_turn(envelope, session_factory=SessionLocal)
    body = result.as_dict()

    reply_text, send_messages = _customer_texts(body)
    return ConsoleTurnResult(
        turn_id=body.get("turn_id"),
        branch_kind=body.get("branch_kind"),
        reply_text=reply_text,
        quick_replies=_quick_replies(body),
        send_messages=send_messages,
        session_vars=_next_state(body),
        trace_summary=_trace_summary(db, body.get("turn_id")),
    )


# --------------------------------------------------------------------------- #
# Media (commit 2): image and voice through the REAL extractor.
#
# `POST /external/media/process` (`app/api/v1/external/media.py`,
# `documentation/plans/_archive/ideation/PLAN-chatbot-media-endpoint.md`) is the one place
# this codebase decides, meters, records and extracts inbound media - `decide_and_record`
# (gate, burst, quota, ledger), `enqueue_job` onto the `media` RQ queue, `process_media_
# extraction` (the real provider call, image or voice). The console calls the SAME three
# steps in process rather than growing a second extractor: no new prompt, no new schema,
# no new RQ task.
#
# **Deviation from D14, flagged rather than papered over.** Every OTHER console write is
# `chatbot.turns` only (`is_test=True`, zero writes elsewhere). Media cannot make that
# promise: `contact_media_usage` (the ledger) and `media_extraction_job` have no `is_test`
# column - that table shape is PLAN-chatbot-media-endpoint's, already shipped and reviewed
# before this slice existed, and adding one is a migration to an already-live feature, out
# of scope for a console page. A console media send therefore CONSUMES the picked contact's
# real monthly quota and writes a real ledger row, the same as if that contact had sent a
# WhatsApp photo. Acceptable for a manual testing tool used sparingly; stated here so it is
# a known trade-off, not a surprise.
#
# **No `attachments` row.** The real pipeline never writes one either - "No image storage.
# Bytes are fetched, sent to the model and dropped" (PLAN section 11). What DOES need
# solving is that the pipeline fetches media by URL (`job.media_url`, a respond.io CDN
# link), not by bytes, and a console upload arrives as base64 with nothing to link to - so
# the bytes are put through the SAME storage backend a live upload uses
# (`app/services/storage_router.py`, `STORAGE_DEFAULT_PROVIDER`), under a
# `chatbot-console/` prefix, to get a URL the extractor can fetch exactly as it would a
# real one. Nothing is inserted into `attachments`; the object is transient storage, not a
# tracked business record.
# --------------------------------------------------------------------------- #

# Console media never claims to BE a respond.io modality string. The real ledger's
# `modality` column is `image | voice` (`ContactMediaUsage`); the composer's own vocabulary
# is `image | audio` (matches the owner's ask, "image/voice", and the file-picker's own
# `accept` groups). Translated at the one seam that calls the real service.
_MODALITY_TO_LEDGER = {"image": "image", "audio": "voice"}

# How often the synchronous wait re-reads the job row. Mirrors `/external/media.py`'s own
# `_POLL_INTERVAL_SECONDS` - short enough not to pad a fast extraction, long enough not to
# spin. This route is a plain `def`, which Starlette already runs off the event loop in
# its own thread pool, so a blocking `time.sleep` here costs one worker thread for the
# wait's duration and never blocks another request the way it would inside `async def`.
_MEDIA_POLL_INTERVAL_SECONDS = 0.25


def _upload_console_media(*, kind: str, filename: str, mime: str, content_base64: str) -> str:
    """Decode and upload console media bytes, return the URL the extractor fetches from.

    Uses whichever provider `STORAGE_DEFAULT_PROVIDER` points at, the same call
    `app/api/v1/resources/attachments.py`'s upload route makes
    (`backend.upload_file(file_content=..., file_path=..., content_type=...)`), under a
    `chatbot-console/` prefix so a bucket listing can tell these apart from tracked
    attachments at a glance. A signed URL, not the bare CDN one: the extractor's fetch is
    an anonymous `httpx.get` with no auth header of its own, the same as it would carry
    for a real (already-public) respond.io CDN link.
    """
    import base64 as base64_mod

    from app.services.storage_router import cdn_base_url, default_provider, get_backend, resolve_signed_url

    raw = base64_mod.b64decode(content_base64)
    provider = default_provider()
    backend = get_backend(provider)
    ext = filename.rsplit(".", 1)[-1] if "." in filename else ("jpg" if kind == "image" else "webm")
    key = f"chatbot-console/{uuid.uuid4().hex}.{ext}"
    s3_key, _ = backend.upload_file(file_content=raw, file_path=key, content_type=mime)
    # `resolve_signed_url` takes the STORED path (the stable CDN url `cdn_base_url`
    # returns, the same shape `attachments.file_path` holds), not the bare key - see
    # `app/api/v1/resources/attachments.py::_resolve_attachment_file_path`.
    stored_path = cdn_base_url(provider, s3_key)
    url = resolve_signed_url(stored_path, provider=provider, expires_in=900)
    if not url:
        raise AppException(
            status_code=502,
            message="Could not prepare the attachment for reading.",
            detail=f"resolve_signed_url returned nothing for {provider}:{s3_key}",
            code="CHATBOT_CONSOLE_MEDIA_UPLOAD_FAILED",
        )
    return url


def _extracted_text(result: dict[str, Any] | None) -> str:
    """The one string that stands in for "what the customer said" - `rendered_text`
    (image) or `transcript` (voice), the same value the real spine patches into the turn
    upstream of `tf-message` (PLAN section 1.3). Falls back to whatever confirmation text
    the extraction produced, then to nothing: an extraction that read nothing distinguishing
    still degrades to the caption alone (PLAN section 4.5's "nothing extracted" row), which
    `_run_console_media_turn` applies by falling back to the caption when this is empty.
    """
    if not isinstance(result, dict):
        return ""
    return str(result.get("rendered_text") or result.get("transcript") or result.get("confirmation_message") or "")


def _poll_media_job(job_id: str, timeout_seconds: float) -> dict[str, Any] | None:
    """Wait for the worker, bounded - `None` on timeout, never an exception.

    A fresh session per read, like `/external/media.py::_read_job_snapshot`: the route's
    own session is mid-transaction by the time this runs, and re-reading a row another
    process is writing through it would only ever see this transaction's own snapshot.
    """
    import time as time_mod

    from app.models.media import MediaExtractionJob

    deadline = time_mod.monotonic() + timeout_seconds
    while True:
        db = SessionLocal()
        try:
            row = db.query(MediaExtractionJob).filter(MediaExtractionJob.id == job_id).first()
            if row is not None and row.status in ("completed", "failed"):
                return {"status": row.status, "result": row.result, "error": row.error}
        finally:
            db.close()
        if time_mod.monotonic() >= deadline:
            return None
        time_mod.sleep(_MEDIA_POLL_INTERVAL_SECONDS)


def _run_console_media_turn(
    db: Session,
    *,
    contact_respond_id: str,
    caption: str,
    session_vars: dict[str, Any] | None,
    prompt_version_id: str | None,
    run_id: str,
    media: dict[str, Any],
) -> ConsoleTurnResult:
    """Decide, meter, record and enqueue through the real media pipeline, wait
    `media_sync_wait_seconds`, then run the chatbot turn on the extracted text - the same
    order `POST /external/media/process` runs in (PLAN section 3.3), synchronous rather
    than `asyncio.to_thread` because this route is a plain `def`.
    """
    from app.services.media_access_service import (
        MediaRequest,
        _now_utc,
        decide_and_record,
        mark_usage_outcome,
        resolve_media_settings,
    )
    from app.services.queue_service import enqueue_job
    from app.tasks.media_tasks import MEDIA_QUEUE, process_media_extraction

    kind = media.get("kind") if media.get("kind") in ("image", "audio") else "image"
    modality = _MODALITY_TO_LEDGER[kind]
    media_url = _upload_console_media(
        kind=kind,
        filename=str(media.get("filename") or ""),
        mime=str(media.get("mime") or ""),
        content_base64=str(media.get("content_base64") or ""),
    )

    settings = resolve_media_settings(db)
    decision = decide_and_record(
        db,
        MediaRequest(
            respond_io_id=contact_respond_id,
            message_id=f"console-media-{uuid.uuid4().hex}",
            modality=modality,
            media_url=media_url,
            mime_type=str(media.get("mime") or ""),
            caption=caption or None,
            turn_id=run_id,
        ),
        settings=settings,
        now=_now_utc(),
    )
    db.commit()

    if not decision.accepted or decision.job is None:
        # denied_gate / denied_burst / denied_quota / denied_duration: nothing was
        # queued. Degrade to the caption alone when one was typed (PLAN 3.5's own
        # "failed extraction" rule, applied here since a refusal is the same kind of
        # "no extracted text" outcome from the turn's point of view); otherwise there is
        # nothing to answer and the console has to say so rather than go silent.
        if caption.strip():
            return run_console_turn(
                db,
                contact_respond_id=contact_respond_id,
                text=caption,
                session_vars=session_vars,
                prompt_version_id=prompt_version_id,
                run_id=run_id,
            )
        return ConsoleTurnResult(
            turn_id=None,
            branch_kind=None,
            reply_text="",
            quick_replies=[],
            send_messages=[],
            session_vars=None,
            trace_summary=_empty_trace_summary(),
            media_status="failed",
            media_id=None,
            media_text=None,
            media_error=f"This contact's media access refused the attachment ({decision.decision}).",
        )

    job_id = str(decision.job.id)
    try:
        rq_job = enqueue_job(
            process_media_extraction, job_id, queue_name=MEDIA_QUEUE, job_timeout=600, job_id=job_id,
        )
        decision.job.rq_job_id = getattr(rq_job, "id", None)
        db.commit()
    except Exception:  # noqa: BLE001 - a queue outage is a failed job, not a 500
        decision.job.status = "failed"
        decision.job.error = "Could not queue the extraction."
        mark_usage_outcome(db, decision.job.usage_id, "not_queued")
        db.commit()

    snapshot = _poll_media_job(job_id, settings.sync_wait_seconds)

    if snapshot is None:
        # Outlived the wait. The job keeps running; the FE polls
        # GET /console/media/{media_id} and sends a plain text turn once it resolves.
        return ConsoleTurnResult(
            turn_id=None,
            branch_kind=None,
            reply_text="",
            quick_replies=[],
            send_messages=[],
            session_vars=None,
            trace_summary=_empty_trace_summary(),
            media_status="pending",
            media_id=job_id,
            media_text=None,
            media_error=None,
        )

    if snapshot["status"] == "failed":
        if caption.strip():
            result = run_console_turn(
                db,
                contact_respond_id=contact_respond_id,
                text=caption,
                session_vars=session_vars,
                prompt_version_id=prompt_version_id,
                run_id=run_id,
            )
            result.media_status = "failed"
            result.media_id = job_id
            result.media_error = snapshot.get("error") or "Extraction failed."
            return result
        return ConsoleTurnResult(
            turn_id=None,
            branch_kind=None,
            reply_text="",
            quick_replies=[],
            send_messages=[],
            session_vars=None,
            trace_summary=_empty_trace_summary(),
            media_status="failed",
            media_id=job_id,
            media_text=None,
            media_error=snapshot.get("error") or "Extraction failed.",
        )

    extracted = _extracted_text(snapshot.get("result"))
    turn_text = extracted or caption
    result = run_console_turn(
        db,
        contact_respond_id=contact_respond_id,
        text=turn_text,
        session_vars=session_vars,
        prompt_version_id=prompt_version_id,
        run_id=run_id,
    )
    result.media_status = "done"
    result.media_id = job_id
    result.media_text = extracted or None
    result.media_error = None
    return result


class ConsoleMediaJobUnknown(AppException):
    """No such job - a stale poll, or a `media_id` that was never a job id."""

    def __init__(self, media_id: str) -> None:
        super().__init__(
            status_code=404,
            message="No such media job.",
            detail=f"no media_extraction_job row for id {media_id!r}",
            code="CHATBOT_CONSOLE_MEDIA_JOB_NOT_FOUND",
        )


def get_console_media_status(db: Session, media_id: str) -> dict[str, Any]:
    """`GET /console/media/{media_id}` - the poll the FE falls back to once a media
    turn's synchronous wait timed out. Safe to call repeatedly; no side effects.
    """
    from app.models.media import MediaExtractionJob

    try:
        row = db.query(MediaExtractionJob).filter(MediaExtractionJob.id == media_id).first()
    except Exception:  # noqa: BLE001 - a malformed id is a miss, not a 500
        db.rollback()
        row = None
    if row is None:
        raise ConsoleMediaJobUnknown(media_id)
    if row.status in ("queued", "running"):
        return {"status": "pending", "text": None, "error": None}
    if row.status == "failed":
        return {"status": "failed", "text": None, "error": row.error or "Extraction failed."}
    return {"status": "done", "text": _extracted_text(row.result) or None, "error": None}
