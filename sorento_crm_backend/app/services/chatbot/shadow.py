"""The shadow parse: the same message, read again by the version being trialled (AC-1027).

D10 says a new parser prompt is promoted by the OWNER, after watching it answer real turns
beside the live one. This module is that second read. When
`system_settings.chatbot_parser_shadow_version` names a version, every real turn also runs
the parser at that version and writes a SECOND `chatbot.turns` row:

    ingress = "shadow", shadow_of = <the live turn's message_id>, status = done,
    the parse in `trace`, response = null

and that is all it does. **It sends nothing, writes no session, opens no lane and raises no
escalation.** A shadow turn is an observation, and the whole value of the window is that
the customer cannot tell it is running.

**A shadow failure is a shadow ROW, not a silence.** The version may have been deleted, the
provider may refuse, the emission may not validate: each of those is exactly what the owner
is watching for, so it lands as a `failed` shadow row carrying the error rather than a log
line nobody reads. Nothing here can touch the live turn - it runs after the live row is
inserted, on its own session, and every exception is caught.

Fire-and-forget: on the worker when the turn engine is offloaded (the same `chat` queue the
live turn uses), in-process otherwise, because an install with no worker must still be able
to run a window.
"""
from __future__ import annotations

import logging
from typing import Any

from app.services.chatbot import trace as trace_mod
from app.services.chatbot.contracts import Envelope

logger = logging.getLogger(__name__)

# `<prompt key>@<version>`, which is what the settings screen stores and what an operator
# can read back. Deliberately not a uuid: the value is shown in a settings field and in the
# turn trace, and "chatbot_semantic_parser@18" says which prompt and which version of it
# without a lookup.
VERSION_SEPARATOR = "@"

# What the shadow row's own `message_id` is: the live one with this suffix. The unique index
# is `(contact_respond_id, message_id, attempt, is_test)` and carries no `ingress` column, so
# reusing the live id would collide with the very turn being shadowed.
MESSAGE_ID_SUFFIX = "-shadow"
MAX_MESSAGE_ID = 128


def shadow_message_id(live_message_id: Any) -> str | None:
    """The shadow row's `message_id`: the live one, suffixed, inside the column's width."""
    if not live_message_id:
        return None
    text = str(live_message_id)
    room = MAX_MESSAGE_ID - len(MESSAGE_ID_SUFFIX)
    return text[:room] + MESSAGE_ID_SUFFIX


def resolve_version_id(db: Any, configured: str) -> str:
    """The `ai_prompt_versions.id` the setting names, or raise saying why not.

    Accepts `"<prompt key>@<version>"`. RAISES rather than falling back to the published
    prompt: a window that silently shadowed the LIVE version would report perfect parity
    and mean nothing, which is worse than a visible row of failures.
    """
    from app.models.ai_prompt import AIPromptVersion
    from app.services.chatbot.head.parser import PROMPT_KEY

    name, _, version = str(configured).partition(VERSION_SEPARATOR)
    name = name.strip() or PROMPT_KEY
    version = version.strip()
    if not version.isdigit():
        raise ValueError(
            f"chatbot_parser_shadow_version {configured!r} is not '<prompt key>@<version>'"
        )
    row = (
        db.query(AIPromptVersion)
        .filter(AIPromptVersion.name == name, AIPromptVersion.version == int(version))
        .first()
    )
    if row is None:
        raise ValueError(f"no {name!r} prompt version {version} to shadow")
    return str(row.id)


def run_for(
    envelope: Envelope,
    *,
    session_factory: Any,
    shadow_version: str,
    contact_respond_id: str,
    live_message_id: Any,
    focus_hints: dict[str, Any] | None = None,
    open_question_hint: dict[str, Any] | None = None,
) -> None:
    """Parse this message again under `shadow_version` and record the result. Never raises.

    The hints are the LIVE turn's, passed in when the caller already has them; a caller that
    does not (the worker, which starts from the envelope alone) lets them default to the
    contact's stored state, which is what the live turn read a moment earlier because the
    live turn has not written its own yet.
    """
    from app.services.chatbot.head import parser as parser_mod

    row_status = "done"
    error: str | None = None
    parsed: Any = None
    prompt_version: Any = None

    try:
        from app.services.chatbot.engine import (
            _current_date_directive,
            _read_session_vars,
            _session,
        )

        with _session(session_factory) as db:
            if focus_hints is None and open_question_hint is None:
                from app.services.chatbot.dialogue import clearing

                body = _read_session_vars(
                    db, respond_io_id=contact_respond_id, reply_to_id=None
                )
                stored = (body or {}).get("session_vars") or {}
                stored = stored.get("variables") if isinstance(stored, dict) else None
                stored = stored if isinstance(stored, dict) else {}
                focus = stored.get("focus")
                question = stored.get("open_question")
                focus_hints = clearing.focus_hints(focus if isinstance(focus, dict) else {})
                open_question_hint = clearing.open_question_hint(question)
            version_id = resolve_version_id(db, shadow_version)
            config = parser_mod.resolve_config(
                db,
                current_date=_current_date_directive(),
                override_version_id=version_id,
            )
            prompt_version = config.prompt_version

        # OUTSIDE the session, exactly as the live turn calls it: the provider must never
        # be answered with a database connection held open.
        user_block = parser_mod.build_user_block(
            previous_response=None,
            latest_user_message=_latest_message(envelope),
            pending_kind=None,
            emits_v3=config.emits_v3,
            focus_hints=focus_hints,
            open_question_hint=open_question_hint,
        )
        parsed = parser_mod.parse(config, user_block)
    except Exception as exc:  # noqa: BLE001 - a shadow failure is a shadow ROW
        row_status = "failed"
        error = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "chatbot shadow parse failed for %s under %r: %s",
            contact_respond_id,
            shadow_version,
            exc,
            exc_info=True,
        )

    try:
        _write_row(
            session_factory,
            envelope=envelope,
            contact_respond_id=contact_respond_id,
            live_message_id=live_message_id,
            shadow_version=shadow_version,
            prompt_version=prompt_version,
            parsed=parsed,
            row_status=row_status,
            error=error,
        )
    except Exception:  # noqa: BLE001 - the live turn must never notice
        logger.warning(
            "chatbot shadow row could not be written for %s", contact_respond_id, exc_info=True
        )


def _latest_message(envelope: Envelope) -> str:
    message = (envelope.message or {}).get("message")
    if isinstance(message, dict):
        text = message.get("text")
        if text:
            return str(text)
        attachment = message.get("attachment")
        if isinstance(attachment, dict) and attachment.get("description"):
            return str(attachment["description"])
    return ""


def _write_row(
    session_factory: Any,
    *,
    envelope: Envelope,
    contact_respond_id: str,
    live_message_id: Any,
    shadow_version: str,
    prompt_version: Any,
    parsed: Any,
    row_status: str,
    error: str | None,
) -> None:
    """One row, on its own session, with the parse where the console reads it.

    The parse rides `trace` in the same `understood` STAGE RECORD shape a live turn writes,
    so the trace screen and `shadow_list.parse_domains` read one shape whichever row they
    are looking at.
    """
    from app.models.chatbot_turn import ChatbotTurn
    from app.services.chatbot.engine import _now

    emission = dict(parsed) if isinstance(parsed, dict) else None
    now = _now()
    record = {
        "stage": "understood",
        "status": "failed" if row_status == "failed" else "ok",
        "started_at": now.isoformat(),
        "ms": 0,
        "summary": (
            f"Parsed the message again under {shadow_version}."
            if row_status == "done"
            else f"The shadow parse under {shadow_version} did not run."
        ),
        "why": "The owner is watching this version answer real turns before promoting it.",
        "facts": {"shadow_version": shadow_version, "prompt_version": prompt_version},
        "error": error,
        "raw": {"parser_raw": emission, "derived": emission},
    }

    from app.services.chatbot.engine import _session

    with _session(session_factory) as db:
        # ONE SHADOW PER MESSAGE, checked rather than caught. A RETRY of a live turn writes
        # `attempt = 2` for the live row, but the shadow's id is derived from the MESSAGE,
        # not from the attempt, so the second shadow collides with the first on
        # `(contact_respond_id, message_id, attempt, is_test)`. Letting that land as an
        # IntegrityError would roll back a transaction the caller did not know was at risk
        # and log a database error for something that is not one: a message parsed twice
        # under the same version has nothing new to say. The row that is already there is
        # the measurement; this one is skipped.
        shadow_id = shadow_message_id(live_message_id)
        if shadow_id is not None:
            already = (
                db.query(ChatbotTurn.id)
                .filter(
                    ChatbotTurn.contact_respond_id == contact_respond_id,
                    ChatbotTurn.message_id == shadow_id,
                    ChatbotTurn.attempt == 1,
                    ChatbotTurn.is_test.is_(bool(envelope.dry_run)),
                )
                .first()
            )
            if already is not None:
                return
        db.add(
            ChatbotTurn(
                contact_respond_id=contact_respond_id,
                message_id=shadow_id,
                ingress="shadow",
                envelope=trace_mod.cap_document(envelope.model_dump(mode="json")),
                is_test=envelope.dry_run,
                status=row_status,
                stage="understood",
                branch_kind=(emission or {}).get("message_type"),
                error=error,
                attempt=1,
                trace=[record],
                # NO REPLY, ever: nothing was sent and nothing was remembered.
                response=None,
                shadow_of=str(live_message_id) if live_message_id else None,
                test_run_id=getattr(envelope, "test_run_id", None),
                started_at=now,
                finished_at=now,
            )
        )
        db.commit()


def fire(
    envelope: Envelope,
    *,
    session_factory: Any,
    shadow_version: Any,
    contact_respond_id: str,
    live_message_id: Any,
    offloaded: bool,
    focus_hints: dict[str, Any] | None = None,
    open_question_hint: dict[str, Any] | None = None,
) -> None:
    """Start the shadow parse and return immediately. Never raises, never blocks a reply.

    `offloaded` is the same flag the live turn ran under: with a worker, this rides the same
    `chat` queue, so a window costs the customer's turn nothing at all. Without one it runs
    in-process, because an install with no worker must still be able to run a window - and
    it runs AFTER the live row is inserted, so a slow provider delays the observation rather
    than the answer.
    """
    if not isinstance(shadow_version, str) or not shadow_version.strip():
        return
    if envelope.dry_run:
        # A dry run answers nobody and writes nothing; shadowing it would put console
        # traffic into the window the owner is reading real turns out of.
        return
    try:
        if offloaded:
            from app.services.chatbot.engine import CHAT_QUEUE
            from app.services.queue_service import enqueue_job
            from app.tasks.chat_turns import run_shadow_parse_job

            enqueue_job(
                run_shadow_parse_job,
                envelope.model_dump(mode="json"),
                shadow_version.strip(),
                contact_respond_id,
                str(live_message_id) if live_message_id else None,
                queue_name=CHAT_QUEUE,
                job_timeout=120,
            )
            return
    except Exception:  # noqa: BLE001 - redis down is not the live turn's problem
        logger.warning("chatbot shadow parse could not be enqueued; running it inline", exc_info=True)

    run_for(
        envelope,
        session_factory=session_factory,
        shadow_version=shadow_version.strip(),
        contact_respond_id=contact_respond_id,
        live_message_id=live_message_id,
        focus_hints=focus_hints,
        open_question_hint=open_question_hint,
    )
