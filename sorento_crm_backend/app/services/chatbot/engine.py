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
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Iterator

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.chatbot_turn import ChatbotTurn
from app.services.chatbot import jsc, trace as trace_mod
from app.services.chatbot.contracts import TURN_FAILURE_STAGES, Envelope
from app.services.chatbot.delegate import delegate_for, enabled_lanes_from
from app.services.error_handler import AppException
from app.services.chatbot.head import parser
from app.services.chatbot.head.access import check_access, default_space_id
from app.services.chatbot.head.build_ctx import build_ctx
from app.services.chatbot.head.output_exchange import (
    ParserOutputError,
    post_process,
    suggest_follow_up,
)
from app.services.chatbot.head.route import decide
from app.services.chatbot.lanes import business, casual
from app.services.chatbot.lanes.business import resolve_gate, services as business_services

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]

# "the caller did not pass a row", which `None` cannot mean here: `None` is the real value
# when the settings singleton does not exist yet.
_UNSET: Any = object()

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
        "ctx",
        "item",
        "branch_kind",
        "delegate",
        "delegate_payload",
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
            "ctx": self.ctx,
            "item": self.item,
            "branch_kind": self.branch_kind,
            "delegate": self.delegate,
            "delegate_payload": self.delegate_payload,
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


# O2 / AC-112: the three keys a DRY-RUN envelope may carry so a harness can drive a turn
# with no LLM and none of the contact's real memory. Declared in ONE order, and that order
# is what `harness_keys_ignored` reports, so two traces diff readably.
#
# `Envelope` is `extra="allow"`, so they arrive as extras rather than as declared fields -
# deliberately: they are a HARNESS contract, not part of the envelope every injector sends,
# and declaring them would invite a live producer to start setting them.
HARNESS_KEYS = (
    "mock_reformulator_output",
    "previous_conversation_state",
    "referenced_result_set",
)


def _harness_keys_present(envelope: Envelope) -> list[str]:
    """Which harness keys this envelope carries, in the declared order.

    Membership, not truthiness: `previous_conversation_state: {}` is a harness saying "this
    contact remembers NOTHING", which is a different instruction from not saying anything.
    """
    extra = envelope.model_extra or {}
    return [key for key in HARNESS_KEYS if key in extra]


def _harness_value(envelope: Envelope, key: str) -> Any:
    return (envelope.model_extra or {}).get(key)


def _inject_harness_session(
    session_block: dict[str, Any], envelope: Envelope
) -> dict[str, Any]:
    """G8: replace the stored memory with the harness's, FOR THIS TURN ONLY.

    Applied to the whole `session_block` rather than to the local `variables`, because the
    same object becomes `ctx.session` and the `received` record's `raw` - a turn whose
    trace showed the contact's real memory while the lane ran on injected memory would be
    the worst kind of unreadable.

    Nothing here writes: the head persists no session state at all (the tail does, at S2),
    and D14 already forbids that write on a dry run. The guarantee is asserted by
    `TestHarnessInjectionsG8::test_the_injected_state_is_never_written_back`.
    """
    present = _harness_keys_present(envelope)
    if not ({"previous_conversation_state", "referenced_result_set"} & set(present)):
        return session_block
    session_vars = dict(jsc.get(session_block, "session_vars") or {})
    if "previous_conversation_state" in present:
        session_vars["variables"] = _harness_value(envelope, "previous_conversation_state")
    if "referenced_result_set" in present:
        session_vars["referenced_result_set"] = _harness_value(envelope, "referenced_result_set")
    return {**session_block, "session_vars": session_vars}


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
        .order_by(ChatbotTurn.created_at.asc())
        .first()
    )


def _existing_turn(db: Session, *, contact_respond_id: str, message_id: str | None):
    """D15: has this respond message already been turned into a turn?

    Checked with a SELECT rather than left to the unique index so a legitimate double
    delivery (webhook plus failover poller) costs a lookup, not an exception and an LLM
    call. The index is the real guarantee under concurrency, and the collision it raises
    is caught in `run_turn` - the SELECT alone is a TOCTOU window, not a lock.
    """
    return _select_turn(db, contact_respond_id=contact_respond_id, message_id=message_id)


def _insert_turn(db: Session, *, envelope: Envelope, contact_respond_id: str) -> ChatbotTurn:
    row = ChatbotTurn(
        contact_respond_id=contact_respond_id,
        message_id=_message_id(envelope),
        ingress=envelope.ingress,
        envelope=envelope.model_dump(mode="json"),
        is_test=envelope.dry_run,
        status="processing",
        stage="received",
        attempt=1,
        trace=[],
        shadow_of=getattr(envelope, "shadow_of", None),
        started_at=_now(),
    )
    db.add(row)
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
    row.response = response
    row.finished_at = _now()
    db.commit()


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
        ctx=response.get("ctx"),
        item=response.get("item"),
        branch_kind=row.branch_kind,
        # D15: replay what the FIRST turn decided, never recompute it. The row's status
        # already records it, and recomputing would hand a different answer back for the
        # same message if `chatbot_completed_lanes` changed in between - which is the one
        # thing a duplicate must not do.
        delegate=row.branch_kind if row.status == "delegated" else None,
        delegate_payload=response.get("delegate_payload"),
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
        if existing is not None:
            # D15: the two injectors delivered the same respond message. No second turn
            # runs, no second LLM call, and the caller's Switch on `duplicate` sends
            # nothing.
            return _duplicate_result(existing)
        try:
            row = _insert_turn(db, envelope=envelope, contact_respond_id=contact_respond_id)
        except IntegrityError:
            # The SELECT above is a TOCTOU window, not a lock: a webhook delivery racing a
            # poller re-delivery can both miss and both insert. The unique index is the
            # real guarantee, so the loser reads the winner's row rather than 500ing.
            db.rollback()
            winner = _select_turn(
                db, contact_respond_id=contact_respond_id, message_id=message_id
            )
            if winner is None:  # pragma: no cover - some OTHER constraint failed
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
        # O2 / AC-112: honoured on a DRY RUN, ignored on a live envelope. The ignored list
        # is recorded below rather than dropped, because a harness envelope that reached a
        # real customer would otherwise answer them from a mock in silence.
        harness_present = _harness_keys_present(envelope)
        harness_ignored: list[str] = [] if dry_run else harness_present
        if dry_run:
            session_block = _inject_harness_session(session_block, envelope)
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
            # ALWAYS present, empty list included: a reader must never have to tell
            # "no harness keys" from "this build does not report them".
            "harness_keys_ignored": harness_ignored,
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
    # G6: a dry run may supply the emission instead of paying for it. The mock goes
    # through the SAME `post_process` + `suggest_follow_up` the real parse takes, so a
    # harness turn routes off DERIVED state and exercises the code under test rather than
    # whatever the harness happened to type. A mock that is not a parser emission raises
    # `ParserOutputError` from `post_process` and lands on the failed-`understood` arm
    # below, exactly as a malformed model answer does (R5 / H44).
    parser_bypassed = dry_run and "mock_reformulator_output" in harness_present
    try:
        if parser_bypassed:
            parser_raw = _harness_value(envelope, "mock_reformulator_output")
        else:
            parser_raw = parser.parse(parser_config, user_block)
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
        summary=(
            "Parser bypassed by harness."
            if parser_bypassed
            else trace_mod.understood_summary(qf)
        ),
        why=(
            "A test envelope supplied the parser's answer, so no model was asked; "
            "everything after this point ran normally."
            if parser_bypassed
            else "The parser is the only step that reads the customer's words; everything after it works on structured state."
        ),
        facts={
            "message_type": qf.get("message_type"),
            "domain": qf.get("domain_hint"),
            "intent": qf.get("intent_hint"),
            "entities": len(qf.get("entities") or []),
            "prompt_version": parser_config.prompt_version,
            "parser_bypassed": parser_bypassed,
        },
        raw={"parser_raw": parse_block.get("_parser_raw"), "derived": qf},
    )

    # -- access + routed ---------------------------------------------------- #
    stage[0] = "access"
    with _session(session_factory) as db:
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

        # ONE read of the settings singleton for the whole turn, on the session routing
        # already holds: no extra session, no second query, and nothing read again later.
        settings_row = _settings_row(db)
        stock_denial_enabled = _stock_denial_enabled(db, settings_row)
        enabled_lanes = _enabled_lanes(db, settings_row)
        # D5, once per turn: the respond workspace's own `space_id`, never n8n's hard-coded
        # 364817. Read HERE because S6c's probes run after this session has closed.
        space_id_for_turn = business_services.fetch_space_id(db)
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
                # Why this turn went to n8n or did not, without reading the settings row.
                "lane_completed_by_crm": branch_kind in enabled_lanes,
            },
            raw={"item": item},
        )

        # -- the business lane's resolve + gate (S6a) ----------------------- #
        # THE one call site into `lanes/`. Three arms reach `sub-resolve-and-gate` in
        # n8n (`check_promotion` through `tag-entry-access-check`, `stock_denied` and
        # `business_query` through `tag-entry-resolve`), so those three run it here and
        # hand the caller the sub's own output item; the other ten delegate unchanged.
        #
        # It runs INSIDE this session on purpose - the resolver is a database service and
        # cannot be called without one. That leaves the session held across the resolver's
        # optional spec-search model call (2 to 3 s when `understand_phrase` fires), which
        # is the ONE place this turn breaks the plan's "never hold a session across
        # provider I/O" rule. Named rather than hidden: S6b moves fetch into its own stage
        # and is where the split belongs, because it adds the MCP call this lane does not
        # yet make.
        delegate = delegate_for(branch_kind, enabled_lanes)
        completes_here = delegate is None

        # S4: the low_signal lane finishes INSIDE the CRM, and its model call must not
        # run with a session open. Everything it needs from the database is read here,
        # while one already is; `_run_casual_lane` below does the rest with none.
        #
        # Gated on `completes_here`, not on the branch kind alone: while the lane is off in
        # `chatbot_completed_lanes` this turn belongs to n8n, and running the clarifier
        # anyway would spend a model call and the customer's time on an answer nobody
        # reads. Shadow mode compares the two lanes by REPLAYING captures, not by paying
        # for every live turn twice.
        clarifier_prompt: dict[str, Any] | None = None
        clarifier_config: Any = None
        clarifier_setup_error: str | None = None
        if branch_kind == "low_signal" and completes_here:
            try:
                resolved = casual.resolve_for_prompt(db, ctx=ctx)
                clarifier_prompt = casual.construct_user_prompt(ctx, resolved)
                clarifier_config = casual.resolve_clarifier_config(db)
            except Exception as exc:  # noqa: BLE001 - see below
                # Everything in this block exists to make the clarifier call possible: the
                # entities that go into its prompt, and the prompt / model / key it runs
                # on. A failure here is the same customer-visible event as the call itself
                # failing - the lane cannot answer - and AC-403 fixes what that looks like:
                # `stage = casual_llm`, `branch_kind` still `low_signal`, and today's
                # `sub-error-logger` text. Letting it reach `run_turn`'s catch-all instead
                # would null the branch kind and send another lane's error reply.
                logger.warning(
                    "chatbot turn %s: low_signal lane setup failed", turn_id, exc_info=True
                )
                clarifier_setup_error = str(exc)

        delegate_payload: dict[str, Any] | None = None
        lane_error_text: str | None = None
        # S6c: does the CRM FINISH this business turn, or hand the payload back to n8n?
        # Both switches are required, and they are independent on purpose:
        # `CHATBOT_BUSINESS_LANE_ENABLED` says the lane may RUN (S6a's shadow switch), and
        # `system_settings.chatbot_completed_lanes` says this arm may ANSWER. Deploy,
        # compare, switch on, cut n8n stays four reversible steps.
        business_completes = False
        if business.handles(branch_kind) and _business_lane_enabled():
            stage[0] = "looked_up"
            try:
                fragment = business.run_until_exit(
                    ctx,
                    item,
                    branch_kind=branch_kind,
                    services=business_services.production_services(db),
                    space_id=default_space_id(db),
                    probe_default_start=resolve_gate.default_probe_start(),
                    # D14, evaluated before anything side-effecting: the resolver's
                    # spec-search reader is the one row a test turn could still write.
                    dry_run=dry_run,
                )
            except Exception as lane_error:  # noqa: BLE001 - shadow until n8n is rewired
                # The lane is SHADOW while n8n still calls `sub-resolve-and-gate` itself,
                # so its failure must not take a turn n8n can still answer. It is recorded
                # loudly instead: the n8n cutover's own precondition is a shadow window
                # with zero of these (n8n-changes.md, S6a).
                logger.exception("chatbot turn %s: business lane failed", turn_id)
                lane_error_text = f"{type(lane_error).__name__}: {lane_error}"
                turn_trace.record(
                    "looked_up",
                    status="failed",
                    summary="Could not resolve what the customer named.",
                    why="The lookup the business lane depends on did not answer.",
                    facts={"lane": "business", "branch_kind": branch_kind},
                    error=lane_error_text,
                    raw=None,
                )
            else:
                payload: dict[str, Any] = fragment["payload"]
                # The lane names the n8n lane that would run this turn (all three arms
                # converge on `business_query`), and that is the right answer ONLY while
                # the turn is being handed back. `delegate_for` has already decided the
                # other case at the top of this block, and overwriting it there is what
                # made a completed turn still report a delegate.
                if not completes_here:
                    delegate = fragment["delegate"]
                delegate_payload = payload
                gate_block = payload.get("gate") or {}
                turn_trace.record(
                    "looked_up",
                    summary=(
                        "Resolved what the customer named and checked it against the "
                        f"{jsc.js_string(qf.get('domain_hint'))} domain."
                    ),
                    why=(
                        "The business lane decides whether the turn can be answered, needs "
                        "a choice from the customer, or found nothing."
                    ),
                    facts={
                        "exit": payload.get("_exit_kind"),
                        "gate_passed": gate_block.get("gate_passed"),
                        "gate_reason": gate_block.get("gate_reason"),
                    },
                    raw={"resolve_gate": payload},
                )

                # -- S6b: the fetch step, on the `continue` exit only ---------- #
                # The other three exits are answers in their own right: `access_ask`
                # needs a tier from the customer, `not_found` and `offer` have nothing
                # to look up. Only `continue` means "the gate is satisfied, go read".
                if payload.get("_exit_kind") != "continue":
                    # S6c: those three exits ARE answers, so the answer half runs on them
                    # straight away - `access_level_choice_message` for the tier ask, the
                    # gate's own picker for `offer`, the miss lane for `not_found`.
                    business_completes = completes_here
                else:
                    try:
                        fetch_fragment = business.run_fetch(
                            payload,
                            services=business_services.fetch_services(db),
                            dry_run=dry_run,
                            space_id=business_services.fetch_space_id(db),
                        )
                    except Exception as fetch_error:  # noqa: BLE001 - shadow, like above
                        logger.exception("chatbot turn %s: fetch step failed", turn_id)
                        lane_error_text = f"{type(fetch_error).__name__}: {fetch_error}"
                        # The CRM cannot answer this turn, so it goes to the n8n lane that
                        # still can - on an arm the owner has switched ON as much as on one
                        # he has not. A lane crash must not take a turn n8n can answer while
                        # its Switch output exists (the same shadow rule the outer handler
                        # states); after AC-610 deletes it, nothing answers either way and
                        # the turn is findable by `stage = 'looked_up'`.
                        delegate = fragment["delegate"]
                        turn_trace.record(
                            "looked_up",
                            status="failed",
                            summary="Could not look up an answer.",
                            why="The fetch step the business lane depends on did not answer.",
                            facts={"lane": "business", "step": "fetch"},
                            error=lane_error_text,
                            raw=None,
                        )
                    else:
                        delegate_payload = {**payload, "fetch": fetch_fragment.get("fetch")}
                        if fetch_fragment.get("kind") == "error":
                            # AC-604 / H11: "no tool matched" and "the read did not come
                            # back" are OUTCOMES, not silence. With the lane switched on
                            # the CRM answers them itself - `complete_answer`'s
                            # `_fetch_arm == "error"` branch renders the miss lane's
                            # not_found reply - and only while it is off does n8n answer,
                            # which is the case that still needs `lane_error_text` so
                            # `WHERE stage = 'looked_up'` finds the turn.
                            fetch_error_text = jsc.js_string(fetch_fragment.get("error"))
                            business_completes = completes_here
                            if not completes_here:
                                lane_error_text = fetch_error_text
                            turn_trace.record(
                                "looked_up",
                                status="ok" if completes_here else "failed",
                                summary="Found nothing to look the answer up with.",
                                why=(
                                    "No tool matched the question, or the read the answer "
                                    "needs did not come back."
                                ),
                                facts={
                                    "arm": fetch_fragment.get("_fetch_arm"),
                                    "outcome": fetch_fragment.get("outcome"),
                                },
                                error=fetch_error_text,
                                raw={"fetch": fetch_fragment.get("fetch")},
                            )
                        else:
                            business_completes = completes_here
                            turn_trace.record(
                                "looked_up",
                                summary=trace_mod.looked_up_summary(fetch_fragment)
                                if hasattr(trace_mod, "looked_up_summary")
                                else "Looked the answer up.",
                                why=(
                                    "One tool is chosen per turn and read once; the answer "
                                    "is rendered from what it returned."
                                ),
                                facts={
                                    "arm": fetch_fragment.get("_fetch_arm"),
                                    "tool": (
                                        (fetch_fragment.get("fetch") or {}).get("tool") or {}
                                    ).get("name"),
                                },
                                raw={"fetch": fetch_fragment.get("fetch")},
                            )
            stage[0] = "routed"

        # S6a review S1: a SHADOW lane failure must be findable without reading the trace
        # JSON. `error` and `status` stay as they are - the TURN did not fail, n8n still
        # answers it, and claiming otherwise would make every shadow blip look like a
        # customer-visible outage on the trace screen. What changes is `stage`, which
        # records how far the turn got: it stops at `looked_up` instead of reaching
        # `routed`, so `WHERE stage = 'looked_up' AND status IN ('delegated','done')` is
        # the operator's query, and `response.delegate_error` beside it carries the reason
        # (`ENTITY_PIN_MISMATCH` included, which arrives here as an AppException).
        # The lane the CRM is finishing is the exception: its turn is not over yet, so
        # closing it here would record a `done` turn before the reply exists (and
        # `_close_turn` is write-once). `_run_casual_lane` closes it after the clarifier
        # answers. With the lane switched off there is nothing to wait for and this closes
        # as `delegated`, exactly as it did before S4.
        if not (
            (branch_kind == "low_signal" and completes_here)
            or business_completes
        ):
            _close_turn(
                db,
                turn_id,
                status="delegated" if delegate else "done",
                stage="looked_up" if lane_error_text else "routed",
                branch_kind=branch_kind,
                error=None,
                records=turn_trace.records,
                # S2 / D15: a duplicate delivery replays THIS, so n8n's re-emitters never
                # see a null `ctx` or `item`. `actions` rides along because the caller must
                # not execute them twice either - it gets the original list and its own
                # Switch on `duplicate` decides to send nothing.
                response={
                    "ctx": ctx,
                    "item": item,
                    "actions": actions,
                    "delegate_payload": delegate_payload,
                    "delegate_error": lane_error_text,
                },
            )

    if business_completes and not lane_error_text:
        return _run_business_answer(
            turn_id=turn_id,
            ctx=ctx,
            item=item,
            branch_kind=branch_kind,
            actions=actions,
            payload=delegate_payload or {},
            dry_run=dry_run,
            session_factory=session_factory,
            turn_trace=turn_trace,
            stage=stage,
            space_id=space_id_for_turn,
        )

    if branch_kind == "low_signal" and completes_here:
        return _run_casual_lane(
            turn_id=turn_id,
            ctx=ctx,
            item=item,
            actions=actions,
            dry_run=dry_run,
            session_factory=session_factory,
            turn_trace=turn_trace,
            stage=stage,
            clarifier_prompt=clarifier_prompt,
            clarifier_config=clarifier_config,
            setup_error=clarifier_setup_error,
        )

    return TurnResult(
        turn_id=turn_id,
        ctx=ctx,
        item=item,
        branch_kind=branch_kind,
        delegate=delegate,
        delegate_payload=delegate_payload,
        actions=actions,
        # D14: on a dry run the response carries the would-be session patch. The HEAD
        # writes no session state at all, so there is nothing to patch yet and this is
        # null for every turn in S1; the tail (S2) is what fills it.
        session_patch=None,
        status="delegated" if delegate else "done",
        stage="looked_up" if lane_error_text else "routed",
    )


def _run_business_answer(
    *,
    turn_id: str,
    ctx: dict[str, Any],
    item: dict[str, Any],
    branch_kind: str,
    actions: list[dict[str, Any]],
    payload: dict[str, Any],
    dry_run: bool,
    session_factory: SessionFactory,
    turn_trace: Any,
    stage: list[str],
    space_id: str | None,
) -> TurnResult:
    """S6c's handover: the answer half plus the tail, with NO database session open.

    Split out of `_run_stages` for the same reason `_run_casual_lane` is: the capacity rule
    is visible in the signature rather than in a comment. This takes a `session_factory`,
    never a `Session`, so the two MCP probes and the family read cannot run with a routing
    connection held open (the 96/100-connection incident is the evidence).

    A failure here is the LANE's failure, not the engine's, exactly as S4 ruled for the
    clarifier: the turn keeps its `branch_kind`, fails at `stage = replied` (the answer
    half is what composes the reply), and the customer gets today's error reply. Letting it reach `run_turn`'s catch-all would null
    the branch kind and send the PARSER's error text, which is a different lane's words for
    a different failure.
    """
    stage[0] = "replied"
    close_turn_for_tail(
        turn_id,
        session_factory=session_factory,
        branch_kind=branch_kind,
        ctx=ctx,
        item=item,
        actions=actions,
        records=turn_trace.records,
    )
    try:
        completed = business.complete_answer(
            payload,
            turn_id=turn_id,
            ctx=ctx,
            item=item,
            branch_kind=branch_kind,
            services=business_services.answer_services_for(session_factory),
            session_factory=session_factory,
            space_id=space_id,
            dry_run=dry_run,
        )
    except Exception as exc:  # noqa: BLE001 - the lane's failure, with the lane's reply
        logger.exception("chatbot turn %s: business answer failed", turn_id)
        failed = f"{type(exc).__name__}: {exc}"
        reply = {"text": GENERIC_ERROR_REPLY, "quick_replies": []}
        answer_actions = [
            *actions,
            {
                "kind": "send_message",
                "text": GENERIC_ERROR_REPLY,
                "quick_replies": [],
                "dry_run": dry_run,
            },
        ]
        with _session(session_factory) as db:
            _close_turn(
                db,
                turn_id,
                status="failed",
                stage="replied",
                branch_kind=branch_kind,
                error=failed,
                records=turn_trace.records,
                response={"ctx": ctx, "item": item, "actions": answer_actions, "reply": reply},
            )
        return TurnResult(
            turn_id=turn_id,
            ctx=ctx,
            item=item,
            branch_kind=branch_kind,
            delegate=None,
            reply=reply,
            actions=answer_actions,
            session_patch=None,
            status="failed",
            stage="replied",
            error=failed,
        )

    return TurnResult(
        turn_id=turn_id,
        ctx=ctx,
        item=item,
        branch_kind=branch_kind,
        delegate=None,
        reply=completed.get("reply"),
        actions=completed.get("actions") or [],
        # D14: on a dry run the tail wrote nothing and hands back what it WOULD have
        # written, so a console or clone turn can be inspected.
        session_patch=completed.get("session_patch"),
        status=completed.get("status") or "done",
        stage=completed.get("stage") or "remembered",
    )


def _run_casual_lane(
    *,
    turn_id: str,
    ctx: dict[str, Any],
    item: dict[str, Any],
    actions: list[dict[str, Any]],
    dry_run: bool,
    session_factory: SessionFactory,
    turn_trace: Any,
    stage: list[str],
    clarifier_prompt: dict[str, Any] | None,
    clarifier_config: Any,
    setup_error: str | None = None,
) -> TurnResult:
    """The `low_signal` lane, from the model call to the closed turn (AC-401, AC-403).

    Split out of `_run_stages` so the "no DB session across LLM I/O" rule is visible in the
    signature rather than in a comment: this function takes a `session_factory`, never a
    `Session`, and opens one only after the provider has answered.

    `ClarifierError` is caught HERE and not by `run_turn`'s outer handler. Routing already
    succeeded, so the turn keeps `branch_kind = "low_signal"` and fails at
    `stage = "casual_llm"`; the outer handler would null the branch kind and send the
    generic parser-error reply, which is a different lane's text (AC-403).
    """
    stage[0] = "casual_llm"
    user_message = (
        casual.render_user_message(clarifier_prompt) if clarifier_prompt is not None else ""
    )

    # -- NO DB SESSION IS OPEN HERE ---------------------------------------- #
    # Every failure string here is TYPE-PREFIXED, and every test against it is
    # `is not None`. `str(exc)` alone is EMPTY for `ValueError("")` or a bare
    # `ClarifierError()`, and an empty string is falsy: `if failed` would read the turn as
    # a success, close the row `done`, and leave `error` as "" - a turn that failed,
    # recorded as fine, with nothing on the trace screen to say otherwise.
    failed: str | None = setup_error
    if failed is not None:
        # SETUP failure (the resolver, the registry, the AI config, the API key). The
        # customer gets a FIXED sentence, never `str(exc)`: these messages carry provider
        # detail and configuration names, and none of that belongs in a WhatsApp reply.
        # The real reason is on the row and on the trace, which is where an operator looks.
        text = casual.CLARIFIER_UNAVAILABLE_REPLY
    else:
        try:
            raw = casual.call_clarifier(clarifier_config, user_message)
            text = casual.reply_text(casual.central_exchange({"text": raw}))
        except casual.ClarifierError as exc:
            failed = f"{type(exc).__name__}: {exc}"
            # The CALL arm keeps today's `sub-error-logger` text, which interpolates the
            # error and has been what a customer sees on this path since it was written.
            # Parity, and the reason the two arms differ (divergences.py, H32).
            text = casual.CLARIFIER_ERROR_PREFIX + str(exc)
        except Exception as exc:  # noqa: BLE001 - a malformed answer is the same failure
            # The model answered but the answer was not usable (invalid JSON out of
            # `central_exchange`). Same lane, same stage, same reply: from the customer's
            # side there is no difference between "no answer" and "an answer I cannot read".
            failed = f"{type(exc).__name__}: {exc}"
            text = casual.CLARIFIER_ERROR_PREFIX + str(exc)

    actions = [
        *actions,
        {"kind": "send_message", "text": text, "quick_replies": [], "dry_run": dry_run},
    ]

    # The clarifier IS this lane's lookup: it is where the turn's answer comes from, the
    # way `sub-answer` is for the business lane. Recorded at `looked_up` rather than
    # `replied` so it does not collide with the `replied` record the tail writes below.
    turn_trace.record(
        "looked_up",
        status="failed" if failed is not None else "ok",
        summary=(
            _casual_failure_summary(failed, setup_error)
            if failed is not None
            else "The clarifier wrote small talk or one clarifying question."
        ),
        why=(
            "The turn carried no business question to look up, so the clarifier writes "
            "the reply."
        ),
        facts={
            "message_type": (clarifier_prompt or {}).get("message_type"),
            "model": getattr(clarifier_config, "model", None),
            "prompt_version": getattr(clarifier_config, "prompt_version", None),
            "resolved_entities": len((clarifier_prompt or {}).get("entities") or []),
        },
        error=failed,
        raw={"user_prompt": user_message},
    )

    if failed is not None:
        # AC-403: a failed clarifier is a FAILED turn, and the tail does not run. No
        # session is written (the customer's memory must not record an answer that was
        # never composed), and `branch_kind` stays `low_signal` because routing succeeded.
        reply = {"text": text, "quick_replies": []}
        with _session(session_factory) as db:
            _close_turn(
                db,
                turn_id,
                status="failed",
                stage="casual_llm",
                branch_kind="low_signal",
                error=failed,
                records=turn_trace.records,
                response={"ctx": ctx, "item": item, "actions": actions, "reply": reply},
            )
        return TurnResult(
            turn_id=turn_id,
            ctx=ctx,
            item=item,
            branch_kind="low_signal",
            delegate=None,
            reply=reply,
            actions=actions,
            session_patch=None,
            status="failed",
            stage="casual_llm",
        )

    # -- the tail, exactly the one every other lane will use ---------------- #
    # The row is closed `delegated` at `routed` FIRST, which is not bookkeeping: it is the
    # state the turn is genuinely in (a lane produced a result and the tail has not folded
    # it in yet), it is the state `complete_turn` refuses to run without, and it is what
    # the trace screen should show if this process dies between the two. It also puts the
    # `send_message` action on the row before the tail reads `prior_actions` off it, so a
    # duplicate delivery replays the action as well as the reply (D15).
    #
    # `answer` is `sub-answer`'s own return on this arm, reproduced exactly: its
    # `answer-result` node emits `{...central-exchange's output, outcome_fragment}`, and
    # the ITEM that reaches `sub-output` is that object - NOT `route-turn`'s item.
    #
    # The difference decides the reply. `build-outcome` reads `central-exchange` out of
    # `item.outcome_fragment`, and `complete_turn`'s entry gate runs `escalate-catalog`
    # only when the item carries a `branch_kind`. `sub-answer`'s output has none, so the
    # catalog is skipped and the compile-state ladder falls through to `central-exchange`.
    # Hand it `route-turn`'s item instead and the catalog runs, produces an empty
    # `response` for a kind it has no case for, and wins the ladder - the reply comes out
    # blank. The turn ROW keeps `low_signal` either way; `branch_kind` is read off the row.
    central = {"response": text}
    answer = {
        **central,
        "outcome_fragment": {
            "central-exchange": central,
            "build-miss-member-offer": None,
            "dym-annotate-partial": None,
        },
    }

    with _session(session_factory) as db:
        _close_turn(
            db,
            turn_id,
            status="delegated",
            stage="routed",
            branch_kind="low_signal",
            error=None,
            records=turn_trace.records,
            response={"ctx": ctx, "item": item, "actions": actions},
        )

    completed = complete_turn(
        turn_id,
        {"item": answer, "ctx": ctx, "answer": answer},
        session_factory=session_factory,
    )

    return TurnResult(
        turn_id=turn_id,
        ctx=ctx,
        item=item,
        branch_kind="low_signal",
        delegate=None,
        reply=completed.reply,
        actions=completed.actions,
        # D14: on a dry run the tail wrote nothing and hands back what it WOULD have
        # written, so a console turn can be inspected. On a live turn it is already saved.
        session_patch=completed.session_patch,
        status=completed.status,
        stage=completed.stage,
    )


def _casual_failure_summary(failed: str, setup_error: str | None) -> str:
    """One sentence for the trace screen, in the operator's words not the provider's.

    "Could not reach the clarifier" is wrong for the commonest setup failure by far - a
    missing API key or an unset AI-assistant config never reached anything, and telling an
    operator the model was unreachable sends them to look at the wrong system.
    """
    if setup_error is None:
        return "Could not reach the clarifier."
    lowered = failed.lower()
    if "api key" in lowered:
        return "The clarifier is not configured: no API key for its provider."
    if "configuration is not set" in lowered:
        return "The clarifier is not configured: the AI assistant settings are empty."
    return "Could not prepare the clarifier call."


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


def _business_lane_enabled() -> bool:
    """`CHATBOT_BUSINESS_LANE_ENABLED`, default FALSE.

    Off, the head behaves exactly as it did in S1: the three business arms delegate by
    name and carry no payload. On, they run the ported `sub-resolve-and-gate` in process
    and hand n8n its output item. It is a config flag rather than a `system_settings`
    column because it is a DEPLOYMENT step, not a tenant preference: it is turned on once
    per environment, in the same change that rewires n8n, and never again.
    """
    from app.config import settings

    return bool(getattr(settings, "chatbot_business_lane_enabled", False))


def _settings_row(db: Session) -> Any:
    """The `system_settings` singleton, read ONCE per turn.

    Both chatbot switches live on it, and both predicates below take the ROW rather than a
    session so the turn makes one query for the pair instead of one each.
    """
    from app.models.user import SystemSetting

    return db.query(SystemSetting).first()


def _stock_denial_enabled(db: Session, row: Any = _UNSET) -> bool:
    """R1: `system_settings.chatbot_stock_denial_enabled`, default false.

    Off, `isStockCheckDenied` is never evaluated and no turn can reach `stock_denied` or
    `demand_qty` - which is exactly as dead as those two lanes are today, by typo.

    Keeps its name and its leading `db` parameter because `test_engine_failure_paths.py`
    patches it by name with a one-argument lambda. `row` is how the caller passes the
    singleton it has already read; omit it and this reads its own, which is what that
    patched call site and any future caller get for free.
    """
    if row is _UNSET:
        row = _settings_row(db)
    return bool(getattr(row, "chatbot_stock_denial_enabled", False)) if row is not None else False


def _enabled_lanes(db: Session, row: Any = _UNSET) -> frozenset[str]:
    """`system_settings.chatbot_completed_lanes`: which lanes the CRM may FINISH.

    Empty by default, so a newly deployed lane delegates to n8n until the owner turns it
    on, and an absent settings row means "none" rather than "all" - the safe direction.
    """
    if row is _UNSET:
        row = _settings_row(db)
    return enabled_lanes_from(getattr(row, "chatbot_completed_lanes", None)) if row else frozenset()


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


# --------------------------------------------------------------------------- #
# The tail (S2). `complete_turn` is the second half of a delegated turn: the lane
# ran in n8n, and everything from "what did it build" to "what do we remember"
# happens here (AC-201).
# --------------------------------------------------------------------------- #

# What `sub-output`'s trigger declares, minus `item` and `ctx`. Every one is nullable and
# every one is a producer's whole output, verbatim, so the tail's by-name reads become
# named arguments (D1: the sub-workflow boundary was transport).
def close_turn_for_tail(
    turn_id: str,
    *,
    session_factory: SessionFactory,
    branch_kind: str,
    ctx: dict[str, Any],
    item: dict[str, Any],
    actions: list[dict[str, Any]],
    records: list[dict[str, Any]],
) -> None:
    """Close the row `delegated` at `routed`, the state `complete_turn` refuses to run without.

    Extracted so a lane that finishes in process (S4's `low_signal`, S6c's three business
    arms) can hand over to the tail without importing `_close_turn`'s private shape or
    opening its own session in the middle of a lane. Not bookkeeping: it is the state the
    turn is genuinely in while the tail has not folded the lane's result in yet, it is what
    the trace screen should show if the process dies between the two, and it puts this
    turn's actions on the row before the tail reads `prior_actions` off it (D15).
    """
    with _session(session_factory) as db:
        _close_turn(
            db,
            turn_id,
            status="delegated",
            stage="routed",
            branch_kind=branch_kind,
            error=None,
            records=records,
            response={"ctx": ctx, "item": item, "actions": actions},
        )


FRAGMENT_FIELDS: tuple[str, ...] = (
    "result",
    "resolved",
    "gate",
    "offer_hold",
    "suggest_offer",
    "not_found",
    "incoming_picker",
    "access_choice",
    "crossdomain_render",
    "answer",
    "clarify",
)


class CompleteResult:
    """What the `/complete` endpoint serialises."""

    __slots__ = ("turn_id", "reply", "actions", "session_patch", "status", "stage", "error")

    def __init__(self, **kwargs: Any) -> None:
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))
        if self.actions is None:
            self.actions = []

    def as_dict(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "reply": self.reply,
            "actions": self.actions,
            "session_patch": self.session_patch,
        }


def _load_turn(db: Session, turn_id: str) -> ChatbotTurn | None:
    return db.query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).first()


def _attachments_src(answer: Any) -> Any:
    """`send-attachments`'s own frozen expression, as a value.

    n8n reads `$("Call 'sub-answer'").first().json.outcome_fragment['central-exchange']`
    by name, which is why the attachment lane survived every rewiring. The CRM hands the
    same value back on `reply.attachments_src` so the node reads one field instead.
    """
    fragment = jsc.get(answer, "outcome_fragment")
    return jsc.get(fragment, "central-exchange") if isinstance(fragment, dict) else None


def complete_turn(  # noqa: PLR0915 - one linear pipeline, and the order IS the contract
    turn_id: str,
    fragments: dict[str, Any],
    *,
    session_factory: SessionFactory,
) -> CompleteResult:
    """Run the tail of one turn: outcome -> member offer -> state -> compose -> persist.

    `fragments` is the `sub-output` trigger contract: `item` plus the eleven nullable
    producer outputs, plus an optional `ctx` override. `ctx` normally comes off the turn
    row, which is where `/turn` persisted it - one less thing for the caller to keep
    consistent, and the only thing that makes a retry from the trace screen possible.

    **Dry run writes NOTHING (D14, AC-702's shape).** `is_test` was decided on the
    envelope at `/turn` and is read off the row here, so a console or clone turn cannot
    become a live write by calling a different URL. The response carries the would-be
    `session_patch` instead.

    **The session write is validated BEFORE it happens.** `SessionVars(extra="forbid")`
    is what stops a harness key leaking into a customer's session (H15, AC-203), and it
    has to raise before `overwrite_for_contact`, not after.
    """
    from app.services.chatbot import copy as copy_mod
    from app.services.chatbot.contracts import SessionVars
    from app.services.chatbot.tail import compose as compose_mod
    from app.services.chatbot.tail import member_offer as member_mod
    from app.services.chatbot.tail import outcome as outcome_mod
    from app.services.chatbot.tail.compile_state import compile_current_state

    item = fragments.get("item") or {}
    values = {name: fragments.get(name) for name in FRAGMENT_FIELDS}

    with _session(session_factory) as db:
        row = _load_turn(db, turn_id)
        if row is None:
            raise LookupError(f"chatbot turn {turn_id} not found")
        if row.status == "done" and isinstance(row.response, dict):
            # Idempotent, the same shape D15 gives a duplicate delivery: the tail already
            # ran and the caller already has an answer it must not send twice.
            stored = row.response
            return CompleteResult(
                turn_id=turn_id,
                reply=stored.get("reply"),
                actions=stored.get("actions") or [],
                session_patch=None,
                status=row.status,
                stage=row.stage,
            )
        if row.status != "delegated":
            # ONLY a delegated turn has a tail to run, and the guard is not tidiness.
            # A `failed` turn has no `ctx` and no lane, so running the tail on it would
            # compose an answer out of whatever `item.branch_kind` the CALLER's fragments
            # happened to carry - an answer decoupled from the real failure - WRITE it to
            # the customer's session, and overwrite `status` / `error` with `done` / null,
            # erasing the R4 / H32 record the trace screen exists to show. A `processing`
            # turn is the same hazard one moment earlier. Refused BEFORE the tail runs, so
            # nothing is composed and nothing is written.
            raise AppException(
                status_code=409,
                message="This turn cannot be completed.",
                detail=(
                    f"chatbot turn {turn_id} is {row.status!r} at stage {row.stage!r}, not "
                    "'delegated', so it has no lane result to fold in. A failed turn is "
                    "retried from the trace screen, never completed."
                ),
                code="CHATBOT_TURN_NOT_DELEGATED",
            )
        contact_respond_id = row.contact_respond_id
        dry_run = bool(row.is_test)
        stored_response = row.response if isinstance(row.response, dict) else {}
        ctx = fragments.get("ctx") or stored_response.get("ctx") or {}
        branch_kind = row.branch_kind
        prior_actions = list(stored_response.get("actions") or [])
        turn_trace = trace_mod.TurnTrace.resume(row.trace)
        canned = copy_mod.resolve(db)

        # EVERY failure in the tail closes the turn, the way R4 promises for every
        # other failure path: `failed` at `remembered`, with the reason on the row and
        # on the trace. Left unwrapped, an allowlist raise (AC-203) or a malformed
        # fragment leaves the row exactly as the HEAD wrote it - `delegated` at
        # `routed` - which reads on the trace screen as a turn still waiting for a lane
        # that finished minutes ago, and is the dropped turn H32 is about.
        try:
            # -- what this branch built ---------------------------------------- #
            producers: dict[str, Any] = {}
            for name, field in outcome_mod.CARRIER_FIELDS.items():
                if values.get(field) is not None:
                    producers[name] = values[field]

            outcome_input: dict[str, Any] = dict(item)
            # `entry-gate`: the escalate catalog runs only when the lane stamped a branch
            # kind on the item. Everything else goes straight to the outcome hub.
            if jsc.js_string(jsc.get(item, "branch_kind") or "") != "":
                catalog = outcome_mod.escalate_catalog(
                    item,
                    ctx,
                    canned,
                    not_found=values["not_found"],
                    incoming_picker=values["incoming_picker"],
                    access_choice=values["access_choice"],
                    suggest_offer=values["suggest_offer"],
                    gate=values["gate"],
                    offer_hold=values["offer_hold"],
                )
                producers["escalate-catalog"] = catalog
                outcome_input = catalog
                if outcome_mod.cs_offer_gate(catalog, ctx, values["gate"]):
                    plan = member_mod.cs_roster_plan(values["gate"])
                    rosters = member_mod.fetch_rosters(db, plan, ctx)
                    offer = member_mod.build_cs_member_offer(catalog, plan, rosters)
                    producers["cs-roster-plan"] = plan
                    producers["build-cs-member-offer"] = offer
                    outcome_input = offer

            outcome_items = outcome_mod.build_outcome([{"json": outcome_input}], producers)

            # -- what to say, and what to remember ------------------------------ #
            compiled = compile_current_state(
                outcome_items[0]["json"],
                ctx,
                resolved=values["resolved"],
                gate=values["gate"],
                execution_id=turn_id,
            )
            composed = compose_mod.crossdomain_compose(
                compiled.item,
                result=values["result"],
                answered=compiled.answered_domain is not None,
            )
            sealed = composed.get("reply") or {}
            session_patch = sealed.get("session_patch") or {}
            variables = session_patch.get("variables") or {}

            turn_trace.record(
                "replied",
                summary=trace_mod.replied_summary(sealed, branch_kind),
                why="The reply is composed from what the lane built, never from the customer's words.",
                facts={
                    "lane": branch_kind,
                    "quick_replies": bool(sealed.get("quick_replies")),
                    "rows_offered": len(variables.get("last_result_set") or []),
                    "cross_domain_block": composed is not compiled.item,
                },
                raw={"reply": sealed},
            )

            # AC-203 / H15: the allowlist is checked BEFORE anything is written. A key the
            # compiler should not be writing fails the turn here rather than landing in a
            # real customer's session, where nothing would ever notice it.
            SessionVars(**variables)

            # `ctx.session` is `get-session-vars`'s own body, so the previous variables sit
            # one level in. Same accessor the compiler uses, so "kept" on the trace screen and
            # "carried" in the compiler can never disagree about what was there before.
            remembered = trace_mod.memory_delta(
                before=jsc.get(jsc.get(jsc.get(ctx, "session"), "session_vars"), "variables") or {},
                after=variables,
            )
            if not dry_run:
                from app.services.conversation_variables_service import overwrite_for_contact

                overwrite_for_contact(db, respond_io_id=contact_respond_id, state=session_patch)
                _log_session_write(db, turn_id=turn_id, contact_respond_id=contact_respond_id)
            turn_trace.record(
                "remembered",
                summary=trace_mod.remembered_summary(remembered, dry_run=dry_run),
                why=(
                    "Nothing was written: this is a test turn (D14)."
                    if dry_run
                    else "The CRM is the only writer of the conversation state on the turn path (D2)."
                ),
                facts={
                    "kept": len(remembered["kept"]),
                    "new": len(remembered["new"]),
                    "cleared": len(remembered["cleared"]),
                    "dry_run": dry_run,
                },
                raw={"session_patch": session_patch},
            )

            reply = {
                "text": sealed.get("text"),
                "quick_replies": sealed.get("quick_replies"),
                # What `sub-sendmsg` and `send-attachments` reach for by name today, handed
                # back as fields so their expressions become one read each (AC-207).
                "result_set": variables.get("last_result_set"),
                "attachments_src": _attachments_src(values["answer"]),
            }
            _close_turn(
                db,
                turn_id,
                status="done",
                stage="remembered",
                branch_kind=branch_kind,
                error=None,
                records=turn_trace.records,
                response={
                    **stored_response,
                    "reply": reply,
                    "actions": prior_actions,
                },
            )
        except AppException:
            # The status guard above and anything else that has already NAMED its own
            # HTTP answer. Re-raised untouched: it did not run the tail, so there is
            # nothing to close and the row must keep the state it was refused in.
            raise
        except Exception as exc:  # noqa: BLE001 - a failed tail is recorded, never dropped
            message = f"{type(exc).__name__}: {exc}"
            logger.exception("chatbot turn %s failed in the tail", turn_id)
            turn_trace.record(
                "remembered",
                status="failed",
                summary="The answer could not be finished.",
                why="Something the tail depends on did not produce a usable result.",
                facts={"lane": branch_kind, "dry_run": dry_run},
                error=message,
                raw=None,
            )
            # The TAIL'S OWN session, rolled back first, not a fresh one. `rollback` is
            # what makes it usable again when the failure was a DB error, and is a no-op
            # when it was not (the allowlist raise is pure Python). A fresh session would
            # look tidier and be wrong: under the test fixture every session nests on one
            # connection, so a nested commit is discarded the moment the outer session
            # closes - the close would be reported and then silently undone.
            db.rollback()
            _close_turn(
                db,
                turn_id,
                status="failed",
                stage="remembered",
                branch_kind=branch_kind,
                error=message,
                records=turn_trace.records,
            )
            raise

    return CompleteResult(
        turn_id=turn_id,
        reply=reply,
        actions=prior_actions,
        # D14: the would-be patch, so a console or clone turn can be inspected without
        # anything having been written.
        session_patch=session_patch if dry_run else None,
        status="done",
        stage="remembered",
    )


def _log_session_write(db: Session, *, turn_id: str, contact_respond_id: str) -> None:
    """AC-206: the session write is logged where n8n's PUT used to be logged.

    Best-effort by the layering rule - a post-commit side effect never raises, because
    the write it describes has already happened and failing here would report a turn that
    did not answer when it did.
    """
    try:
        from app.schemas.integration import IntegrationLogCreate
        from app.services.integration_service import IntegrationLogService

        IntegrationLogService(db).create_integration_log(
            IntegrationLogCreate(
                integration_channel="n8n",
                business_table="respond_contacts.session_vars",
                business_id=turn_id,
                external_reference=contact_respond_id,
                direction="inbound",
                endpoint=f"/api/v1/external/chat/turn/{turn_id}/complete",
                http_method="POST",
                status_code=200,
                status="success",
            )
        )
    except Exception as log_error:  # noqa: BLE001
        logger.warning(
            "Failed to log the chatbot session write for turn %s: %s", turn_id, log_error
        )
