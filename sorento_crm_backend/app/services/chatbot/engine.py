"""`run_turn` - the head of the turn: receive, understand, check access, route.

One inbound WhatsApp message in, `{turn_id, ctx, item, branch_kind, delegate}` out. The
stages the S1 head owns map onto the five nodes it replaces in the live spine
(`get-session-vars`, `Call 'sub-query-reformulator'`, `check-access`, `build-ctx`,
`route-turn`), and `item` is byte-equal to what `route-turn` emits today so every n8n
reader downstream is unchanged (AC-101, AC-110).

**Session discipline.** `run_turn` takes a session FACTORY, not a session. The plan's
capacity section is explicit: never hold a DB session across LLM or MCP I/O, and the
96/100-connection incident is the evidence. The engine opens a session to read, closes it,
makes the parser call with nothing checked out, and reopens to check access and record the
turn. A request-scoped `Depends(get_db)` session could not satisfy that, which is why the
signature differs from the plan's original sketch (the plan is updated in the same change).

**D14, dry run.** `envelope.dry_run` is evaluated FIRST, before anything side-effecting
(H37: n8n called next-assignee and guarded afterwards). On a dry run the only row written
anywhere is the `chatbot.turns` record itself, every action carries `dry_run: true`, and
the response carries `session_patch` - null in S1, because the head writes no session
state; the tail (S2) is what fills it.
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Iterator

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.chatbot_turn import ChatbotTurn
from app.services.chatbot import jsc, trace as trace_mod
from app.services.chatbot.contracts import TURN_FAILURE_STAGES, Envelope
from app.services.chatbot.delegate import delegate_for
from app.services.chatbot.head import parser
from app.services.chatbot.head.access import check_access, default_space_id
from app.services.chatbot.head.build_ctx import build_ctx
from app.services.chatbot.head.output_exchange import (
    ParserOutputError,
    post_process,
    suggest_follow_up,
)
from app.services.chatbot.head.route import decide
from app.services.chatbot.usage import record_parser_usage

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]

# H5 / AC-107: `sub-media-intake` did not patch a transcript onto an audio turn, so the
# spine's audio branch had no successor and the turn died silently. It is now a FAILED
# turn with an explicit reason and today's error reply.
AUDIO_NOT_PATCHED_ERROR = (
    "media intake did not transcribe this voice note, so there is no text to understand"
)
GENERIC_ERROR_REPLY = parser.PARSER_ERROR_REPLY


class TurnResult:
    """What the endpoint serialises. A plain object so the route stays a thin adapter."""

    __slots__ = (
        "turn_id",
        "is_test",
        "ctx",
        "item",
        "branch_kind",
        "delegate",
        "reply",
        "actions",
        "session_patch",
        "duplicate",
        "status",
        "stage",
        "error",
    )

    def __init__(self, **kwargs: Any) -> None:
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))
        if self.actions is None:
            self.actions = []
        if self.duplicate is None:
            self.duplicate = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "is_test": bool(self.is_test),
            "ctx": self.ctx,
            "item": self.item,
            "branch_kind": self.branch_kind,
            "delegate": self.delegate,
            "reply": self.reply,
            "actions": self.actions,
            "session_patch": self.session_patch,
            "duplicate": self.duplicate,
        }


def _now() -> datetime:
    return datetime.now(timezone.utc)


@contextmanager
def _session(factory: SessionFactory) -> Iterator[Session]:
    db = factory()
    try:
        yield db
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Envelope readers. Each names the n8n node whose read it reproduces, so the
# by-name hazard the port removes stays traceable.
# --------------------------------------------------------------------------- #


def _tf_message(envelope: Envelope) -> dict[str, Any]:
    """`tf-message`: the respond.io webhook body carried on the envelope."""
    return envelope.message or {}


def _inner_message(envelope: Envelope) -> dict[str, Any]:
    """`ctx.text.message.message` - the respond.io message payload itself."""
    return jsc.get(jsc.get(_tf_message(envelope), "message"), "message") or {}


def _message_id(envelope: Envelope) -> str | None:
    value = jsc.get(jsc.get(_tf_message(envelope), "message"), "messageId")
    return str(value) if value not in (None, "") else None


def _contact_respond_id(envelope: Envelope) -> str:
    """`sorento-sub-respond-findcontact-respond`'s `id`, carried on the envelope (D1).

    Presence is guaranteed by `Envelope`'s own validator, so a caller that omits it gets a
    422 naming the field instead of a 500 from in here. The guard stays as a belt: this is
    also reachable from `app/tasks/chat_turns.py` (S7) with an envelope rebuilt from a
    stored row, and a silent empty string would key a turn to nobody.
    """
    contact_id = jsc.get(envelope.contact, "id")
    if contact_id in (None, ""):  # pragma: no cover - Envelope validation catches it first
        raise ValueError("envelope.contact.id is required")
    return str(contact_id)


def _is_human_intervened(envelope: Envelope) -> bool:
    """`is-human-intervened`: `custom_fields.find(...)?.value?.toBoolean() == true`."""
    row = jsc.find(
        jsc.get(envelope.contact, "custom_fields"),
        lambda x: jsc.get(x, "name") == "is_human_intervened",
    )
    return jsc.to_boolean(jsc.get(row, "value")) is True


def _attachment_type(envelope: Envelope) -> Any:
    return jsc.get(jsc.get(_inner_message(envelope), "attachment"), "type")


def _reply_to_message_id(envelope: Envelope) -> str | None:
    """`tf-message.message.replyTo.id` - the quoted message, when the customer quoted."""
    value = jsc.get(jsc.get(jsc.get(_tf_message(envelope), "message"), "replyTo"), "id")
    return str(value) if value not in (None, "") else None


def build_latest_user_message(envelope: Envelope, session_block: Any = None) -> str:
    """The two-line string `Call 'sub-query-reformulator'` builds today, verbatim.

    The live expression (`export/live-spine-sorento-consume-main/workflow.json`, the
    `Call 'sub-query-reformulator'` node) chains THREE alternatives on line 1:
    the message text, an attachment's description, then `$json.message`. All three are
    reproduced. The third reads the node's own input - `get-session-vars`'s response,
    `{respond_io_id, session_vars}` - which carries no `message` key today, so it
    contributes nothing on any captured turn. It is implemented anyway rather than
    written off as dead: "verbatim" has to mean it, and the day that response grows a
    `message` key the port would otherwise diverge in silence.

    Line 1 is the text, or an image's description when there is no text. Line 2 is the
    quoted message n8n appends as `reply to: ...`; several ported blocks split it back off
    with `/\\s*reply to:/i`, so the exact shape (including the trailing newline) matters.
    """
    inner = _inner_message(envelope)
    text = jsc.get(inner, "text")
    if not jsc.truthy(text):
        text = jsc.get(jsc.get(inner, "attachment"), "description")
    if not jsc.truthy(text):
        text = jsc.get(session_block, "message")  # the third alternative, `|| $json.message`
    line1 = jsc.js_string(text) if jsc.truthy(text) else ""

    reply_to = jsc.get(jsc.get(_tf_message(envelope), "message"), "replyTo")
    quoted = jsc.get(reply_to, "message")
    line2 = ""
    if jsc.truthy(quoted):
        quoted_text = jsc.get(quoted, "text")
        body = quoted_text if jsc.truthy(quoted_text) else jsc.get(quoted, "title")
        line2 = "reply to: " + jsc.js_string(body) if jsc.truthy(body) else "reply to: "
    return f"{line1}\n{line2}\n"


def _pending_kind(variables: dict[str, Any]) -> str | None:
    """R3: the persisted marker, read where the JS matched a frozen reply string."""
    pending = variables.get("pending")
    kind = jsc.get(pending, "kind")
    return str(kind) if kind else None


# --------------------------------------------------------------------------- #
# Reads (session-bound, short)
# --------------------------------------------------------------------------- #


def _read_session_vars(db: Session, *, respond_io_id: str, reply_to_id: str | None) -> dict:
    """`get-session-vars`: the same body `GET /external/conversation-variables/{id}` returns."""
    from app.services.conversation_variables_service import (
        get_for_contact,
        get_referenced_result_set,
        get_referenced_state,
    )

    state = get_for_contact(db, respond_io_id=respond_io_id)
    if reply_to_id is not None:
        state = {
            **state,
            "referenced_result_set": get_referenced_result_set(
                db, respond_io_id=respond_io_id, message_id=reply_to_id
            ),
            "referenced_state": get_referenced_state(
                db, respond_io_id=respond_io_id, message_id=reply_to_id
            ),
        }
    return {"respond_io_id": respond_io_id, "session_vars": state}


def _select_turn(db: Session, *, contact_respond_id: str, message_id: str | None):
    """The raw lookup. Kept separate from `_existing_turn` so the post-collision retry
    below can re-read WITHOUT going through whatever a test has wrapped around the public
    helper - the forced-TOCTOU test synchronises on `_existing_turn`, and a second trip
    through that barrier would deadlock the very path being fixed."""
    if message_id is None:
        return None
    return (
        db.query(ChatbotTurn)
        .filter(
            ChatbotTurn.contact_respond_id == contact_respond_id,
            ChatbotTurn.message_id == message_id,
        )
        # NEWEST first: with a retry there can be several rows for one message, and the
        # one that matters is the last one - the earlier attempts are settled history.
        .order_by(ChatbotTurn.created_at.desc(), ChatbotTurn.attempt.desc())
        .first()
    )


def _awaiting_retry(row) -> bool:
    """Is this row a FAILED turn an operator asked to re-run (S2b)?

    D15 says a respond message already turned into a turn is a duplicate, and a retry
    re-posts that same message - same `message_id` - so without this it would come back
    as `duplicate: true` and Retry would be a no-op that reported success. The marker is
    what tells the two apart: an operator asked for this one.
    """
    return row is not None and row.status == "failed" and row.retry_requested_at is not None


def _existing_turn(db: Session, *, contact_respond_id: str, message_id: str | None):
    """D15: has this respond message already been turned into a turn?

    Checked with a SELECT rather than left to the unique index so a legitimate double
    delivery (webhook plus failover poller) costs a lookup, not an exception and an LLM
    call. The index is the real guarantee under concurrency, and the collision it raises
    is caught in `run_turn` - the SELECT alone is a TOCTOU window, not a lock.
    """
    return _select_turn(db, contact_respond_id=contact_respond_id, message_id=message_id)


def _insert_turn(
    db: Session,
    *,
    envelope: Envelope,
    contact_respond_id: str,
    retrying: ChatbotTurn | None = None,
) -> ChatbotTurn:
    """The turn row. `retrying` is the failed row an operator asked to re-run (S2b).

    A retry is a NEW turn, not an edit of the old one: same message, next attempt, ingress
    `retry`. The old row keeps its trace and its failure - that is the record the operator
    was reading - and only loses its retry marker, so a second failure can be retried too.
    """
    row = ChatbotTurn(
        contact_respond_id=contact_respond_id,
        message_id=_message_id(envelope),
        ingress="retry" if retrying is not None else envelope.ingress,
        envelope=trace_mod.cap_document(envelope.model_dump(mode="json")),
        is_test=envelope.dry_run,
        status="processing",
        stage="received",
        attempt=(retrying.attempt + 1) if retrying is not None else 1,
        trace=[],
        shadow_of=getattr(envelope, "shadow_of", None),
        started_at=_now(),
    )
    db.add(row)
    if retrying is not None:
        # Consumed. Leaving it set would make the NEXT delivery of this message look like
        # another requested re-run rather than the duplicate it is.
        retrying.retry_requested_at = None
    db.commit()
    db.refresh(row)
    return row


def _close_turn(
    db: Session,
    turn_id: str,
    *,
    status: str,
    stage: str | None,
    branch_kind: str | None,
    error: str | None,
    records: list[dict[str, Any]],
    response: dict[str, Any] | None = None,
) -> None:
    assert stage is None or stage in TURN_FAILURE_STAGES, (
        f"{stage!r} is not a declared turn stage - a typo here lands in the column and "
        f"reads as an unknown state on the trace screen. Declared: {TURN_FAILURE_STAGES}"
    )
    row = db.query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).first()
    if row is None:  # pragma: no cover - the row was inserted two lines earlier
        return
    row.status = status
    row.stage = stage
    row.branch_kind = branch_kind
    row.error = error
    row.trace = records
    # D15 needs the ORIGINAL answer, not just the fact that a turn happened: a duplicate
    # delivery replays this, and n8n's `build-ctx` / `route-turn` re-emitters would throw
    # on a null. It is also what S2b's Retry reads. Written HERE, at close, which is what
    # bounds the guarantee - see `_duplicate_result`.
    row.response = trace_mod.cap_document(response)
    row.finished_at = _now()
    db.commit()


def _record_parser_usage(
    db: Session,
    *,
    usage: dict[str, Any],
    started: float,
    contact_respond_id: str,
    dry_run: bool,
    answered: bool,
) -> None:
    """One `ai_assistant_usage_logs` row for the turn's parser call.

    LIVE turns only (D14: a test envelope writes nothing outside `chatbot.turns`), and
    only when the provider reported something - a stubbed parse has no spend to record.
    Written on the session that is open anyway, so it costs no extra connection.
    """
    if dry_run or not usage:
        return
    record_parser_usage(
        db,
        usage=usage,
        response_time_ms=int((time.perf_counter() - started) * 1000),
        contact_respond_id=contact_respond_id,
        answered=answered,
    )


def _duplicate_result(row: ChatbotTurn) -> TurnResult:
    """D15: the same respond message arrived twice. Replay the FIRST turn's answer.

    **`ctx` and `item` can still be null here, and that is not a defect to fix in the
    engine.** `response` is written by `_close_turn`, so it exists only once the first
    turn has FINISHED. Two cases return nulls:

    * the first turn is still `processing` - which is the LIKELY timing, not the edge
      case: a webhook delivery and a poller re-delivery arrive within the same second or
      two, well inside the 5 to 10 seconds a parse plus an access check takes;
    * the first turn `failed`, so it produced no answer to replay at all.

    Making the second caller WAIT for the first would put a poll loop on a synchronous
    request for a message the caller must not answer twice anyway, which buys nothing:
    whatever it waited for, it still sends nothing. **The actual guarantee is on the n8n
    side** - the Switch on `duplicate` sits BEFORE the `build-ctx` / `route-turn`
    re-emitters, so a null `ctx` is never dereferenced (plan, S1 n8n section; AC-110).
    The response body is a courtesy for the trace screen and for a caller that wants to
    log what the original turn decided, never a contract the caller may depend on.

    `status` is the row's own, so `processing` (in flight), `failed` and `delegated` /
    `done` are all distinguishable: a caller that sees `duplicate: true, status:
    processing` knows the nulls mean "not finished yet", not "nothing to say".
    """
    response = row.response if isinstance(row.response, dict) else {}
    return TurnResult(
        turn_id=str(row.id),
        is_test=bool(row.is_test),
        ctx=response.get("ctx"),
        item=response.get("item"),
        branch_kind=row.branch_kind,
        delegate=delegate_for(row.branch_kind) if row.branch_kind else None,
        reply=response.get("reply"),
        actions=response.get("actions") or [],
        duplicate=True,
        # The row's own status, unmodified: `processing` means the first turn is still in
        # flight and the nulls above are "not yet", not "never".
        status=row.status,
        stage=row.stage,
    )


# --------------------------------------------------------------------------- #
# The turn
# --------------------------------------------------------------------------- #


def run_turn(envelope: Envelope, *, session_factory: SessionFactory) -> TurnResult:
    """Run the head of one turn. NEVER raises for a business failure; records it.

    Two things happen before the stages: the D15 dedup, and the row insert. Everything
    after that is wrapped, so an unexpected exception anywhere - a provider error while
    resolving config, an access-service failure, the stock predicate throwing on a
    contact with no `is_allowed_stock` field - closes the turn as `failed` with the stage
    it reached and hands the caller today's error reply. A turn left at `processing` with
    a null error and no trace is exactly the dropped turn H32 is about.
    """
    turn_trace = trace_mod.TurnTrace()
    turn_trace.start()

    contact_respond_id = _contact_respond_id(envelope)
    message_id = _message_id(envelope)
    dry_run = envelope.dry_run

    with _session(session_factory) as db:
        existing = _existing_turn(
            db, contact_respond_id=contact_respond_id, message_id=message_id
        )
        retrying = existing if _awaiting_retry(existing) else None
        if existing is not None and retrying is None:
            # D15: the two injectors delivered the same respond message. No second turn
            # runs, no second LLM call, and the caller's Switch on `duplicate` sends
            # nothing.
            return _duplicate_result(existing)
        try:
            row = _insert_turn(
                db,
                envelope=envelope,
                contact_respond_id=contact_respond_id,
                retrying=retrying,
            )
        except IntegrityError:
            # The SELECT above is a TOCTOU window, not a lock: a webhook delivery racing a
            # poller re-delivery can both miss and both insert. The unique index is the
            # real guarantee, so the loser reads the winner's row rather than 500ing.
            db.rollback()
            winner = _select_turn(
                db, contact_respond_id=contact_respond_id, message_id=message_id
            )
            if winner is None or _awaiting_retry(winner):
                # Either some OTHER constraint failed, or two retries of one message
                # raced - neither is a duplicate, and guessing would answer the customer
                # from a turn that never ran.
                raise
            return _duplicate_result(winner)
        turn_id = str(row.id)

    # The stage the turn is currently in, for the catch-all below. A plain list because
    # the inner stages update it and the handler reads it.
    stage: list[str] = ["received"]
    actions: list[dict[str, Any]] = []
    try:
        return _run_stages(
            envelope,
            session_factory=session_factory,
            turn_trace=turn_trace,
            turn_id=turn_id,
            contact_respond_id=contact_respond_id,
            dry_run=dry_run,
            actions=actions,
            stage=stage,
        )
    except Exception as exc:  # noqa: BLE001 - a failed turn is recorded, never dropped
        message = f"{type(exc).__name__}: {exc}"
        logger.exception("chatbot turn %s failed at stage %s", turn_id, stage[0])
        turn_trace.record(
            stage[0],  # type: ignore[arg-type]
            status="failed",
            summary="The turn stopped before it could be answered.",
            why="Something the turn depends on did not respond as expected.",
            facts={"stage": stage[0]},
            error=message,
            raw=None,
        )
        with _session(session_factory) as db:
            _close_turn(
                db,
                turn_id,
                status="failed",
                stage=stage[0],
                branch_kind=None,
                error=message,
                records=turn_trace.records,
            )
        return _failed_result(turn_id, stage[0], message, actions, dry_run)


def _run_stages(  # noqa: PLR0915
    envelope: Envelope,
    *,
    session_factory: SessionFactory,
    turn_trace: trace_mod.TurnTrace,
    turn_id: str,
    contact_respond_id: str,
    dry_run: bool,
    actions: list[dict[str, Any]],
    stage: list[str],
) -> TurnResult:
    """received -> understood -> access -> routed. Wrapped by `run_turn`."""
    with _session(session_factory) as db:
        # AC-108: today's `set-human-intervened` path. The turn CONTINUES; the caller
        # clears the flag on the contact.
        if _is_human_intervened(envelope):
            actions.append(
                {
                    "kind": "update_contact_fields",
                    "fields": {"is_human_intervened": False},
                    "dry_run": dry_run,
                }
            )

        # AC-107 / H5: the attachment is still audio, so media intake did not patch a
        # transcript in. n8n's audio branch simply had no successor and the turn vanished.
        if _attachment_type(envelope) == "audio":
            # Two stage names, on purpose. The ROW says `intake` (AC-107's word, and the
            # real stopping point - media intake, which runs in n8n, is what failed). The
            # TRACE row says `received`, because `TurnStage` is the closed set of eight
            # the timeline renders and `intake` is not one of them. `facts.stage` carries
            # the precise answer so the screen can show it without widening the timeline.
            turn_trace.record(
                "received",
                status="failed",
                summary="Could not read the voice note.",
                why="Media intake returned no transcript, so there is nothing to understand.",
                facts={"attachment_type": "audio", "stage": "intake"},
                error=AUDIO_NOT_PATCHED_ERROR,
                raw={"message": _inner_message(envelope)},
            )
            _close_turn(
                db,
                turn_id,
                status="failed",
                stage="intake",
                branch_kind=None,
                error=AUDIO_NOT_PATCHED_ERROR,
                records=turn_trace.records,
            )
            return _failed_result(turn_id, "intake", AUDIO_NOT_PATCHED_ERROR, actions, dry_run)

        session_block = _read_session_vars(
            db,
            respond_io_id=contact_respond_id,
            reply_to_id=_reply_to_message_id(envelope),
        )
        variables = jsc.get(jsc.get(session_block, "session_vars"), "variables") or {}
        referenced_result_set = jsc.get(
            jsc.get(session_block, "session_vars"), "referenced_result_set"
        )
        latest_user_message = build_latest_user_message(envelope, session_block)
        parser_config = parser.resolve_config(db, current_date=_current_date_directive())

    turn_trace.record(
        "received",
        summary="Received the message and loaded what the bot remembered.",
        why="Every turn starts from the contact's stored conversation state.",
        facts={
            "ingress": envelope.ingress,
            "remembered_keys": len(variables),
            "quoted_a_message": _reply_to_message_id(envelope) is not None,
            "dry_run": dry_run,
        },
        raw={"session_vars": session_block},
    )

    # -- understood (NO DB SESSION IS OPEN HERE) ---------------------------- #
    stage[0] = "understood"
    parent_input = {
        "latest_user_message": latest_user_message,
        "contact_id": contact_respond_id,
        "previous_conversation_state": variables,
        "referenced_result_set": referenced_result_set,
    }
    user_block = parser.build_user_block(
        previous_response=variables.get("response"),
        latest_user_message=latest_user_message,
        pending_kind=_pending_kind(variables),
    )
    parse_started = time.perf_counter()
    try:
        parser_raw = parser.parse(parser_config, user_block)
        parser_usage = getattr(parser_raw, "usage", {}) or {}
        parse_block = post_process({"output": parser_raw}, {}, parent_input)
        parse_block = suggest_follow_up(parse_block, parent_input)
    except (parser.ParserError, ParserOutputError) as exc:
        # R5 / H44: no soft default and no default routing. A failed understanding is a
        # failed turn with today's error reply.
        message = str(exc)
        turn_trace.record(
            "understood",
            status="failed",
            summary="Could not understand the message.",
            why="The parser did not return a usable answer, so the turn was not routed.",
            facts={"prompt_version": parser_config.prompt_version, "model": parser_config.model},
            error=message,
            raw={"user_block": user_block},
        )
        with _session(session_factory) as db:
            # The provider bills a truncated or non-JSON emission too, so a failed parse
            # is a spend the usage table has to carry.
            _record_parser_usage(
                db,
                usage=getattr(exc, "usage", {}) or {},
                started=parse_started,
                contact_respond_id=contact_respond_id,
                dry_run=dry_run,
                answered=False,
            )
            _close_turn(
                db,
                turn_id,
                status="failed",
                stage="understood",
                branch_kind=None,
                error=message,
                records=turn_trace.records,
            )
        return _failed_result(turn_id, "understood", message, actions, dry_run)

    qf = parse_block.get("output") or {}
    turn_trace.record(
        "understood",
        summary=trace_mod.understood_summary(qf),
        why="The parser is the only step that reads the customer's words; everything after it works on structured state.",
        facts={
            "message_type": qf.get("message_type"),
            "domain": qf.get("domain_hint"),
            "intent": qf.get("intent_hint"),
            "entities": len(qf.get("entities") or []),
            "prompt_version": parser_config.prompt_version,
            # Always present, 0 when the parse was stubbed or the provider reported
            # nothing: a missing row reads as "free", which no LLM call is.
            "tokens": int(parser_usage.get("total_tokens") or 0),
        },
        raw={"parser_raw": parse_block.get("_parser_raw"), "derived": qf},
    )

    # -- access + routed ---------------------------------------------------- #
    stage[0] = "access"
    with _session(session_factory) as db:
        _record_parser_usage(
            db,
            usage=parser_usage,
            started=parse_started,
            contact_respond_id=contact_respond_id,
            dry_run=dry_run,
            answered=True,
        )
        suggested_agent = jsc.get(qf.get("routing"), "suggested_agent")
        access = check_access(
            db,
            agent_code=suggested_agent,
            contact_id=contact_respond_id,
            space_id=default_space_id(db),
        )
        turn_trace.record(
            "access",
            summary=(
                f"Access allowed for {access.get('agent_name') or suggested_agent}."
                if access.get("allowed")
                else f"Access refused: {access.get('decision')}."
            ),
            why="The contact must be granted the agent this turn would use before anything is looked up.",
            facts={
                "agent": suggested_agent,
                "allowed": bool(access.get("allowed")),
                "decision": access.get("decision"),
            },
            raw=access,
        )

        stage[0] = "routed"
        ctx = build_ctx(
            contact=envelope.contact,
            text=_tf_message(envelope),
            session=session_block,
            parse=parse_block,
            access=access,
            media=getattr(envelope, "media", None),
        )[0]["json"]["ctx"]

        stock_denial_enabled = _stock_denial_enabled(db)
        branch_kind, tier_stamp = decide(ctx, stock_denial_enabled=stock_denial_enabled)
        item = _stamp_item(access, branch_kind, tier_stamp)

        turn_trace.record(
            "routed",
            summary=f"Routed to {trace_mod.lane_words(branch_kind, qf.get('domain_hint'))}.",
            why=trace_mod.routed_why(branch_kind, qf, bool(access.get("allowed"))),
            facts={
                "lane": branch_kind,
                "tier_pick": tier_stamp.get("tier_pick"),
                "stock_denial_enabled": stock_denial_enabled,
            },
            raw={"item": item},
        )

        delegate = delegate_for(branch_kind)
        _close_turn(
            db,
            turn_id,
            status="delegated" if delegate else "done",
            stage="routed",
            branch_kind=branch_kind,
            error=None,
            records=turn_trace.records,
            # S2 / D15: a duplicate delivery replays THIS, so n8n's re-emitters never see
            # a null `ctx` or `item`. `actions` rides along because the caller must not
            # execute them twice either - it gets the original list and its own Switch on
            # `duplicate` decides to send nothing.
            response={"ctx": ctx, "item": item, "actions": actions},
        )

    return TurnResult(
        turn_id=turn_id,
        is_test=dry_run,
        ctx=ctx,
        item=item,
        branch_kind=branch_kind,
        delegate=delegate,
        actions=actions,
        # D14: on a dry run the response carries the would-be session patch. The HEAD
        # writes no session state at all, so there is nothing to patch yet and this is
        # null for every turn in S1; the tail (S2) is what fills it.
        session_patch=None,
        status="delegated" if delegate else "done",
        stage="routed",
    )


def _stamp_item(access: dict, branch_kind: str, tier_stamp: dict) -> dict[str, Any]:
    """`route-turn`'s output item, byte-equal to today (AC-101)."""
    from app.services.chatbot.contracts import TAG_ONLY_BRANCH_KINDS

    if branch_kind in TAG_ONLY_BRANCH_KINDS:
        return {"branch_kind": branch_kind}
    return {**access, "branch_kind": branch_kind, **tier_stamp}


def _failed_result(
    turn_id: str, stage: str, error: str, actions: list[dict[str, Any]], dry_run: bool
) -> TurnResult:
    """A failed turn still hands the caller today's error reply to send (AC-105, AC-107)."""
    return TurnResult(
        turn_id=turn_id,
        is_test=dry_run,
        ctx=None,
        item=None,
        branch_kind=None,
        delegate=None,
        reply={"text": GENERIC_ERROR_REPLY, "quick_replies": []},
        actions=[
            *actions,
            {
                "kind": "send_message",
                "text": GENERIC_ERROR_REPLY,
                "quick_replies": [],
                "dry_run": dry_run,
            },
        ],
        status="failed",
        stage=stage,
        error=error,
    )


def _stock_denial_enabled(db: Session) -> bool:
    """R1: `system_settings.chatbot_stock_denial_enabled`, default false.

    Off, `isStockCheckDenied` is never evaluated and no turn can reach `stock_denied` or
    `demand_qty` - which is exactly as dead as those two lanes are today, by typo.
    """
    from app.models.user import SystemSetting

    row = db.query(SystemSetting).first()
    return bool(getattr(row, "chatbot_stock_denial_enabled", False)) if row is not None else False


# Luxon's `cccc, dd MMMM yyyy` is English regardless of where the process runs. Python's
# `%A` / `%B` follow LC_TIME, so a container with a non-English locale would hand the
# parser a date it has never been shown a single example of. Named, not formatted.
_WEEKDAYS = (
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
)
_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def _current_date_directive() -> str:
    """`{{ $now.toUTC(8*60).format('cccc, dd MMMM yyyy') }}` - Malaysia time, same format."""
    from datetime import timedelta

    now_myt = datetime.now(timezone.utc) + timedelta(hours=8)
    return (
        f"{_WEEKDAYS[now_myt.weekday()]}, {now_myt.day:02d} "
        f"{_MONTHS[now_myt.month - 1]} {now_myt.year}"
    )
