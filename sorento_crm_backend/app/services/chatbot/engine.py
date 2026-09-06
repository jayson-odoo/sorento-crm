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
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterator, Mapping

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.base import set_company_scope
from app.models.chatbot_turn import ChatbotTurn
from app.services.chatbot import dispatch, jsc, trace as trace_mod
from app.services.chatbot.contracts import (
    BUSINESS_BRANCH_KINDS,
    SELF_CLOSING_BRANCH_KINDS,
    TURN_FAILURE_STAGES,
    Envelope,
)
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
from app.services.chatbot.lanes import business, canned as canned_lanes, casual
from app.services.chatbot.lanes.escalation import run as run_escalation_lane
from app.services.chatbot.lanes.business import resolve_gate, services as business_services
from app.services.chatbot.usage import record_parser_usage
# Module level and by name, the same shape `app/api/v1/external/media.py` uses for its own
# enqueue-and-wait: the offload is one flag away from being the normal path, and a lazy
# import inside the branch would hide the dependency from anything reading this file.
from app.services.queue_service import cancel_job, enqueue_job, get_job_status, redis_conn

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]

# The branch kinds whose arm closes its OWN row, after its lane has produced an answer,
# AND for which `completes_here` alone is the whole question. Everything else closes at
# `routed` in the block below. `contracts` owns the list because `lanes/canned.py`
# subtracts the same one to know which kinds are ITS to compose.
#
# The business arms come off: they close their own row too, but whether they reach the
# arm that does is a SECOND question - the lane can be switched on and still hand the
# turn back (the resolver raised, the fetch was an outage, the exit was not an answer).
# `business_completes` is that answer and it sits beside this set in the guard, so a
# business turn that did not reach its answer half still closes as `delegated`.
_CRM_FINISHED_HERE: frozenset[str] = SELF_CLOSING_BRANCH_KINDS - BUSINESS_BRANCH_KINDS

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

# AC-703. The queue the offloaded turn runs on, classified `fast` in `worker.QUEUES`: a
# customer is watching "typing...", so it must never queue behind a 39-minute import.
CHAT_QUEUE = "chat"

# How often the waiting request looks at the job. Same order as `/external/media`'s own
# poll: short enough not to pad a fast turn, long enough not to spin.
WORKER_POLL_INTERVAL_SECONDS = 0.25


class TurnResult:
    """What the endpoint serialises. A plain object so the route stays a thin adapter."""

    __slots__ = (
        "turn_id",
        "is_test",
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
            "is_test": bool(self.is_test),
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
# Company scope. The engine calls ROUTE functions in process (the resolver, stock,
# promotions, product attachments), so the router dependency that stamps the caller's
# company scope onto the request session - `apply_company_scope` - never runs for them.
# An unstamped session reads UNSET, `build_company_predicate` compiles UNSET to
# `false()` for every owned model, and the turn answers "Couldn't find: <code>" for a
# product that exists in the contact's own company. Measured in prod and locally,
# 6 Sep 2026 (H56).
#
# So the turn resolves the contact's scope ONCE, from the SAME identity rule the
# X-API-Key path uses (`resolve_contact_company_scope`, shared with that dependency),
# and every session it opens afterwards carries it.
# --------------------------------------------------------------------------- #


def _contact_company_scope(factory: SessionFactory, contact_respond_id: str) -> frozenset:
    """The contact's companies, on a session of its own, before the turn starts.

    The lookup itself needs NO scope: `respond_workspaces`, `respond_contacts` and
    `respond_contact_companies` are plain `Base` models, none of them
    `CompanyScopedMixin`, so no scope filter applies to reading them (which is what
    makes resolving the scope from an unscoped session sound rather than circular).

    Fail-closed on every unhappy path: an unknown contact, a contact with no company
    row, no default workspace, or a lookup that raised all give an EMPTY frozenset
    (0 owned rows), never `None` (which would mean every company).
    """
    from app.services.company_scope_resolver import resolve_contact_company_scope

    db = factory()
    try:
        return resolve_contact_company_scope(db, contact_respond_id, default_space_id(db))
    except Exception:  # noqa: BLE001 - a scope lookup must never fail the turn
        logger.warning(
            "chatbot: company scope lookup failed for contact %s, failing closed",
            contact_respond_id,
            exc_info=True,
        )
        return frozenset()
    finally:
        db.close()


def _scoped_factory(factory: SessionFactory, scope: frozenset) -> SessionFactory:
    """`factory`, wrapped so every session it opens is stamped with `scope`.

    The FACTORY is wrapped rather than each of the engine's ~15 `_session` call sites
    changed, because the factory is also what the lanes get (`answer_services_for`
    opens its own session from it for the family read) - one seam covers both, and a
    session opened anywhere in the turn cannot be missed.
    """

    def open_scoped_session() -> Session:
        db = factory()
        set_company_scope(db, scope)
        return db

    return open_scoped_session


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


# O2 / AC-112: the keys a DRY-RUN envelope may carry so a harness can drive a turn with no
# LLM and none of the contact's real memory. Declared in ONE order, and that order is what
# `harness_keys_ignored` reports, so two traces diff readably.
#
# `Envelope` is `extra="allow"`, so they arrive as extras rather than as declared fields -
# deliberately: they are a HARNESS contract, not part of the envelope every injector sends,
# and declaring them would invite a live producer to start setting them.
#
# `prompt_overrides` (S8a, AC-807) joined at the end: `{prompt_key: version_id}`, so the
# Prompts screen can run a real turn against the version an operator is EDITING rather than
# the published one. It belongs here and not on the envelope proper for the same reason the
# other three do, plus one of its own - pinning an unpublished prompt version is exactly a
# live producer must never be able to do, and being dry-run-only is what guarantees it.
HARNESS_KEYS = (
    "mock_reformulator_output",
    "previous_conversation_state",
    "referenced_result_set",
    "prompt_overrides",
)


def _prompt_override(envelope: Envelope, prompt_key: str, *, dry_run: bool) -> str | None:
    """The version id this dry run pins for `prompt_key`, or None.

    Returns None on a LIVE turn whatever the envelope says. The harness keys are already
    ignored when `dry_run` is false, and this is the one whose leak would mean a customer
    answered by an unpublished prompt, so it is checked here as well rather than relying on
    the caller having checked.
    """
    if not dry_run:
        return None
    overrides = _harness_value(envelope, "prompt_overrides")
    if not isinstance(overrides, dict):
        return None
    value = overrides.get(prompt_key)
    return str(value) if value else None


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


def _select_turn(
    db: Session,
    *,
    contact_respond_id: str,
    message_id: str | None,
    is_test: bool | None = None,
):
    """The raw lookup. Kept separate from `_existing_turn` so the post-collision retry
    below can re-read WITHOUT going through whatever a test has wrapped around the public
    helper - the forced-TOCTOU test synchronises on `_existing_turn`, and a second trip
    through that barrier would deadlock the very path being fixed.

    The ORDER BY is the ONE place the "which row" question is answered, for the head and
    for the id-less `/turn/complete` alike (`find_turn_for_message`). The HIGHEST attempt
    wins, agreed with the n8n side: when S2b's retry puts a second row on a message, the
    retry is the row being watched, and completing (or replaying) the older one would fold
    a lane's result into a row nobody is looking at and leave the live one delegated
    forever; `created_at` breaks a tie for a row written before `attempt` was populated.

    **`is_test` narrows the pair to one WORLD (H57), and `None` means "either".** D15's
    dedup question is "has this respond message already been turned into a turn", and a
    TEST turn is not an answer to it: without the flag a dry run from the Prompts screen
    against a real contact shadowed the live delivery of that same `messageId`, which came
    back `duplicate: true` carrying the test row's canned reply, so the customer was sent
    nothing at all. The head therefore always passes its envelope's own `dry_run`; the
    id-less complete route passes nothing, because the body it holds does not say which
    world it is in and it must be able to complete either (a clone turn completes by body
    too). With both a test and a live row on one pair, that route gets the NEWEST, which
    is the turn whose lane result is arriving."""
    if message_id is None:
        return None
    filters = [
        ChatbotTurn.contact_respond_id == contact_respond_id,
        ChatbotTurn.message_id == message_id,
    ]
    if is_test is not None:
        filters.append(ChatbotTurn.is_test.is_(is_test))
    return (
        db.query(ChatbotTurn)
        .filter(*filters)
        # NEWEST first: with a retry there can be several rows for one message, and the
        # one that matters is the last one - the earlier attempts are settled history.
        # `attempt` leads because it is the retry's own counter (S2b writes old + 1), so
        # it answers the question directly; `created_at` only breaks a tie for a row
        # written before `attempt` was populated.
        .order_by(ChatbotTurn.attempt.desc(), ChatbotTurn.created_at.desc())
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


def find_turn_for_message(db: Session, *, contact_respond_id: str, message_id: str | None):
    """Which row is this message's turn? Asked by the ENDPOINT as well as by the head.

    The id-less `/turn/complete` identifies a turn from `(contact, respond message id)`,
    which is the same question `_existing_turn` asks on arrival, so it asks it through the
    same lookup instead of writing a second `ORDER BY`: the HIGHEST attempt, once for both
    readers. Two orderings over one pair would disagree about which row IS the turn the
    moment a second row for a message existed (S2b's retry), and the disagreement would
    surface as a lane result folded into a row nobody is watching. Public because
    `app/api/v1/external/chat.py` is a doorway file; the package still EXPORTS only
    `run_turn` / `complete_turn` (D3).
    """
    return _select_turn(db, contact_respond_id=contact_respond_id, message_id=message_id)


def _existing_turn(
    db: Session, *, contact_respond_id: str, message_id: str | None, is_test: bool = False
):
    """D15: has this respond message already been turned into a turn IN THIS WORLD?

    Checked with a SELECT rather than left to the unique index so a legitimate double
    delivery (webhook plus failover poller) costs a lookup, not an exception and an LLM
    call. The index is the real guarantee under concurrency, and the collision it raises
    is caught in `run_turn` - the SELECT alone is a TOCTOU window, not a lock.

    `is_test` is the envelope's own `dry_run` (H57): a test row must never make a live
    delivery a duplicate, nor the other way round. The unique index carries `is_test` for
    the same reason (migration 481).
    """
    return _select_turn(
        db,
        contact_respond_id=contact_respond_id,
        message_id=message_id,
        is_test=is_test,
    )


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


# The two states a turn ENDS in. `delegated` is not one of them: it is the handover the
# tail runs from, and the tail closes the row a second time when it finishes.
_TERMINAL_STATUSES = frozenset({"done", "failed"})


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
    """Write the turn's outcome. FIRST terminal write wins.

    Not tidiness: a failure inside the tail closes the row itself (`failed` at
    `remembered`, where it really stopped) and then RE-RAISES, and the lane handler that
    called it catches that same exception and closes again (`failed` at `replied`). The
    second write is strictly less true than the first - it names the stage of the caller
    rather than the stage of the failure - so it is refused rather than allowed to win.

    The `delegated` handover is deliberately NOT terminal: `close_turn_for_tail` writes it
    before the tail runs and `complete_turn` supersedes it with `done`, which is the
    two-phase close every completed lane makes.
    """
    assert stage is None or stage in TURN_FAILURE_STAGES, (
        f"{stage!r} is not a declared turn stage - a typo here lands in the column and "
        f"reads as an unknown state on the trace screen. Declared: {TURN_FAILURE_STAGES}"
    )
    row = db.query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).first()
    if row is None:  # pragma: no cover - the row was inserted two lines earlier
        return
    if row.finished_at is not None and row.status in _TERMINAL_STATUSES:
        # Debug, not warning: this is an EXPECTED sequence on the failure path (the tail
        # closes, re-raises, the lane handler catches), and an operator reading warnings
        # would be sent to look for a bug that is not there. What matters is that the row
        # keeps the first record; the second is only interesting when reading the log.
        logger.debug(
            "chatbot turn %s is already %s at %s; refused a second close as %s at %s",
            turn_id,
            row.status,
            row.stage,
            status,
            stage,
        )
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
    * the first turn `failed` BEFORE a lane owned it - the early stages (`intake`,
      `received`, `understood`, `access`) close the row with no `response` at all, so
      there is nothing to replay. A failure AFTER a lane owns the turn is different and
      deliberately so: both lane failure paths (`_run_business_answer`'s catch-all and
      the fetch-outage close in `_run_stages`) store the full shape, error reply
      included, so a duplicate of one of those replays the words the caller has already
      sent - which is exactly what stops it sending them twice.

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

    **`is_test` here is the ORIGINAL ROW's flag, not this call's envelope, and that is
    deliberate** (security review round 2, N5). Everywhere else the head stamps
    `result.is_test` from the CURRENT envelope, because the flag describes the call; on
    this path the whole answer describes the first turn, so its flag has to come from the
    same place its `reply` and `actions` do. Stamping the caller's flag on somebody else's
    answer would produce a result whose top-level field and whose per-action `dry_run`
    disagreed.

    Since H57 the two can no longer disagree anyway: the dedup lookup is narrowed to the
    envelope's OWN `is_test` (`_existing_turn`), so a duplicate is always a duplicate of a
    row from the same world and this flag always equals the caller's. The cross-world case
    the previous paragraph used to describe - a test envelope reading back `is_test: false`
    off a live row - is gone, because a test envelope for a message that already ran live
    now runs as its own turn instead of being answered from the customer's.
    """
    response = row.response if isinstance(row.response, dict) else {}
    return TurnResult(
        turn_id=str(row.id),
        is_test=bool(row.is_test),
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


def run_turn(
    envelope: Envelope, *, session_factory: SessionFactory, offload: bool | None = None
) -> TurnResult:
    """Run the head of one turn. NEVER raises for a business failure; records it.

    Three things happen before the stages, in this order and for these reasons: the D15
    dedup (a duplicate answers from the first turn and takes no ticket), the per-contact
    ticket (AC-709 - taken before the INSERT, because the insert is the widest thing that
    could reorder two messages a customer sent one after the other), and the row insert.
    Everything after that is wrapped, so an unexpected exception anywhere - a provider
    error while resolving config, an access-service failure, the stock predicate throwing
    on a contact with no `is_allowed_stock` field - closes the turn as `failed` with the
    stage it reached and hands the caller today's error reply. A turn left at `processing`
    with a null error and no trace is exactly the dropped turn H32 is about. The ticket is
    released in a `finally` around all of it.

    `offload` exists for ONE caller: the RQ job (`app/tasks/chat_turns.py`) passes `False`
    so the worker actually runs the turn instead of enqueuing it to itself forever. Every
    other caller leaves it None and gets whatever `CHATBOT_TURN_ON_WORKER` says.
    """
    contact_respond_id = _contact_respond_id(envelope)
    # H56. BEFORE the offload branch, so the invariant reads the same on every entry:
    # every session this turn opens - the dedup read, the stages, the lanes' own family
    # read, and the offload path's row close - carries the contact's company scope.
    # Resolved once, on a session of its own, from the same rule the X-API-Key
    # dependency uses. An unknown contact fails closed to zero rows.
    session_factory = _scoped_factory(
        session_factory, _contact_company_scope(session_factory, contact_respond_id)
    )

    if offload is None:
        offload = bool(getattr(settings, "chatbot_turn_on_worker", False))
    if offload:
        return _run_on_worker(envelope, session_factory=session_factory)

    turn_trace = trace_mod.TurnTrace()
    turn_trace.start()

    message_id = _message_id(envelope)
    dry_run = envelope.dry_run

    # ONE read of the settings singleton for the whole turn, and it happens HERE rather
    # than at routing because S7 mode is a settings column now (AC-810) and the ticket is
    # taken before the row insert. The snapshot travels into `_run_stages`, which used to
    # do this read itself: two reads would be a second round trip for no new information,
    # and worse, a turn could order itself under S7 mode and then route as though it were
    # off. Read on the session the dedup already needs, never on one of its own.
    switches = _TurnSwitches()
    ordered = False
    ticket: int | None = None
    redis = None
    try:
        with _session(session_factory) as db:
            switches = _read_switches(db)
            # H57: a DRY RUN takes no ticket, waits on nothing and marks nothing. The
            # ordering keys (`chatbot:seq|done|running:{contact}`, dispatch.py) are keyed
            # on the contact id and are SHARED with that contact's live traffic, so a test
            # turn run from the Prompts screen against a real contact would otherwise take
            # a real place in the queue the customer's next WhatsApp message waits on - and
            # a test turn must never delay a real customer. Nothing is lost: ordering
            # decides the order of REPLIES to one contact, and a dry run sends none.
            ordered = _s7_mode(db, switches) and not dry_run
            existing = _existing_turn(
                db,
                contact_respond_id=contact_respond_id,
                message_id=message_id,
                is_test=dry_run,
            )
            retrying = existing if _awaiting_retry(existing) else None
            if existing is not None and retrying is None:
                # D15: the two injectors delivered the same respond message. No second turn
                # runs, no second LLM call, and the caller's Switch on `duplicate` sends
                # nothing. NO TICKET has been taken at this point, on purpose: a duplicate
                # that took one and released it immediately would advance the counter past
                # a turn that is still running and let its successor start beside it.
                return _duplicate_result(existing)

            if ordered:
                # AC-709. The ticket is taken HERE - after the dedup read, before the row
                # INSERT - and the position is the guarantee. `chatbot.turns.created_at`
                # is this session's transaction start, i.e. the moment the request reached
                # the engine; taking the ticket after the insert instead left the whole
                # write between the two, and under a burst that window is tens of
                # milliseconds of connection setup and commit. Two messages 50 ms apart
                # then took their tickets in the WRONG order and the CRM answered them
                # backwards - measured, 2 inversions in 6 turns, by
                # `tests/chatbot/test_s7_poller_batch_order.py` before this moved.
                redis = _ordering_redis()
                try:
                    ticket = dispatch.contact_ticket(redis, contact_respond_id)
                except dispatch.ORDERING_ERRORS:
                    # Redis is not answering. Run the turn UNORDERED rather than failing
                    # it: out-of-order replies are a degradation, a chatbot that answers
                    # nothing is an outage, and until this flag existed a redis blip cost
                    # this path nothing at all.
                    logger.warning(
                        "chatbot ordering: redis is unavailable, running this turn for %s "
                        "unordered",
                        contact_respond_id,
                        exc_info=True,
                    )
                    ticket = None

            try:
                row = _insert_turn(
                    db,
                    envelope=envelope,
                    contact_respond_id=contact_respond_id,
                    retrying=retrying,
                )
            except IntegrityError:
                # The SELECT above is a TOCTOU window, not a lock: a webhook delivery
                # racing a poller re-delivery can both miss and both insert. The unique
                # index is the real guarantee, so the loser reads the winner's row rather
                # than 500ing. The ticket it took is released by the `finally` below.
                db.rollback()
                winner = _select_turn(
                    db,
                    contact_respond_id=contact_respond_id,
                    message_id=message_id,
                    is_test=dry_run,
                )
                if winner is None or _awaiting_retry(winner):
                    # Either some OTHER constraint failed, or two retries of one message
                    # raced - neither is a duplicate, and guessing would answer the
                    # customer from a turn that never ran.
                    raise
                return _duplicate_result(winner)
            turn_id = str(row.id)

        # The stage the turn is currently in, for the catch-all below. A plain list because
        # the inner stages update it and the handler reads it.
        stage: list[str] = ["received"]
        actions: list[dict[str, Any]] = []
        if ticket is not None:
            # `stage[0]` carries `queued` through the wait, so the handler below files a
            # `QueueWait` under the stage it actually happened in without a special case
            # (AC-710). The wait itself happens after the row exists, so a queue timeout is
            # a recorded turn and not a vanished one.
            stage[0] = "queued"
        try:
            if ticket is not None:
                try:
                    dispatch.wait_for_turn(
                        redis,
                        contact_respond_id,
                        ticket,
                        timeout_s=float(
                            getattr(settings, "chatbot_queue_wait_seconds", 45.0)
                        ),
                    )
                    dispatch.mark_running(redis, contact_respond_id, ticket)
                except dispatch.ORDERING_ERRORS:
                    # Redis went away mid-wait. Same call as above: answer unordered
                    # rather than not at all. `QueueWait` is NOT one of these and still
                    # fails the turn at `queued` - that one means the ordering worked and
                    # the predecessor was too slow, which is a real, recordable outcome.
                    logger.warning(
                        "chatbot ordering: redis is unavailable mid-wait, running turn "
                        "%s unordered",
                        turn_id,
                        exc_info=True,
                    )
                stage[0] = "received"
            result = _run_stages(
                envelope,
                session_factory=session_factory,
                turn_trace=turn_trace,
                turn_id=turn_id,
                contact_respond_id=contact_respond_id,
                dry_run=dry_run,
                actions=actions,
                stage=stage,
                switches=switches,
            )
            # D14: `is_test` is decided on the ENVELOPE, so it belongs on every answer the
            # head returns, whichever arm produced it. Stamped at this ONE exit rather than
            # on each arm's own `TurnResult`, which is exactly how three arms - the canned
            # block, `_run_casual_lane` and `_run_escalation_arm` - came to leave it false
            # on a turn that wrote nothing. Every action already carried its own `dry_run`;
            # this is the top-level field a caller switches the whole turn on. The worker
            # offload above rebuilds its result from a job that came through here, so it is
            # stamped too, and a duplicate reads `is_test` off the row it replays.
            result.is_test = dry_run
            return result
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
    finally:
        # AC-704. In a `finally`, and one that covers the ROW INSERT and the WAIT as well
        # as the stages, because the ONE thing worse than a failed turn is a failed turn
        # that never releases its ticket: every later message from that contact would then
        # wait out the whole queue window and fail as well, and the customer would watch
        # one broken turn break the conversation. The turn most in need of releasing is
        # the one that gave up waiting (AC-710) - it is the one whose predecessor may be
        # dead - and a `finally` on the stages alone would be the only one to skip it.
        #
        # `mark_done` is monotone, so releasing out of order can never rewind the counter.
        if ticket is not None:
            try:
                dispatch.mark_done(redis, contact_respond_id, ticket)
            except dispatch.ORDERING_ERRORS:
                # Best effort, same reasoning as the take above: if redis is down the next
                # turn for this contact cannot read the counter either, so it runs
                # unordered rather than waiting on a release that never lands.
                logger.warning(
                    "chatbot ordering: could not release ticket %s for %s",
                    ticket,
                    contact_respond_id,
                    exc_info=True,
                )


def _ordering_redis() -> Any:
    """The connection the ordering keys live on: the one the queues already use.

    Its `decode_responses=False` is why `dispatch._as_int` exists - the tests drive a
    decoding client and the engine does not, and a ticket counter that reads differently
    depending on who is asking would be the worst kind of intermittent.
    """
    return redis_conn


def _run_on_worker(envelope: Envelope, *, session_factory: SessionFactory) -> TurnResult:
    """AC-703. Run the turn on the `chat` queue and wait for it, inside this request.

    The caller's contract does not change: n8n still gets the finished turn on the same
    response. What changes is which process holds the LLM wait - an API thread, or a
    worker. Off by default; the trigger for turning it on is measured (the plan's capacity
    section: beyond ~250 concurrent turns the API threads, not the model, are the limit).

    Enqueue-and-wait is `app/api/v1/external/media.py`'s pattern, for its reason: a job
    row that outlives the request means a slow turn degrades into a recorded one rather
    than a hung socket.

    **What this does NOT do is raise the concurrency ceiling, and the flag's trigger has
    to be read that way.** `/external/media` waits on the event loop (`async def`,
    `asyncio.to_thread`, `asyncio.sleep`); this endpoint is synchronous, so the wait
    happens on the API's threadpool thread and that thread is occupied either way. What
    moves is the LLM call's CPU and memory, off the API process and onto a worker that can
    be scaled and restarted on its own. Making the wait free as well means making
    `/chat/turn` async, which is a change to the endpoint and not to this function; it is
    named in the plan's capacity section rather than done here, because the measured
    trigger for the offload has not arrived either. The connection half of the same
    problem IS fixed: the request no longer holds a database transaction while it waits.
    """
    # Imported HERE, not at module level: the task module imports this engine (it is the
    # thing it runs), so a top-level import is a cycle. `enqueue_job` and `get_job_status`
    # stay at module level because the tests patch them by name on this module.
    from app.tasks.chat_turns import run_turn_job

    job = enqueue_job(
        run_turn_job,
        envelope.model_dump(mode="json"),
        queue_name=CHAT_QUEUE,
        job_timeout=int(getattr(settings, "chatbot_turn_wait_seconds", 60)) * 2,
    )
    deadline = time.monotonic() + float(getattr(settings, "chatbot_turn_wait_seconds", 60))
    while True:
        snapshot = get_job_status(job.id) or {}
        state = snapshot.get("status")
        if state == "finished":
            result = snapshot.get("result")
            if isinstance(result, dict):
                return TurnResult(**result)
            return _worker_failed(
                envelope,
                session_factory,
                "the offloaded turn finished without returning a turn",
            )
        if state in ("failed", "stopped", "canceled"):
            return _worker_failed(
                envelope,
                session_factory,
                f"the offloaded turn {state}: {(snapshot.get('exc_info') or '')[:300]}",
            )
        if time.monotonic() >= deadline:
            # STOP the job before answering. Left running, the worker finishes the turn
            # minutes later and closes the row `done` or `delegated` - a row carrying an
            # answer nobody will ever send, because the caller has already sent the
            # apology, and (when it delegated) a ghost n8n will never complete.
            # `cancel_job` sends the stop command to a started job and cancels a queued
            # one; it swallows its own errors, including the race where the worker
            # finished a millisecond ago.
            cancel_job(job.id)
            return _worker_failed(
                envelope,
                session_factory,
                f"the offloaded turn did not finish within "
                f"{getattr(settings, 'chatbot_turn_wait_seconds', 60)}s",
            )
        time.sleep(WORKER_POLL_INTERVAL_SECONDS)


def _worker_failed(
    envelope: Envelope, session_factory: SessionFactory, message: str
) -> TurnResult:
    """The caller still gets today's error reply when the offloaded turn does not answer.

    The turn id is read back off the row the WORKER inserted, so the operator opening the
    trace screen lands on the turn that actually ran rather than on a job id that means
    nothing there. Empty only when the worker never got as far as inserting.

    **The row is CLOSED here, not left open.** H32's invariant is that no turn sits at
    `processing` with a null error: the caller has already been handed the apology, so a
    row still claiming to be in flight is the dropped turn this whole inbox exists to
    prevent. Closed `failed` at `queued`, the stage the turn genuinely reached from the
    API's point of view.

    Tolerant of the worker winning the race: a row that already has `finished_at` is left
    exactly as the worker wrote it. Its answer is not sent (the caller has the apology),
    but overwriting a finished trace with "the offload timed out" would erase what
    actually happened.
    """
    turn_id = ""
    try:
        with _session(session_factory) as db:
            row = _select_turn(
                db,
                contact_respond_id=_contact_respond_id(envelope),
                message_id=_message_id(envelope),
                # The row THIS envelope wrote, not the other world's row for the same
                # message (H57).
                is_test=envelope.dry_run,
            )
            if row is not None:
                turn_id = str(row.id)
                if row.finished_at is None:
                    _close_turn(
                        db,
                        turn_id,
                        status="failed",
                        stage="queued",
                        branch_kind=None,
                        error=message,
                        records=trace_mod.TurnTrace.resume(row.trace).records,
                        response=row.response if isinstance(row.response, dict) else None,
                    )
    except Exception:  # noqa: BLE001 - the reply matters more than the id
        logger.warning("chatbot offload: could not close the turn row", exc_info=True)
    logger.error("chatbot offload failed: %s", message)
    return _failed_result(turn_id, "queued", message, [], envelope.dry_run)


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
    switches: _TurnSwitches,
) -> TurnResult:
    """received -> understood -> access -> routed. Wrapped by `run_turn`.

    `switches` is the settings snapshot `run_turn` already read (AC-810): this function
    does not read the singleton itself, because S7 mode is needed before the ticket, which
    is before this runs.
    """
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
        parser_config = parser.resolve_config(
            db,
            current_date=_current_date_directive(),
            override_version_id=_prompt_override(envelope, parser.PROMPT_KEY, dry_run=dry_run),
        )

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
    parse_started = time.perf_counter()
    try:
        if parser_bypassed:
            parser_raw = _harness_value(envelope, "mock_reformulator_output")
        else:
            parser_raw = parser.parse(parser_config, user_block)
        # Empty on a bypassed parse: no call, no spend to record.
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
            # Always present, 0 when the parse was bypassed or the provider reported
            # nothing: a missing row reads as "free", which no LLM call is.
            "tokens": int(parser_usage.get("total_tokens") or 0),
            "parser_bypassed": parser_bypassed,
        },
        raw={"parser_raw": parse_block.get("_parser_raw"), "derived": qf},
    )

    # -- access + routed ---------------------------------------------------- #
    stage[0] = "access"
    # Set inside the block below when the CRM owns the turn and the fetch failed for a
    # reason that is not an absence; returned after the session closes, like every other
    # result this function hands back.
    hard_failure: TurnResult | None = None
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

        # The settings snapshot `run_turn` read on its first session. Named
        # `settings_row` because every helper below reads it with `getattr` and does not
        # care whether it was handed the ORM row or the snapshot of it.
        settings_row = switches
        stock_denial_enabled = _stock_denial_enabled(db, settings_row)
        enabled_lanes = _enabled_lanes(db, settings_row)
        # AC-810: both switches come off that same row, so the turn decides once and every
        # branch below reads a local boolean. Re-reading per branch would mean a query per
        # decision and, worse, a turn that could see the switch change halfway through it.
        s7_mode = _s7_mode(db, settings_row)
        business_lane_enabled = _business_lane_enabled(db, settings_row)
        # D5, once per turn: the respond workspace's own `space_id`, never n8n's hard-coded
        # 364817. Read HERE because S6c's probes run after this session has closed.
        space_id_for_turn = business_services.fetch_space_id(db)
        # AC-304: the configured unsupported-domain list, or None when the owner has set
        # none. `route.decide` owns the fallback to the two literals the JS hard-codes, so
        # None travels as an argument rather than as an absent one - one call shape, and
        # the default lives in exactly one file.
        branch_kind, tier_stamp = decide(
            ctx,
            stock_denial_enabled=stock_denial_enabled,
            unsupported_domains=_unsupported_domains(settings_row),
        )
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
        if delegate is None and business.handles(branch_kind) and not business_lane_enabled:
            # The settings row named a business arm, but `chatbot_business_lane_enabled`
            # (the lane's own switch, S6a) is off, so the block below never runs and
            # nothing in this build would answer the turn. Without this the turn closes
            # `done` at `routed` with no reply and no delegate - the silent turn H11 names,
            # reached through the settings form instead of through a bug. The two switches
            # are ordered on purpose (deploy, compare, switch on, cut n8n); this is what
            # makes the wrong order safe rather than silent.
            delegate = business.DELEGATE
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
                clarifier_config = casual.resolve_clarifier_config(
                    db,
                    override_version_id=_prompt_override(
                        envelope, casual.PROMPT_KEY, dry_run=dry_run
                    ),
                )
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
        # Set only when the CRM owns this turn (the lane is switched on) AND the fetch
        # failed for a reason that is not an absence: the customer gets the generic error
        # reply, not the miss lane's words. See the `error` arm below.
        fetch_failed_hard: str | None = None
        # S6c: does the CRM FINISH this business turn, or hand the payload back to n8n?
        # Both switches are required, and they are independent on purpose:
        # `system_settings.chatbot_business_lane_enabled` says the lane may RUN (S6a's
        # shadow switch), and `system_settings.chatbot_completed_lanes` says it may ANSWER. Deploy,
        # compare, switch on, cut n8n stays four reversible steps.
        business_completes = False
        if business.handles(branch_kind) and business_lane_enabled:
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
                # The same restore the fetch-raise handler below makes, and for the same
                # reason: `fragment` never bound here, so without this a turn on an arm the
                # owner has switched ON closes `done` with no reply AND no delegate - a
                # silent turn. The resolver is the seam the plan records as un-retried
                # (n8n retries `resolve-entity`, the port does not), so a transient failure
                # here is the expected case rather than the exotic one.
                delegate = business.DELEGATE
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
                        delegate = business.DELEGATE
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
                            # The `error` arm carries TWO different events and they get
                            # two different answers (captain's ruling, round 2):
                            #
                            # * `outcome == "not_found"` is a GENUINE ABSENCE - the
                            #   question was understood and no tool matches it. AC-604 /
                            #   H11: with the lane switched on the CRM answers it itself
                            #   through the miss lane, instead of the empty turn.
                            # * anything else is an INFRASTRUCTURE failure (MCP raised,
                            #   error envelope, tool search down). Telling the customer
                            #   "I could not find anything" would assert an absence the
                            #   read never established, so the turn is recorded `failed`
                            #   at `looked_up` with the generic error reply and R4's
                            #   manual retry. Live does the same: `Call 'sub-get-results'`
                            #   is `continueErrorOutput` into `set-ran-query-formulator`
                            #   ("There is some error encountered by the AI: ..."), never
                            #   into `not-found-error-message`.
                            #
                            # With the lane OFF both cases delegate, and `lane_error_text`
                            # is what makes `WHERE stage = 'looked_up'` find the turn.
                            fetch_error_text = jsc.js_string(fetch_fragment.get("error"))
                            absent = fetch_fragment.get("outcome") == "not_found"
                            business_completes = completes_here and absent
                            if not business_completes:
                                lane_error_text = fetch_error_text
                            if completes_here and not absent:
                                fetch_failed_hard = fetch_error_text
                            turn_trace.record(
                                "looked_up",
                                status="ok" if business_completes else "failed",
                                summary=(
                                    "Found nothing to look the answer up with."
                                    if absent
                                    else "Could not look the answer up."
                                ),
                                why=(
                                    "No tool matched the question."
                                    if absent
                                    else "The read the answer needs did not come back."
                                ),
                                facts={
                                    "arm": fetch_fragment.get("_fetch_arm"),
                                    "outcome": fetch_fragment.get("outcome"),
                                    # The reason belongs on the record either way; it is
                                    # only an ERROR on the turn nobody answers.
                                    "reason": fetch_error_text,
                                },
                                error=None if business_completes else fetch_error_text,
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
        # -- the lanes the CRM finishes itself (S3, AC-301) ------------------ #
        # Gated on `completes_here` exactly as the low_signal block above is: the code
        # half is `contracts.CRM_COMPLETED_BRANCH_KINDS` and the data half is
        # `chatbot_completed_lanes`, and `delegate_for` is the ONE place that reads both.
        if branch_kind in canned_lanes.COMPLETED_BRANCH_KINDS and completes_here:
            # `ideate` makes a TOOL call, so a failure there stops at `looked_up` the way
            # every other lookup does; the canned kinds have nothing to look up and go
            # straight to composing. The distinction is what the trace screen shows an
            # operator when an MCP call is what broke.
            stage[0] = "looked_up" if branch_kind == "ideate" else "replied"
            reply, session_patch, extra_actions = _complete_canned_lane(
                db,
                branch_kind=branch_kind,
                ctx=ctx,
                item=item,
                turn_id=turn_id,
                dry_run=dry_run,
                contact_respond_id=contact_respond_id,
                turn_trace=turn_trace,
            )
            actions = [*actions, *extra_actions]
            _close_turn(
                db,
                turn_id,
                status="done",
                stage="sent",
                branch_kind=branch_kind,
                error=None,
                records=turn_trace.records,
                response={"ctx": ctx, "item": item, "actions": actions, "reply": reply},
            )
            return TurnResult(
                turn_id=turn_id,
                ctx=ctx,
                item=item,
                branch_kind=branch_kind,
                # D4: the CRM finished it, so there is no lane left for n8n to run. Its
                # `head-arm` Switch reads exactly this and sends.
                delegate=None,
                actions=actions,
                reply=reply,
                # D14: the would-be patch on a dry run, so a console or clone turn can be
                # inspected without anything having been written.
                session_patch=session_patch if dry_run else None,
                status="done",
                stage="sent",
            )

        # A lane the CRM is FINISHING is the exception: its turn is not over yet, so
        # closing it here would record a `done` turn before the reply exists - and that
        # record would STAND, because `_close_turn` refuses a second terminal write. Each
        # such arm closes the row itself once its lane has answered - `_run_casual_lane`
        # after the clarifier, `_run_escalation_arm` after the handover,
        # `_run_business_answer` after S6c's answer half. With the lane switched off there
        # is nothing to wait for and this closes as `delegated`, exactly as it did before
        # S4. The S3 canned kinds are not in this set because their block above has
        # already returned.
        #
        # THREE outcomes, in this order, and the order is the contract (AC-715 sits
        # between two arms that both look like it and are not):
        #
        # 1. `fetch_failed_hard` - the CRM OWNS this turn (the lane is switched on, so
        #    `delegate` is None) and cannot answer it. A failure, not a misconfiguration.
        # 2. the S7 orphan guard - `delegate` is NOT None, so the turn was handed back,
        #    and in S7 mode there is nothing on the other side to take it. It fires only
        #    on a real delegate, which after S6c means a lane outside
        #    `chatbot_completed_lanes` (or one whose deployment flag is off, or one that
        #    raised) - a completed business turn has already set `delegate` to None above
        #    and reaches its answer half instead.
        # 3. everything else closes here at `routed`, as it always did.
        if fetch_failed_hard is not None:
            # The CRM owns this turn and cannot answer it. Recorded `failed` at the stage
            # it stopped, with the reply the caller sends, so the trace screen's Retry (R4:
            # manual, never automatic) has something to retry.
            hard_failure = _failed_result(
                turn_id,
                "looked_up",
                fetch_failed_hard,
                actions,
                dry_run,
                ctx=ctx,
                item=item,
                branch_kind=branch_kind,
            )
            _close_turn(
                db,
                turn_id,
                status="failed",
                stage="looked_up",
                branch_kind=branch_kind,
                error=fetch_failed_hard,
                records=turn_trace.records,
                response={
                    "ctx": ctx,
                    "item": item,
                    "actions": hard_failure.actions,
                    "reply": hard_failure.reply,
                    "delegate_payload": delegate_payload,
                    "delegate_error": fetch_failed_hard,
                },
            )
        elif delegate is not None and s7_mode and not dry_run:
            # S7 mode retires the n8n tail: `/turn/{id}/complete` answers 410 Gone, so a
            # turn that still delegates has NOBODY to finish it. Left `delegated` it would
            # sit as a ghost until the TTL sweep - ten minutes of a customer waiting for a
            # reply that no process is going to compose - so it is closed here, at the
            # stage it actually reached, with the reason an operator can act on and the
            # error reply the customer gets for every other failure.
            #
            # It is a MISCONFIGURATION, not a lane failure: the flag was turned on before
            # the CRM could complete this lane. R4's manual Retry applies unchanged, and it
            # is the right button - once the lane is in `chatbot_completed_lanes`, retrying
            # the original message answers it properly.
            #
            # LIVE turns only, and the exception is load-bearing rather than convenient. A
            # dry run has no customer waiting and nothing that would have completed it
            # either way: the clone's `test-guard` records actions and never calls
            # `/complete`, and the load gate posts `is_test` envelopes precisely to measure
            # the plumbing - the ticket, the wait, the row writes - which happen before this
            # point. Failing them would make the AC-711 gate, the shadow window and every
            # console turn unable to run in the mode they exist to prove out (measured: all
            # 30 turns of a gate run went red on this arm). The trace note below is written
            # for a dry run too, so the harness still SEES the lane it could not complete.
            stage[0] = "looked_up" if lane_error_text else "routed"
            # The message has to name the CAUSE, because it is read on a live outage and
            # acted on. Three of them reach here and they need different instructions:
            # the arm is not switched on, the arm IS switched on but its deployment flag
            # is not, or the lane ran and raised. Telling an operator to add a lane that
            # is already listed leaves them stuck on the settings form with the customer
            # still waiting.
            if (
                business.handles(branch_kind)
                and not business_lane_enabled
                and branch_kind in enabled_lanes
            ):
                orphan_error = (
                    f"S7 mode is on (system_settings.chatbot_ordering_enabled), so the "
                    f"CRM owns the tail and /complete is gone. {branch_kind!r} IS in "
                    f"system_settings.chatbot_completed_lanes, but the business lane's "
                    f"own switch chatbot_business_lane_enabled is off, so nothing in this "
                    f"build runs it. Turn the business lane on under Settings > Chatbot, "
                    f"or turn S7 mode off."
                )
            else:
                orphan_error = (
                    f"S7 mode is on (system_settings.chatbot_ordering_enabled), so the "
                    f"CRM owns the tail and /complete is gone, but the {delegate!r} lane "
                    f"is not completed in the CRM. Add {branch_kind!r} to "
                    f"system_settings.chatbot_completed_lanes on a build that can complete "
                    f"it, or turn S7 mode off."
                )
            if lane_error_text:
                # The lane IS completed by this build and still handed the turn back,
                # because it raised. Saying only "not completed in the CRM" would send an
                # operator to the settings form for a crash, so the reason travels too.
                orphan_error = (
                    f"{orphan_error} The lane handed this turn back after failing: "
                    f"{lane_error_text}"
                )
            logger.error("chatbot turn %s: %s", turn_id, orphan_error)
            turn_trace.record(
                stage[0],  # type: ignore[arg-type]
                status="failed",
                summary="The turn was routed to a lane the CRM cannot finish.",
                why=(
                    "S7 mode retires the n8n tail, so a lane that still delegates has "
                    "nobody left to complete it."
                ),
                facts={"lane": delegate, "s7_mode": True, "lane_completed_by_crm": False},
                error=orphan_error,
                raw={"item": item},
            )
            # Built BEFORE the close, exactly as the `fetch_failed_hard` branch above
            # does it and for the same two reasons: the row must record the apology the
            # customer was actually sent, so the trace screen shows the whole event, and
            # a D15 duplicate delivery replays that same reply and action list instead of
            # a bare `ctx`.
            orphan_failure = _failed_result(
                turn_id,
                stage[0],
                orphan_error,
                actions,
                dry_run,
                ctx=ctx,
                item=item,
                branch_kind=branch_kind,
            )
            _close_turn(
                db,
                turn_id,
                status="failed",
                stage=stage[0],
                branch_kind=branch_kind,
                error=orphan_error,
                records=turn_trace.records,
                response={
                    "ctx": ctx,
                    "item": item,
                    "actions": orphan_failure.actions,
                    "reply": orphan_failure.reply,
                    "delegate_payload": delegate_payload,
                    "delegate_error": lane_error_text,
                },
            )
            return orphan_failure

        if delegate is not None and s7_mode and dry_run:
            # See above: the turn is NOT failed, but the harness is told what would have
            # happened to a live one, so a shadow or clone run is what surfaces a lane that
            # is not ready before the flag reaches a customer.
            turn_trace.record(
                "routed",
                status="skipped",
                summary="A live turn on this lane would have no tail to go to.",
                why=(
                    "S7 mode retires the n8n tail, and this lane is not completed in the "
                    "CRM - a dry run is allowed through because nothing was going to "
                    "complete it either way."
                ),
                facts={"lane": delegate, "s7_mode": True, "lane_completed_by_crm": False},
                error=None,
                raw=None,
            )

        if fetch_failed_hard is None and not (
            (branch_kind in _CRM_FINISHED_HERE and completes_here) or business_completes
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

    if hard_failure is not None:
        return hard_failure

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

    if branch_kind == "out_of_scope" and completes_here:
        return _run_escalation_arm(
            turn_id=turn_id,
            ctx=ctx,
            item=item,
            actions=actions,
            dry_run=dry_run,
            session_factory=session_factory,
            turn_trace=turn_trace,
            stage=stage,
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
        is_test=dry_run,
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
        # AC-507: `quick_replies` is n8n's comma-joined string or null, never a list -
        # `sub-sendmsg` runs string methods on it, so a list is a send that never leaves.
        # This is the one path where the lane apologises to the customer, and in S7 mode
        # the caller executes these actions directly, so getting the type wrong here is
        # silence on an already-failed turn. Null, like every other hand-built site.
        reply = {"text": GENERIC_ERROR_REPLY, "quick_replies": None}
        answer_actions = [
            *actions,
            {
                "kind": "send_message",
                "text": GENERIC_ERROR_REPLY,
                "quick_replies": None,
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
        # AC-507: `quick_replies` is n8n's comma-joined string or null, never a list -
        # this lane offers none, so it is null, matching every other hand-built action.
        {"kind": "send_message", "text": text, "quick_replies": None, "dry_run": dry_run},
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
        # AC-507: null, not `[]` - the same string-or-null contract every other reply
        # carries (a failed clarifier never composed one).
        reply = {"text": text, "quick_replies": None}
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


def _run_escalation_arm(
    *,
    turn_id: str,
    ctx: dict[str, Any],
    item: dict[str, Any],
    actions: list[dict[str, Any]],
    dry_run: bool,
    session_factory: SessionFactory,
    turn_trace: Any,
    stage: list[str],
) -> TurnResult:
    """The `out_of_scope` lane, from the lane call to the closed turn (AC-501 to AC-505).

    `run_escalation_lane` is a module-level name so a test can replace it; the real one is
    `lanes.escalation.run`, whose `services` default builds the production bundle. The lane
    owns its own unit of work: the round-robin cursor and the SLA row must not roll back
    with the turn's routing transaction, because a person has already been told.

    A lane failure is a FAILED turn at `looked_up` with today's generic reply and NO
    partial assignment - the lane returns its whole action list or raises before returning
    any of it, so "assigned but no SLA row" is not a state this can produce.
    """
    stage[0] = "looked_up"
    try:
        # The lane opens its OWN session (its writes are a unit of work of their own), and
        # it opens it off THIS factory rather than `SessionLocal`, so the contact's company
        # scope travels into it (H56). Defence in depth: `post_next_assignee` pins its own
        # scope before it reads `Team` / `AgentTeam`, so the draw was not failing; the
        # pre-pin reads and the lane's unit of work were the unscoped half.
        fragment = run_escalation_lane(
            ctx, item, dry_run=dry_run, session_factory=session_factory
        )
    except Exception as exc:  # noqa: BLE001 - a failed lane is recorded, never dropped
        message = f"{type(exc).__name__}: {exc}"
        logger.exception("chatbot turn %s: escalation lane failed", turn_id)
        turn_trace.record(
            "looked_up",
            status="failed",
            summary="Could not hand the conversation to a person.",
            why="The assignment the escalation lane depends on did not complete.",
            facts={"lane": "out_of_scope", "dry_run": dry_run},
            error=message,
            raw=None,
        )
        with _session(session_factory) as db:
            _close_turn(
                db,
                turn_id,
                status="failed",
                stage="looked_up",
                branch_kind="out_of_scope",
                error=message,
                records=turn_trace.records,
                response={"ctx": ctx, "item": item, "actions": actions},
            )
        return _failed_result(turn_id, "looked_up", message, actions, dry_run)

    arm = fragment.get("arm")
    clarify = fragment.get("clarify")
    lane_actions = list(fragment.get("actions") or [])
    pending = fragment.get("pending")

    # Only `looked_up` is recorded here. `replied` and `remembered` are the TAIL's, and
    # recording a `replied` of our own would put two of them on the trace.
    turn_trace.record(
        "looked_up",
        summary=(
            "Asked which company should take it."
            if arm == "clarify"
            else "Handed the conversation to a person."
        ),
        why=(
            "More than one company was offered and nobody picked one, so assigning would "
            "have round-robined a pool the customer never chose."
            if arm == "clarify"
            else "The turn asked for a human, so the lane assigns one and starts the SLA clock."
        ),
        facts={
            "lane": "out_of_scope",
            "arm": arm,
            "actions": [a.get("kind") for a in lane_actions],
            "dry_run": dry_run,
        },
        raw={"clarify": clarify, "pending": pending},
    )

    # -- the tail, the same one every completed lane runs -------------------- #
    # n8n sends this arm through `tag-out-of-scope` -> `sub-output`, so the session IS
    # written today: the routing axes, and `escalate-catalog`'s `includeResponse: false`
    # state text ("Informed the user that request is out of scope..."). Skipping the tail
    # would have quietly dropped both the moment the lane was switched on.
    #
    # The item handed over is `tag-out-of-scope`'s, `{branch_kind: "out_of_scope"}` and
    # nothing else - NOT `route-turn`'s item. That is what makes `complete_turn`'s entry
    # gate run `escalate-catalog` for this arm, which is where the acknowledgement text
    # comes from. It stays a tail concern and is deliberately not one of the actions.
    #
    # The row is closed `delegated` at `routed` first: it is the state the turn is really
    # in (a lane produced a result, the tail has not folded it in), it is what
    # `complete_turn` refuses to run without, and it puts the actions on the row before the
    # tail reads `prior_actions` off it, so a duplicate replays them too (D15).
    all_actions = [*actions, *lane_actions]
    with _session(session_factory) as db:
        _close_turn(
            db,
            turn_id,
            status="delegated",
            stage="routed",
            branch_kind="out_of_scope",
            error=None,
            records=turn_trace.records,
            response={"ctx": ctx, "item": item, "actions": all_actions, "pending": pending},
        )

    completed = complete_turn(
        turn_id,
        {"item": {"branch_kind": "out_of_scope"}, "ctx": ctx, "clarify": clarify},
        session_factory=session_factory,
    )

    # -- seal the send actions with what the tail composed -------------------- #
    # `quick_replies` and `result_set` are the SEALED reply's, and they do not exist until
    # the tail has run - the lane declares the keys empty and they are filled here, so the
    # executor sees one `send_message` shape whoever built it. `attachments_src` is the
    # same story one step further: when the tail produced one, the send_attachments action
    # goes LAST, after both messages, which is the order `send-attachments` runs in today.
    sealed = completed.reply or {}
    final_actions = [_seal_send(a, sealed) for a in (completed.actions or [])]
    if jsc.truthy(sealed.get("attachments_src")):
        final_actions.append(
            {
                "kind": "send_attachments",
                "attachments_src": sealed.get("attachments_src"),
                "reply": sealed,
                "dry_run": dry_run,
            }
        )
    if final_actions != (completed.actions or []):
        # The row has to carry what the caller was handed, or a duplicate delivery replays
        # a different action list than the first turn produced (D15).
        with _session(session_factory) as db:
            row = db.query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).first()
            if row is not None and isinstance(row.response, dict):
                row.response = {**row.response, "actions": final_actions}
                db.commit()

    return TurnResult(
        turn_id=turn_id,
        ctx=ctx,
        item=item,
        branch_kind="out_of_scope",
        delegate=None,
        reply=completed.reply,
        actions=final_actions,
        # D14: on a dry run the tail wrote nothing and hands back what it WOULD have
        # written; on a live turn it is already saved.
        session_patch=completed.session_patch,
        status=completed.status,
        stage=completed.stage,
    )


def _seal_send(action: dict[str, Any], sealed: dict[str, Any]) -> dict[str, Any]:
    """Fill a `send_message`'s sealed halves from the tail's reply. Others pass through."""
    if action.get("kind") != "send_message":
        return action
    # AC-507/D9: n8n's `quick_reply` is a comma-joined STRING or null, never a list -
    # `or []` here would hand the sender a type its `quick_reply` input has never taken.
    # The sealed value wins when the tail composed one, and only then: a lane that built
    # its OWN quick replies (the escalation clarifies name the teams so the answer is a
    # tap) must not have them erased by a turn whose tail composed none. Same rule for
    # `result_set`, for the same reason.
    sealed_replies = sealed.get("quick_replies")
    sealed_set = sealed.get("result_set")
    return {
        **action,
        "quick_replies": sealed_replies if sealed_replies else action.get("quick_replies"),
        "result_set": sealed_set if sealed_set else action.get("result_set"),
    }


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
    """`route-turn`'s output item, byte-equal to today (AC-101).

    `stock_denied` also carries `not_allowed_check_stock: true` - n8n stamps it with a
    one-field `Edit Fields2` Set between the route Switch and `tag-entry-resolve`, and
    `sub-main-processing` reads it by that exact name. The CRM stamps it here rather than
    keeping a node-shaped Set of its own, so the item `sub-main-processing` receives is
    unchanged while that lane still delegates (S6 owns it).
    """
    from app.services.chatbot.contracts import TAG_ONLY_BRANCH_KINDS

    if branch_kind in TAG_ONLY_BRANCH_KINDS:
        return {"branch_kind": branch_kind}
    item = {**access, "branch_kind": branch_kind, **tier_stamp}
    if branch_kind == "stock_denied":
        item["not_allowed_check_stock"] = True
    return item


def _failed_result(
    turn_id: str,
    stage: str,
    error: str,
    actions: list[dict[str, Any]],
    dry_run: bool,
    *,
    ctx: dict[str, Any] | None = None,
    item: dict[str, Any] | None = None,
    branch_kind: str | None = None,
) -> TurnResult:
    """A failed turn still hands the caller today's error reply to send (AC-105, AC-107).

    `quick_replies` is null, never `[]`: AC-507's contract is `quick_reply` is n8n's
    comma-joined string or null, and a failed turn offered none.

    `ctx` / `item` / `branch_kind` default to None because most failures happen before
    they exist. A LANE failure has all three, and keeps them: the turn was routed, so
    nulling them would lose where it got to (S4's rule for the clarifier, and what D15's
    duplicate replay hands n8n's by-name re-emitters).
    """
    return TurnResult(
        turn_id=turn_id,
        is_test=dry_run,
        ctx=ctx,
        item=item,
        branch_kind=branch_kind,
        delegate=None,
        reply={"text": GENERIC_ERROR_REPLY, "quick_replies": None},
        actions=[
            *actions,
            {
                "kind": "send_message",
                "text": GENERIC_ERROR_REPLY,
                "quick_replies": None,
                "dry_run": dry_run,
            },
        ],
        status="failed",
        stage=stage,
        error=error,
    )


def _s7_mode(db: Session, row: Any = _UNSET) -> bool:
    """`system_settings.chatbot_ordering_enabled` - the CRM owns the whole turn.

    Ordering and tail-ownership are the same promote (the thin spine posts every message to
    `/turn` and the CRM answers it), so they are one switch; `app/api/v1/external/chat.py`
    reads the same column for the other half, the 410 on `/complete`. Its precondition is
    on the settings screen next to it: every lane the owner has switched on has to be one
    this build can complete before this goes on.

    A settings COLUMN since AC-810, read per turn off the row the turn has already read
    (`row`), because the owner flips it while watching live turns and an environment
    variable makes that a deploy. Same `db`-first signature as `_stock_denial_enabled`
    below, for the same reason: a caller with no row in hand still gets a correct answer.
    """
    if row is _UNSET:
        row = _settings_row(db)
    return bool(getattr(row, "chatbot_ordering_enabled", False)) if row is not None else False


def _business_lane_enabled(db: Session, row: Any = _UNSET) -> bool:
    """`system_settings.chatbot_business_lane_enabled`, default FALSE.

    Off, the head behaves exactly as it did in S1: the three business arms delegate by
    name and carry no payload. On, they run the ported `sub-resolve-and-gate` in process
    and hand n8n its output item. It stays independent of `chatbot_completed_lanes` (which
    says an arm may ANSWER) so deploy, compare, switch on and cut n8n remain four
    separately reversible steps.
    """
    if row is _UNSET:
        row = _settings_row(db)
    return (
        bool(getattr(row, "chatbot_business_lane_enabled", False)) if row is not None else False
    )


def _settings_row(db: Session) -> Any:
    """The `system_settings` singleton, read ONCE per turn.

    Every chatbot switch lives on it, and each predicate below takes the ROW rather than a
    session so the turn makes one query for all of them instead of one each.
    """
    from app.models.user import SystemSetting

    return db.query(SystemSetting).first()


@dataclass(frozen=True)
class _TurnSwitches:
    """The settings values one turn reads, snapshotted off the row at the first session.

    A SNAPSHOT rather than the ORM row, because the turn needs S7 mode before the ticket
    (in the dedup session) and the other four while routing (in a later one), and the row
    would be detached by then. Field names match the columns on purpose: every predicate
    below reads them with `getattr`, so the snapshot and the row are interchangeable and a
    caller with only a session still gets a correct answer.

    Read once means the switches cannot change halfway through a turn, which is the more
    important half: a turn that ordered itself under S7 mode and then routed as though it
    were off would have taken a ticket nobody releases.
    """

    chatbot_stock_denial_enabled: bool = False
    chatbot_unsupported_domains: Any = None
    chatbot_completed_lanes: Any = None
    chatbot_business_lane_enabled: bool = False
    chatbot_ordering_enabled: bool = False


def _read_switches(db: Session) -> _TurnSwitches:
    """One query for every switch the turn will consult. No row = every default."""
    row = _settings_row(db)
    if row is None:
        return _TurnSwitches()
    return _TurnSwitches(
        chatbot_stock_denial_enabled=bool(
            getattr(row, "chatbot_stock_denial_enabled", False)
        ),
        chatbot_unsupported_domains=getattr(row, "chatbot_unsupported_domains", None),
        chatbot_completed_lanes=getattr(row, "chatbot_completed_lanes", None),
        chatbot_business_lane_enabled=bool(
            getattr(row, "chatbot_business_lane_enabled", False)
        ),
        chatbot_ordering_enabled=bool(getattr(row, "chatbot_ordering_enabled", False)),
    )


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


def _unsupported_domains(row: Any) -> tuple[str, ...] | None:
    """`system_settings.chatbot_unsupported_domains` (AC-304), or None for the default.

    None rather than the default list, so `route.decide` owns the fallback in ONE place -
    returning the two literals here would put them in two files. Takes the row the turn
    has already read rather than querying again.
    """
    configured = getattr(row, "chatbot_unsupported_domains", None) if row else None
    return tuple(str(x) for x in configured) if isinstance(configured, list) else None


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

    __slots__ = (
        "turn_id",
        "reply",
        "actions",
        "session_patch",
        "status",
        "stage",
        "error",
        "is_test",
    )

    def __init__(self, **kwargs: Any) -> None:
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))
        if self.actions is None:
            self.actions = []
        self.is_test = bool(self.is_test)

    def as_dict(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "reply": self.reply,
            "actions": self.actions,
            "session_patch": self.session_patch,
            # The ROW's `is_test`, so the caller's test-guard reads one field here instead
            # of remembering what `/turn` said about this turn two calls ago.
            "is_test": self.is_test,
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
    source = jsc.get(fragment, "central-exchange") if isinstance(fragment, dict) else None
    return _clean_attachments(source)


def _clean_attachments(source: Any) -> Any:
    """One send per FILE, and a filename that says WHICH file it is.

    `source` is `central-exchange`'s own item - the ANSWER ENVELOPE - and the list the
    executor sends from is `envelope.attachments`, which is what `sub-send-attachments`'
    own `central-exchange` stub reads (`const a = n.first().json.attachments; return
    Array.isArray(a) ? a : []`). Every other shape passes through untouched, including the
    casual lane's `{response}` and a bare list.

    An attachment entry is `{url, filename, mimeType, attachmentType[, uploadedAt]}` and
    NOTHING else - measured over 7402 entries in the capture corpus, zero of which carry an
    id or a company. So:

    * **Identity is the `url`**, which is also the key the executor's own `Remove
      Duplicates` node uses, so the two halves cannot disagree about what a duplicate is.
    * **The company comes from the ROW that produced the file**, because the entry does not
      carry one. The envelope's rows do: each carries `company_name` and the values that
      name the thing the file belongs to. A row CLAIMS a file when one of its values is the
      filename, or is contained in it (a packing list is named after its container). When
      the claims line up one-for-one with the colliding files, they pair off in row order -
      the presenter appends attachments as it walks rows - and each file is qualified with
      its own company.

    When the claims do NOT line up, the files are left exactly as they arrived: an absence
    of evidence is not a licence to label one of them "Mocha". Measured on the corpus: of 91
    filename collisions between different urls, 56 attribute cleanly to two different
    companies and 35 carry no rows to attribute from.
    """
    if isinstance(source, dict):
        files = source.get("attachments")
        if not isinstance(files, list) or not files:
            return source
        return {**source, "attachments": _label_attachments(files, _company_rows(source))}
    if isinstance(source, list):
        return _label_attachments(source, [])
    return source


def _company_rows(envelope: Any) -> list[tuple[Any, list[str]]]:
    """`[(company_name, [values that identify this row])]`, in the envelope's own order."""
    items = envelope.get("items") if isinstance(envelope, dict) else None
    if not isinstance(items, list):
        items = envelope.get("answers") if isinstance(envelope, dict) else None
    rows: list[tuple[Any, list[str]]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        company: Any = None
        values: list[str] = []
        for field in item.get("fields") or []:
            if not isinstance(field, dict):
                continue
            key = jsc.nullish_str(field.get("key")).lower()
            value = field.get("value")
            if key == "company_name" or field.get("label") == "Company":
                company = value
            elif isinstance(value, str) and value.strip():
                values.append(value.strip())
        rows.append((company, values))
    return rows


def _claims(name: str, values: list[str]) -> bool:
    """Does a row carrying these values own the file called `name`?

    Equality first (a promotion row's value IS the flyer's filename), then containment for
    values long enough to be an identifier (a packing list is "<container> - WH.xlsx"). Six
    characters is the floor so a short code or a status word cannot claim a file by
    accident; nothing shorter appears as a container, shipment or product code.
    """
    return any(v == name for v in values) or any(len(v) >= 6 and v in name for v in values)


def _with_company(filename: str, company: Any) -> str:
    """"x.xlsx" + "Mocha" -> "x (Mocha).xlsx". BEFORE the suffix, never after it.

    WhatsApp picks the viewer off the extension, so a name ending in "(Mocha)" arrives as a
    file the phone does not know how to open.
    """
    stem, dot, suffix = filename.rpartition(".")
    label = f" ({jsc.js_string(company)})"
    if dot and stem and 1 <= len(suffix) <= 8 and " " not in suffix:
        return f"{stem}{label}.{suffix}"
    return f"{filename}{label}"


def _label_attachments(files: list, rows: list[tuple[Any, list[str]]]) -> list:
    """Dedupe on `url`, then qualify a surviving filename collision with its company."""
    kept: list[Any] = []
    seen_urls: set[Any] = set()
    for entry in files:
        if not isinstance(entry, dict):
            kept.append(entry)
            continue
        url = entry.get("url")
        if jsc.truthy(url):
            if url in seen_urls:
                continue
            seen_urls.add(url)
        kept.append(entry)

    groups: dict[str, list[int]] = {}
    for index, entry in enumerate(kept):
        if isinstance(entry, dict) and jsc.truthy(entry.get("filename")):
            groups.setdefault(jsc.js_string(entry.get("filename")), []).append(index)

    labelled = list(kept)
    for name, indexes in groups.items():
        if len(indexes) < 2:
            continue
        claims = [company for company, values in rows if _claims(name, values)]
        if len(claims) != len(indexes) or not all(jsc.truthy(c) for c in claims):
            continue  # nothing established: send them exactly as they arrived
        if len({jsc.js_string(c) for c in claims}) < 2:
            continue  # one company owns both: the suffix would be noise
        for index, company in zip(indexes, claims):
            entry = labelled[index]
            labelled[index] = {**entry, "filename": _with_company(name, company)}
    return labelled


def run_tail(
    db: Session,
    *,
    turn_id: str,
    ctx: Mapping[str, Any],
    item: Mapping[str, Any],
    values: Mapping[str, Any],
    canned: Any,
    branch_kind: str | None,
    dry_run: bool,
    contact_respond_id: str,
    turn_trace: trace_mod.TurnTrace,
    write_session: bool = True,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """outcome -> CS member offer -> compile-state -> compose -> validate -> persist.

    ONE tail, TWO callers. `complete_turn` runs it for a lane that ran in n8n, and
    `run_turn` runs it for a lane the CRM finished itself (S3) - and they must be the same
    code, because the whole claim of the port is that a turn's memory does not depend on
    which half of the migration answered it.

    `write_session` is the ONE thing a caller may vary, and it is not a dry-run flag:
    `access_denied` answers WITHOUT the tail's write on a live turn (n8n's `route[0]`
    goes straight to the send node and never reaches `compile-current-state`), and a
    contact refused the
    agent must not have the turn written into their memory. `dry_run` suppresses the write
    for a different reason (D14) and both suppress it independently.

    Returns `(reply, session_patch)`, where `session_patch` is `None` when the sealed
    reply carried no patch AT ALL - which is not the same as an explicit `{}` (a reset the
    compiler asked for, and still written). See the note at the read site: collapsing the
    two wiped a live customer's memory on a turn that never asked for it (H57). Raises
    before writing anything when the compiled variables carry a key outside the allowlist
    (AC-203).
    """
    from app.services.chatbot.contracts import SessionVars
    from app.services.chatbot.tail import compose as compose_mod
    from app.services.chatbot.tail import member_offer as member_mod
    from app.services.chatbot.tail import outcome as outcome_mod
    from app.services.chatbot.tail.compile_state import compile_current_state

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
    # H57: an ABSENT `session_patch` and an EXPLICIT `{}` are two different instructions,
    # and `or {}` collapsed them. `{}` is a RESET the compiler asked for and is written;
    # absent means the sealed reply carried no memory to save, and the only correct answer
    # to that is to leave the customer's remembered state exactly as it was. Under the old
    # default a lane that produced no state wiped it, which reads to the customer as the
    # bot forgetting the conversation mid-thread. `None` is what "no instruction" is called
    # from here down; every read of the patch below tolerates it.
    raw_patch = sealed.get("session_patch")
    session_patch = raw_patch if isinstance(raw_patch, dict) else None
    variables = (session_patch or {}).get("variables") or {}

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
    before_variables = (
        jsc.get(jsc.get(jsc.get(ctx, "session"), "session_vars"), "variables") or {}
    )
    remembered = trace_mod.memory_delta(
        before=before_variables,
        # With no patch there is no write, so the memory is KEPT exactly as it was.
        # Reporting the empty `variables` above as the "after" would file every remembered
        # value under `cleared` on the trace screen and describe a wipe that never happens.
        after=variables if session_patch is not None else before_variables,
    )
    written = (not dry_run) and write_session and session_patch is not None
    if written:
        from app.services.conversation_variables_service import overwrite_for_contact

        overwrite_for_contact(db, respond_io_id=contact_respond_id, state=session_patch)
        _log_session_write(db, turn_id=turn_id, contact_respond_id=contact_respond_id)
    turn_trace.record(
        "remembered",
        summary=trace_mod.remembered_summary(remembered, dry_run=dry_run),
        why=(
            "Nothing was written: this is a test turn (D14)."
            if dry_run
            else "Nothing was written: a refused turn is not remembered."
            if not write_session
            else "Nothing was written: this reply carried no state to save, so what was "
            "remembered before is kept."
            if session_patch is None
            else "The CRM is the only writer of the conversation state on the turn path (D2)."
        ),
        facts={
            "kept": len(remembered["kept"]),
            "new": len(remembered["new"]),
            "cleared": len(remembered["cleared"]),
            "dry_run": dry_run,
            "written": written,
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
    return reply, session_patch


def _send_actions(
    reply: Mapping[str, Any], *, dry_run: bool, preview: bool = False
) -> list[dict[str, Any]]:
    """The actions the CALLER executes for a finished turn, in order (D9).

    Shape agreed with the n8n executor, and it is the SEALED reply's own values verbatim,
    not a normalised copy of them:

    * `quick_replies` is `compile-current-state`'s `quick_reply` as it stands - n8n's
      comma-joined string, or null when the turn offered none. Coercing it to a list
      would hand `sub-sendmsg` a type its `quick_reply` input has never been given, and
      the sender is the half of this that did NOT move into the CRM.
    * `result_set` is `variables.last_result_set`, which is what the send node passes on
      so a numbered reply's rows travel with the message that numbered them.
    * `send_attachments` is a SECOND action and only when there is something to send.
      It carries the whole `reply` because `sub-send-attachments` reads more than one
      field off it, and it comes AFTER the message for the same reason n8n wires it that
      way: the text explains the files.

    `preview` adds AC-507's second flag, and only a lane that stood a seam value in sets
    it: the key is ABSENT on a live action and on a dry run whose text is real, exactly as
    the escalation lane emits it, so a reader never has to tell `preview: false` from
    "this build does not report it".
    """
    send: dict[str, Any] = {
        "kind": "send_message",
        "text": reply.get("text"),
        "quick_replies": reply.get("quick_replies"),
        "result_set": reply.get("result_set"),
        "dry_run": dry_run,
    }
    if preview:
        send["preview"] = True
    actions = [send]
    attachments = reply.get("attachments_src")
    if attachments is not None:
        attach: dict[str, Any] = {
            "kind": "send_attachments",
            "attachments_src": attachments,
            "reply": dict(reply),
            "dry_run": dry_run,
        }
        if preview:
            attach["preview"] = True
        actions.append(attach)
    return actions


def _complete_canned_lane(
    db: Session,
    *,
    branch_kind: str,
    ctx: Mapping[str, Any],
    item: Mapping[str, Any],
    turn_id: str,
    dry_run: bool,
    contact_respond_id: str,
    turn_trace: trace_mod.TurnTrace,
) -> tuple[dict[str, Any], dict[str, Any] | None, list[dict[str, Any]]]:
    """One of S3's eight lanes, answered inside the turn. `(reply, patch, actions)`.

    Two shapes, and the split is n8n's own graph rather than a convenience:

    * **`access_denied`** is answered by the SEND NODE's own expression - the `route`
      Switch's `access_denied` output goes STRAIGHT to
      `sorento-sub-respond-sendmsg-respond5` (there is no tag node on that arm) and never
      reaches `compile-current-state`. So the CRM composes that one string and runs
      no tail: a contact who is not allowed the agent must not have the turn written into
      their memory, and running the tail would write it.
    * **everything else** builds the `sub-output` fragments its lane would have handed the
      tail, and the S2 tail runs UNCHANGED. `ideate` supplies its reply through
      `item.outcome_fragment` - RS-6.1c's own mechanism and the exact key `build-outcome`
      reads - so the tail needs no ideate arm.

    The `sent` stage is recorded here and it is not a fiction: the CRM never sends (D9),
    it hands the caller a `send_message` action, and the trace records that hand-off so
    the operator screen shows where the turn ended.
    """
    from app.services.chatbot import copy as copy_mod
    from app.services.chatbot.lanes import ideate as ideate_mod

    canned = copy_mod.resolve(db)
    reply_extras: dict[str, Any] = {}
    # Only the `ideate` arm can set this: it is the one canned lane whose reply text comes
    # from a seam, so it is the one whose `send_message` stands a value in (AC-507).
    preview = False

    if branch_kind in canned_lanes.NO_SESSION_WRITE_BRANCH_KINDS:
        text = canned_lanes.access_denied_text(ctx, canned)
        reply = {"text": text, "quick_replies": None, "result_set": [], "attachments_src": None}
        session_patch: dict[str, Any] | None = {}
        turn_trace.record(
            "replied",
            summary=f"Refused: {trace_mod.lane_words(branch_kind).lower()}.",
            why="The contact is not granted the agent this turn would have used.",
            facts={"lane": branch_kind},
            raw={"reply": reply},
        )
        turn_trace.record(
            "remembered",
            summary="Nothing was remembered.",
            why="A refused turn is not written into the contact's memory.",
            facts={"lane": branch_kind, "written": False, "dry_run": dry_run},
            raw=None,
        )
    else:
        prev_variables = jsc.get(
            jsc.get(jsc.get(ctx, "session"), "session_vars"), "variables"
        ) or {}
        if branch_kind == "ideate":
            # D14 / H37: `dry_run` goes INTO the lane, not around it. The lane's seam is
            # an MCP write tool that mints a real idea record and pulls the contact's
            # media, so the guard has to sit before the call rather than after it.
            lane = ideate_mod.run(ctx, item, dry_run=dry_run)
            tail_item = lane["item"]
            reply_extras = lane["reply_extras"]
            preview = bool(lane.get("preview"))
            fragments: dict[str, Any] = {"item": tail_item}
        else:
            fragments = canned_lanes.fragments_for(branch_kind, item, ctx, prev_variables, canned)
            tail_item = fragments["item"]
        values = {name: fragments.get(name) for name in FRAGMENT_FIELDS}
        reply, session_patch = run_tail(
            db,
            turn_id=turn_id,
            ctx=ctx,
            item=tail_item,
            values=values,
            canned=canned,
            branch_kind=branch_kind,
            dry_run=dry_run,
            contact_respond_id=contact_respond_id,
            turn_trace=turn_trace,
        )
        reply = {**reply, **reply_extras}

    actions = _send_actions(reply, dry_run=dry_run, preview=preview)
    turn_trace.record(
        "sent",
        summary="Handed the reply to the caller to send.",
        why="The CRM never sends on the turn path; n8n owns respond.io egress (D9).",
        facts={"lane": branch_kind, "actions": len(actions), "dry_run": dry_run},
        raw={"actions": actions},
    )
    return reply, session_patch, actions


def complete_turn(  # noqa: PLR0915 - one linear pipeline, and the order IS the contract
    turn_id: str,
    fragments: dict[str, Any],
    *,
    session_factory: SessionFactory,
    compose_send_action: bool = False,
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

    `compose_send_action` is for a lane that finishes IN the CRM and only learns its own
    words here (S6c's business arms): it puts the `send_message` on the row before the row
    is closed, so the caller has something to send and a duplicate delivery replays it.
    Default FALSE, because `/complete` is n8n's path and n8n composes its own send.
    """
    from app.services.chatbot import copy as copy_mod

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
                is_test=bool(row.is_test),
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
        # H56, the tail's half. `/complete` is n8n's own entry, so this session comes
        # straight off `SessionLocal` and nothing has stamped a company scope on it -
        # which would empty the CS roster read below (`fetch_rosters` -> `list_team_roster`
        # walks `Team` / `AgentTeam`, both owned models) exactly the way it emptied the
        # resolver. The row's contact is the only identity a `/complete` call carries, and
        # it is the same one the head scoped by.
        #
        # UNCONDITIONAL, and the earlier "only when the session carries no scope yet"
        # version was wrong twice over: it cost an in-process caller nothing, but it made
        # the property untestable (`tests/conftest.py` defaults every new session to
        # Sorento, so the guard never fired under test) and it would silently skip a
        # session some other listener had stamped with a scope that is not this contact's.
        # Two indexed reads on a path that already makes an LLM call is not a cost worth
        # a conditional.
        set_company_scope(
            db, _contact_company_scope(session_factory, str(contact_respond_id or ""))
        )
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
            reply, session_patch = run_tail(
                db,
                turn_id=turn_id,
                ctx=ctx,
                item=item,
                values=values,
                canned=canned,
                branch_kind=branch_kind,
                dry_run=dry_run,
                contact_respond_id=contact_respond_id,
                turn_trace=turn_trace,
            )
            # D9: the caller SENDS; the engine hands it the action to send. Only a lane
            # that ASKED for it gets one: the `/complete` path is n8n's, and n8n composes
            # its own send (the world replays assert exactly that - a tail-composed action
            # there would be a second message). A lane that already knows its text builds
            # the action before the tail instead (S4's clarifier), which is why the
            # `send_message` guard below leaves it alone: one send per turn either way.
            # Built through `_send_actions`, the same builder `_complete_canned_lane` uses,
            # so a CRM-completed business answer carries `result_set` and its
            # `send_attachments` follow-up exactly as an n8n-completed one does.
            if (
                compose_send_action
                and isinstance(reply["text"], str)
                and reply["text"]
                and not any(a.get("kind") == "send_message" for a in prior_actions)
            ):
                prior_actions = [*prior_actions, *_send_actions(reply, dry_run=dry_run)]
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
                    # D15: the duplicate replay must hand back the SAME action list the
                    # first delivery got, so the send rides on the row too.
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
        is_test=dry_run,
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
