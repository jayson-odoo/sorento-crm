"""CHAT-INBOX-QUEUE: the CRM owns each contact's message queue.

Plan `documentation/plans/chatbot/PLAN-chat-inbox-queue.md` (Final rules 1-8), UAC
`chat-inbox-queue-acceptance-criteria.md`. With `chatbot_direct_ingress_mode` covering a
contact, every injector of that contact's messages (the respond.io webhook, n8n's
`/chat/turn`: spine, INJECT and Retry) only ENQUEUES: it inserts the message's turn row at
status `queued`, or finds it there (the unique key on `chatbot.turns`), and answers at once.
Nobody waits on a turn, so a deploy has no long request to cut.

A drain per contact, on the API process's bounded direct-turn pool
(`app/tasks/chat_turns.py::_submit`), answers the rows: one drain per contact across every
process (a Redis mutex kept alive by a heartbeat, `chatbot:drain:{contact}`), oldest SEND
time first (`send_order.send_key_ms`), the takeover check, the turn (`engine.run_turn`),
the sender POST (`direct_ingress.send_outcome`), then the done mark. No clamp, no ticket.

Row states: `queued` -> `processing` (claimed) -> stage `sending` (stamped BEFORE each
sender POST) -> `done` or `failed`. A row this module owns carries an `inbox` fact on its
first trace record, which is how recovery tells it from a sync-path turn in flight.

Three rules that make it safe:

* **Look-ahead** (rule 4). Right before the turn writes conversation state, or closes, the
  engine calls `checkpoint`: when an EARLIER-sent message of the contact is queued, the turn
  yields (`TurnYielded`) with nothing written, its row goes back to `queued`, and the drain
  takes the earlier one first.
* **Never lose** (rule 5). Rows live in Postgres. `sweep` (every API process, at start-up
  and every `SWEEP_INTERVAL_SECONDS`) kicks a drain for every contact with queued rows and
  no live mutex; a drain that takes the mutex first recovers the rows a dead process left
  `processing`.
* **Never double-answer** (rule 6). A dead row with no POST attempted runs again; one at
  stage `sending` is re-sent only when `should_resend` says so, otherwise it is flagged for
  staff (`failed`, stage `send_unconfirmed`).
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any, Callable

from sqlalchemy import func, or_, text, update
from sqlalchemy.exc import IntegrityError

from app.models.chatbot_turn import ChatbotTurn
from app.services.chatbot import direct_ingress, send_order
from app.services.chatbot import trace as trace_mod

logger = logging.getLogger(__name__)


QUEUED = "queued"
CLAIMED_STAGE = "received"
SENDING_STAGE = "sending"
SEND_UNCONFIRMED_STAGE = "send_unconfirmed"
INBOX_MARKER = [{"facts": {"inbox": True}}]
# The states a row this module owns is in while it is not finished.
OPEN_STATUSES = ("processing", "delegated")

# The mutex lives as long as `dispatch`'s alive stamp (clears the redis socket timeout)
# and is refreshed on the same beat.
MUTEX_TTL_SECONDS = 15.0
HEARTBEAT_INTERVAL_SECONDS = 4.0
# A single row held longer than this is hung: the heartbeat stops so another process can
# recover the contact (the claim fence keeps that to one answer).
MAX_ROW_HOLD_SECONDS = 900.0
SWEEP_INTERVAL_SECONDS = 1.5
# A refused connection proves nothing left, so it is sent again, a bounded number of times.
MAX_SEND_ATTEMPTS = 3
RESEND_BACKOFF_SECONDS = 0.5
# IQ-33: a loop guard far above any human rate.
MAX_QUEUED_PER_CONTACT = 200
# IQ-31: a failed takeover lookup backs the contact off 1, 2, 4 ... seconds, up to this.
LOOKUP_BACKOFF_MAX_SECONDS = 60.0

_REFRESH_LUA = (
    "if redis.call('GET', KEYS[1]) == ARGV[1] then "
    "return redis.call('PEXPIRE', KEYS[1], ARGV[2]) else return 0 end"
)
_RELEASE_LUA = (
    "if redis.call('GET', KEYS[1]) == ARGV[1] then "
    "return redis.call('DEL', KEYS[1]) else return 0 end"
)


class TurnYielded(BaseException):
    """The running turn gives way, with nothing written: to an earlier-sent queued message
    (look-ahead), or because its photo read is still pending or shutdown began (parked).

    A BaseException on purpose: every `except Exception` in the engine and its lanes turns
    a failure into an error reply and a closed row, and a yield must pass all of them."""


class ClaimLost(BaseException):
    """This drain no longer owns the row (its claim was recovered and re-claimed after the
    mutex was lost): it stops with nothing written and posts nothing (IQ-29)."""


class InboxFull(Exception):
    """The contact already has `MAX_QUEUED_PER_CONTACT` queued rows (IQ-33)."""


# --------------------------------------------------------------------------- #
# Process state
# --------------------------------------------------------------------------- #

_cv = threading.Condition()
_shutting_down = threading.Event()
_active = 0
_local = threading.local()
_sweeper: threading.Thread | None = None
_sweeper_stop = threading.Event()
# When this process last ran a row of a contact: the sweep re-arms the least recently
# served contact first, so a long backlog cannot keep the pool from another (IQ-30).
_last_served: dict[str, float] = {}


class _RowRun:
    """The row the current drain thread is running, read by the engine's seams."""

    def __init__(
        self, turn_id: str, contact: str, send_key: float | None, claimed_at: Any, factory: Callable[[], Any]
    ):
        self.turn_id = turn_id
        self.contact = contact
        self.send_key = send_key
        self.claimed_at = claimed_at
        self.factory = factory
        # Set once a checkpoint found nothing earlier: from then on the turn writes and
        # posts, so it may not yield any more.
        self.committed = False
        # The engine's own close (status, stage), applied after the POST.
        self.close: tuple[str, str | None] | None = None


def current_run(turn_id: str | None = None) -> _RowRun | None:
    run = getattr(_local, "run", None)
    if run is None or (turn_id is not None and str(turn_id) != run.turn_id):
        return None
    return run


def draining() -> bool:
    """Is this thread running a turn for the inbox drain?"""
    return getattr(_local, "run", None) is not None


def shutting_down() -> bool:
    return _shutting_down.is_set()


def inbox_records(trace: Any) -> list[dict[str, Any]]:
    """The records this module put on a row's trace (they carry the `inbox` fact)."""
    return [
        r
        for r in (trace or [])
        if isinstance(r, dict) and isinstance(r.get("facts"), dict) and r["facts"].get("inbox")
    ]


# --------------------------------------------------------------------------- #
# The switch, enqueue, kick
# --------------------------------------------------------------------------- #


def queue_mode_for(db: Any, contact_respond_id: str) -> bool:
    """True when the direct-ingress switch covers this contact."""
    from app.models.user import SystemSetting

    return direct_ingress.covers(db.query(SystemSetting).first(), str(contact_respond_id or ""))


def contact_of(envelope: Any) -> str:
    """The respond.io contact id the queue files this envelope under."""
    from app.services.chatbot import engine

    return engine._contact_respond_id(envelope)


def _from_the_customer_on_whatsapp(body: Any) -> bool:
    """IQ-32: the webhook's structural gates, for `/chat/turn`'s copy: an incoming message,
    not from a staff or bot sender, on WhatsApp. No stale cut: a failover copy still queues."""
    from app.services.chat_history_ingest_service import normalise_channel

    body = body if isinstance(body, dict) else {}
    message = body.get("message") if isinstance(body.get("message"), dict) else {}
    if str(message.get("traffic") or "").strip().lower() != "incoming":
        return False
    sender = message.get("sender") if isinstance(message.get("sender"), dict) else {}
    if str(sender.get("source") or "").strip().lower() in direct_ingress.STAFF_SENDER_SOURCES:
        return False
    channel = body.get("channel") if isinstance(body.get("channel"), dict) else {}
    return normalise_channel(channel.get("source") or channel.get("type")) == "whatsapp"


def accepts(db: Any, envelope: Any) -> bool:
    """Does this `/chat/turn` envelope go to the queue? A live customer WhatsApp message of
    a covered contact, with a sender to answer through and on the default workspace (the
    sender speaks for that one only). Test and console turns never do."""
    from app.services.chatbot import engine

    if envelope.dry_run or envelope.ingress == "console":
        return False
    contact = engine._contact_respond_id(envelope)
    if not contact or engine._message_id(envelope) is None:
        return False
    if not _from_the_customer_on_whatsapp(envelope.message):
        return False
    if not queue_mode_for(db, contact):
        return False
    if not direct_ingress.sender_configured(db):
        return False
    return direct_ingress._on_default_workspace(db, contact)


def _queued_trace() -> list[dict[str, Any]]:
    record = trace_mod.TurnTrace()
    record.start()
    record.record(
        "queued",  # type: ignore[arg-type]
        status="ok",
        summary="Queued in this contact's inbox.",
        why="The CRM answers a contact's messages one at a time, in the order they were sent.",
        facts={"inbox": True},
    )
    return record.persisted()


def _queued_count(db: Any, contact: str) -> int:
    return int(
        db.query(func.count(ChatbotTurn.id))
        .filter(
            ChatbotTurn.contact_respond_id == contact,
            ChatbotTurn.status == QUEUED,
            ChatbotTurn.is_test.is_(False),
        )
        .scalar()
        or 0
    )


def enqueue(db: Any, envelope: Any) -> tuple[str, bool]:
    """Insert this message's `queued` row, or find the one already there. Never runs it.

    Returns `(turn_id, created)`. A failed row an operator asked to retry gets its next
    attempt queued (the Retry copy), once however many copies arrive. Raises `InboxFull`
    past `MAX_QUEUED_PER_CONTACT` queued rows (logged as an error)."""
    from app.services.chatbot import engine

    contact = engine._contact_respond_id(envelope)
    message_id = engine._message_id(envelope)
    existing = engine._select_turn(db, contact_respond_id=contact, message_id=message_id, is_test=False)
    retrying = existing if engine._awaiting_retry(existing) else None
    if existing is not None and retrying is None:
        return str(existing.id), False
    if _queued_count(db, contact) >= MAX_QUEUED_PER_CONTACT:
        logger.error(
            "chatbot inbox: %s already has %s queued rows; message %s is not queued",
            contact,
            MAX_QUEUED_PER_CONTACT,
            message_id,
        )
        raise InboxFull(contact)
    row = ChatbotTurn(
        contact_respond_id=contact,
        message_id=message_id,
        ingress="retry" if retrying is not None else envelope.ingress,
        envelope=trace_mod.cap_document(envelope.model_dump(mode="json")),
        is_test=False,
        status=QUEUED,
        stage=QUEUED,
        attempt=(retrying.attempt + 1) if retrying is not None else 1,
        trace=_queued_trace(),
        started_at=engine._now(),
    )
    db.add(row)
    if retrying is not None:
        retrying.retry_requested_at = None
    try:
        db.commit()
    except IntegrityError:
        # Two copies raced past the SELECT; the unique key kept one row.
        db.rollback()
        winner = engine._select_turn(db, contact_respond_id=contact, message_id=message_id, is_test=False)
        if winner is None:
            raise
        return str(winner.id), False
    return str(row.id), True


def kick(contact_respond_id: str) -> None:
    """Make sure a drain for this contact is scheduled on the pool. A no-op when one is
    live (it re-reads the queue after letting go, so the new row is not missed) or the
    contact is backing off; a full pool leaves the rows queued for the sweeper."""
    from app.tasks import chat_turns

    contact = str(contact_respond_id or "")
    if not contact or _shutting_down.is_set() or _mutex_alive(contact) or _backing_off(contact):
        return
    try:
        chat_turns._submit(_drain_job, contact)
    except Exception:  # noqa: BLE001 - the sweeper re-arms it
        logger.warning("chatbot inbox: could not schedule a drain for %s", contact, exc_info=True)


def _drain_job(contact: str) -> None:
    """One step on the pool: ONE row, then the contact goes to the back of the pool, so a
    long backlog never holds a thread (IQ-30)."""
    from app.database import SessionLocal

    held = _step(contact, SessionLocal)
    if held is None or _shutting_down.is_set():
        return
    # Read again AFTER letting go: a row enqueued while this step held the mutex was
    # kicked into a no-op, so it is this contact's next step.
    if _has_queued(contact, SessionLocal):
        kick(contact)


# --------------------------------------------------------------------------- #
# The mutex and the backoff
# --------------------------------------------------------------------------- #


def _redis() -> Any:
    from app.services.queue_service import redis_conn

    return redis_conn


def _mutex_key(contact: str) -> str:
    return f"chatbot:drain:{contact}"


def _backoff_key(contact: str) -> str:
    return f"chatbot:inbox:backoff:{contact}"


def _lookup_fails_key(contact: str) -> str:
    return f"chatbot:inbox:lookup-fails:{contact}"


def _mutex_alive(contact: str) -> bool:
    try:
        return bool(_redis().exists(_mutex_key(contact)))
    except Exception:  # noqa: BLE001 - unreadable reads as held: nothing is started on it
        logger.warning("chatbot inbox: drain mutex unreadable for %s", contact, exc_info=True)
        return True


def _backing_off(contact: str) -> bool:
    try:
        return bool(_redis().exists(_backoff_key(contact)))
    except Exception:  # noqa: BLE001
        return False


def _back_off(contact: str) -> None:
    """IQ-31: the contact's next run waits 1, 2, 4 ... seconds after each failed lookup."""
    try:
        fails = int(_redis().incr(_lookup_fails_key(contact)))
        _redis().expire(_lookup_fails_key(contact), 900)
        delay = min(LOOKUP_BACKOFF_MAX_SECONDS, 2.0 ** (fails - 1))
        _redis().set(_backoff_key(contact), 1, px=int(delay * 1000))
    except Exception:  # noqa: BLE001
        logger.warning("chatbot inbox: could not back off %s", contact, exc_info=True)


def _clear_backoff(contact: str) -> None:
    try:
        _redis().delete(_lookup_fails_key(contact), _backoff_key(contact))
    except Exception:  # noqa: BLE001
        pass


class _Mutex:
    """One drain per contact across processes: SET NX with a TTL, refreshed by a heartbeat
    thread while the drain runs, released only by its owner."""

    def __init__(self, contact: str) -> None:
        self.key = _mutex_key(contact)
        self.token = uuid.uuid4().hex
        self.row_started = time.monotonic()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def acquire(self) -> bool:
        return bool(_redis().set(self.key, self.token, nx=True, px=int(MUTEX_TTL_SECONDS * 1000)))

    def start_heartbeat(self) -> None:
        self._thread = threading.Thread(target=self._beat, name="chatbot-inbox-heartbeat", daemon=True)
        self._thread.start()

    def _beat(self) -> None:
        while not self._stop.wait(HEARTBEAT_INTERVAL_SECONDS):
            if time.monotonic() - self.row_started > MAX_ROW_HOLD_SECONDS:
                logger.error("chatbot inbox: a row held %s past %.0fs, letting it lapse", self.key, MAX_ROW_HOLD_SECONDS)
                return
            try:
                _redis().eval(_REFRESH_LUA, 1, self.key, self.token, int(MUTEX_TTL_SECONDS * 1000))
            except Exception:  # noqa: BLE001 - retried on the next beat
                logger.warning("chatbot inbox: heartbeat failed for %s", self.key, exc_info=True)

    def release(self) -> None:
        self._stop.set()
        try:
            _redis().eval(_RELEASE_LUA, 1, self.key, self.token)
        except Exception:  # noqa: BLE001 - it lapses within the TTL
            logger.warning("chatbot inbox: could not release %s", self.key, exc_info=True)


# --------------------------------------------------------------------------- #
# Rows: claim, fence, marks
# --------------------------------------------------------------------------- #


def _factory(session_factory: Callable[[], Any] | None) -> Callable[[], Any]:
    from app.database import SessionLocal

    return session_factory or SessionLocal


def _send_key(envelope: Any, created_at: Any) -> float:
    sent = send_order.send_key_ms(envelope.get("message") if isinstance(envelope, dict) else None)
    if sent is not None:
        return float(sent)
    return created_at.timestamp() * 1000 if created_at is not None else float("inf")


def _queued_keys(db: Any, contact: str) -> list[tuple[float, Any, str]]:
    """The contact's queued rows by send time, oldest first: (send key, created_at, id).
    Reads only the two clock fields, never the envelopes (IQ-33)."""
    stamp = ChatbotTurn.envelope["message"]["message"]["timestamp"].astext
    rows = (
        db.query(ChatbotTurn.id, ChatbotTurn.message_id, stamp, ChatbotTurn.created_at)
        .filter(
            ChatbotTurn.contact_respond_id == contact,
            ChatbotTurn.status == QUEUED,
            ChatbotTurn.is_test.is_(False),
        )
        .all()
    )
    keys = [
        (_send_key({"message": {"message": {"messageId": mid, "timestamp": ts}}}, created), created, str(rid))
        for rid, mid, ts, created in rows
    ]
    return sorted(keys, key=lambda k: (k[0], k[1]))


def _claim_next(contact: str, factory: Callable[[], Any]) -> tuple[str, Any] | None:
    """Take the contact's oldest-sent queued row (`queued` -> `processing`). The claim
    stamps `started_at` with the database clock: the fence every later write of this run
    matches on (IQ-29)."""
    db = factory()
    try:
        for _ in range(5):
            keys = _queued_keys(db, contact)
            if not keys:
                return None
            turn_id = keys[0][2]
            claimed_at = db.execute(
                text(
                    "UPDATE chatbot.turns SET status = 'processing', stage = :stage, "
                    "started_at = clock_timestamp() WHERE id = CAST(:id AS uuid) AND status = 'queued' "
                    "RETURNING started_at"
                ),
                {"id": turn_id, "stage": CLAIMED_STAGE},
            ).scalar()
            db.commit()
            if claimed_at is not None:
                return turn_id, claimed_at
        return None
    finally:
        db.close()


def _still_mine(db: Any, run: _RowRun) -> bool:
    started_at = db.query(ChatbotTurn.started_at).filter(ChatbotTurn.id == run.turn_id).scalar()
    return started_at == run.claimed_at


def checkpoint(turn_id: str | None = None) -> None:
    """The look-ahead (rule 4), called by the engine right before the turn writes
    conversation state, runs a lane side effect it cannot undo, or closes. On the inbox
    drain: a lost claim stops the turn (`ClaimLost`), and an earlier-sent queued row of the
    same contact makes it yield; once a look-ahead passes, the turn is committed."""
    run = current_run(turn_id)
    if run is None:
        return
    db = run.factory()
    try:
        if not _still_mine(db, run):
            raise ClaimLost(run.turn_id)
        if run.committed:
            return
        earlier = [k for k in _queued_keys(db, run.contact) if k[0] < run.send_key] if run.send_key is not None else []
    finally:
        db.close()
    if earlier:
        raise TurnYielded(earlier[0][2])
    run.committed = True


def _set_row(factory: Callable[[], Any], turn_id: str, claimed_at: Any = None, **values: Any) -> bool:
    """Update an open row; with `claimed_at`, only while this claim still owns it."""
    conditions = [ChatbotTurn.id == turn_id, ChatbotTurn.status.in_(OPEN_STATUSES)]
    if claimed_at is not None:
        conditions.append(ChatbotTurn.started_at == claimed_at)
    db = factory()
    try:
        result = db.execute(update(ChatbotTurn).where(*conditions).values(**values))
        db.commit()
        return bool(result.rowcount)
    finally:
        db.close()


def _requeue(factory: Callable[[], Any], turn_id: str, claimed_at: Any = None) -> None:
    _set_row(factory, turn_id, claimed_at, status=QUEUED, stage=QUEUED, finished_at=None)


def _stamp_sending(factory: Callable[[], Any], turn_id: str, claimed_at: Any) -> bool:
    # `finished_at` doubles as the stamp's time, so recovery reads only this attempt's log.
    return _set_row(factory, turn_id, claimed_at, stage=SENDING_STAGE, finished_at=func.now())


def _finish(factory: Callable[[], Any], turn_id: str, status: str, stage: str | None, claimed_at: Any = None) -> None:
    """The done mark: the engine's own close, applied once the POST has returned."""
    from app.services.chatbot import engine

    if not _set_row(factory, turn_id, claimed_at, status=status, stage=stage, finished_at=func.now()):
        return
    if status in ("done", "failed"):
        db = factory()
        try:
            engine.chat_facts.record_turn(db, turn_id)
        except Exception:  # noqa: BLE001 - analytics must never fail a turn
            db.rollback()
            logger.warning("chat facts: recording turn %s failed", turn_id, exc_info=True)
        finally:
            db.close()


def _append_record(factory: Callable[[], Any], turn_id: str, *, status: str, summary: str, why: str, facts: dict) -> None:
    db = factory()
    try:
        row = db.query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).first()
        if row is None:
            return
        record = trace_mod.TurnTrace()
        record.start()
        record.record("sent", status=status, summary=summary, why=why, facts=facts)  # type: ignore[arg-type]
        row.trace = [*(row.trace or []), *record.persisted()]
        db.commit()
    finally:
        db.close()


def _flag_for_staff(factory: Callable[[], Any], turn_id: str, outcome: str | None, claimed_at: Any = None) -> None:
    """A POST that may have reached the sender is not sent again: `failed` at
    `send_unconfirmed`, with a failed record on the trace for staff."""
    from app.services.chatbot import engine

    db = factory()
    try:
        row = db.query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).first()
        if row is None or row.status not in OPEN_STATUSES:
            return
        if claimed_at is not None and row.started_at != claimed_at:
            return
        record = trace_mod.TurnTrace()
        record.start()
        record.record(
            "sent",
            status="failed",
            summary="The reply may not have reached the customer. Check the conversation before sending it again.",
            why="A sender POST that timed out or answered with an error may still have been delivered, so it is not sent twice.",
            facts={"outcome": outcome},
            error="Sender delivery unconfirmed.",
        )
        row.trace = [*(row.trace or []), *record.persisted()]
        row.status = "failed"
        row.stage = SEND_UNCONFIRMED_STAGE
        row.error = row.error or "Sender delivery unconfirmed."
        row.finished_at = engine._now()
        db.commit()
    finally:
        db.close()


def should_resend(outcome: str | None) -> bool:
    """Rule (a): re-send only when the logged result proves the POST never left (`refused`).

    `outcome` is one of `refused`, `timeout`, `http_error`, `ok`, or None (the attempt was
    stamped, its result never logged: a crash mid-POST). Rule (b), always re-send, is a
    one-line flip here."""
    return outcome == direct_ingress.SEND_REFUSED


def _post(factory: Callable[[], Any], run: _RowRun, result: Any, status: str, stage: str | None) -> str:
    """POST the turn's actions to the sender, then mark the row (IQ-16). A stamp that
    matches no row means the claim was lost: nothing is posted (IQ-29)."""
    outcome: str | None = None
    for attempt in range(1, MAX_SEND_ATTEMPTS + 1):
        if not _stamp_sending(factory, run.turn_id, run.claimed_at):
            logger.warning("chatbot inbox: turn %s is no longer this drain's; not posted", run.turn_id)
            return "lost"
        outcome = direct_ingress.send_outcome(
            factory,
            turn_id=run.turn_id,
            contact_id=run.contact,
            actions=list(result.actions or []),
            reply=result.reply,
            branch_kind=result.branch_kind,
        )
        if outcome == direct_ingress.SEND_OK:
            _finish(factory, run.turn_id, status, stage, run.claimed_at)
            return "done"
        if attempt >= MAX_SEND_ATTEMPTS or not should_resend(outcome):
            break
        time.sleep(RESEND_BACKOFF_SECONDS * attempt)
    _flag_for_staff(factory, run.turn_id, outcome, run.claimed_at)
    return "flagged"


def _close_skipped(factory: Callable[[], Any], turn_id: str, reason: str, claimed_at: Any) -> None:
    """A row nobody answers (human takeover): closed `done`, no turn, no POST."""
    _append_record(
        factory,
        turn_id,
        status="skipped",
        summary="A person has taken over this conversation; sent no reply.",
        why="The chatbot stays silent while staff handle the conversation.",
        facts={"skipped": reason},
    )
    _finish(factory, turn_id, "done", CLAIMED_STAGE, claimed_at)


def _run_row(turn_id: str, claimed_at: Any, contact: str, factory: Callable[[], Any]) -> str:
    """Run one claimed row: takeover check, turn, POST, done mark. Returns what happened."""
    from app.services.chatbot import engine
    from app.services.chatbot.contracts import Envelope

    db = factory()
    try:
        row = db.query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).first()
        if row is None:
            return "missing"
        stored = dict(row.envelope or {})
        send_key = _send_key(stored, row.created_at)
        # The takeover flag is read when the row comes up, as the direct-ingress job did.
        record = direct_ingress._lookup_contact(db, contact)
    finally:
        db.close()
    if not isinstance(record, dict):
        # IQ-31 (security M1): an unread takeover flag never answers. Back to `queued`,
        # and the contact backs off before its next try.
        logger.warning("chatbot inbox: contact lookup failed for %s; turn %s waits", contact, turn_id)
        _requeue(factory, turn_id, claimed_at)
        _back_off(contact)
        return "lookup_failed"
    _clear_backoff(contact)
    block = dict(record)
    block["id"] = str(block.get("id") or contact)
    if direct_ingress._human_intervened(block) is True:
        _close_skipped(factory, turn_id, "human_intervened", claimed_at)
        return "skipped"

    run = _RowRun(turn_id, contact, send_key, claimed_at, factory)
    _local.run = run
    try:
        envelope = Envelope(**{**stored, "contact": block})
        result = engine.run_turn(envelope, session_factory=factory, offload=False, queued_turn_id=turn_id)
    except TurnYielded:
        _requeue(factory, turn_id, claimed_at)
        return "yielded"
    except ClaimLost:
        logger.warning("chatbot inbox: turn %s was re-claimed elsewhere; this run stops", turn_id)
        return "lost"
    except Exception as exc:  # noqa: BLE001 - the engine records its own failures; this is past it
        logger.exception("chatbot inbox: turn %s raised", turn_id)
        _set_row(factory, turn_id, claimed_at, status="failed", error=f"{type(exc).__name__}: {exc}")
        return "failed"
    finally:
        _local.run = None
    status, stage = run.close or (str(result.status or "done"), result.stage)
    if result.duplicate or not result.actions:
        _finish(factory, turn_id, status, stage, claimed_at)
        return "done"
    return _post(factory, run, result, status, stage)


def _last_send_outcome(db: Any, turn_id: str, stamped_at: Any) -> str | None:
    """The logged result of the POST stamped at `stamped_at`, or None if none was logged."""
    if stamped_at is None:
        return None
    row = db.execute(
        text(
            "SELECT status, status_code, error_message FROM integration_log "
            "WHERE integration_channel = :ch AND business_table = 'chatbot.turns' "
            "AND business_id = :id AND created_at >= :at ORDER BY created_at DESC LIMIT 1"
        ),
        {"ch": direct_ingress.INTEGRATION_CHANNEL, "id": turn_id, "at": stamped_at},
    ).first()
    if row is None:
        return None
    if row[0] == "success":
        return direct_ingress.SEND_OK
    if row[2] == direct_ingress.REFUSED_ERROR:
        return direct_ingress.SEND_REFUSED
    return direct_ingress.SEND_TIMEOUT if row[1] is None else direct_ingress.SEND_HTTP_ERROR


def _recover_dead_rows(contact: str, factory: Callable[[], Any]) -> None:
    """Under the contact's mutex, every open row this module owns is dead (its drain let go
    of the mutex, or its process died). Nothing posted: back to `queued`. Stamped
    `sending`: a logged `ok` is done (IQ-34), otherwise `should_resend` decides (rule 6)."""
    db = factory()
    try:
        dead = (
            db.query(ChatbotTurn.id, ChatbotTurn.stage, ChatbotTurn.finished_at, ChatbotTurn.error)
            .filter(
                ChatbotTurn.contact_respond_id == contact,
                ChatbotTurn.status.in_(OPEN_STATUSES),
                ChatbotTurn.is_test.is_(False),
                ChatbotTurn.trace.contains(INBOX_MARKER),
            )
            .all()
        )
        outcomes = {
            str(rid): _last_send_outcome(db, str(rid), at) for rid, stage, at, _e in dead if stage == SENDING_STAGE
        }
    finally:
        db.close()
    for rid, stage, _at, error in dead:
        turn_id = str(rid)
        outcome = outcomes.get(turn_id)
        if stage != SENDING_STAGE:
            logger.warning("chatbot inbox: recovering turn %s of %s (nothing was sent)", turn_id, contact)
            _requeue(factory, turn_id)
        elif outcome == direct_ingress.SEND_OK:
            logger.warning("chatbot inbox: turn %s of %s was sent before its process died", turn_id, contact)
            _finish(factory, turn_id, "failed" if error else "done", "sent")
        elif should_resend(outcome):
            logger.warning("chatbot inbox: turn %s of %s is sent again", turn_id, contact)
            _requeue(factory, turn_id)
        else:
            logger.warning("chatbot inbox: turn %s of %s may have been sent; flagged", turn_id, contact)
            _flag_for_staff(factory, turn_id, outcome)


def _has_queued(contact: str, factory: Callable[[], Any]) -> bool:
    db = factory()
    try:
        return (
            db.query(ChatbotTurn.id)
            .filter(
                ChatbotTurn.contact_respond_id == contact,
                ChatbotTurn.status == QUEUED,
                ChatbotTurn.is_test.is_(False),
            )
            .first()
            is not None
        )
    finally:
        db.close()


def _step(contact: str, factory: Callable[[], Any]) -> tuple[str, int] | None:
    """One hold of the contact's mutex: recover its dead rows, then run its oldest-sent
    queued row. Returns (what happened, rows finished), or None when another drain holds
    the contact."""
    global _active
    if _shutting_down.is_set() or _backing_off(contact):
        return None
    mutex = _Mutex(contact)
    try:
        if not mutex.acquire():
            return None
    except Exception:  # noqa: BLE001 - the sweeper re-arms it
        logger.warning("chatbot inbox: drain mutex unavailable for %s", contact, exc_info=True)
        return None
    with _cv:
        _active += 1
        _last_served[contact] = time.monotonic()
    try:
        mutex.start_heartbeat()
        _recover_dead_rows(contact, factory)
        if _shutting_down.is_set():
            return "shutdown", 0
        claimed = _claim_next(contact, factory)
        if claimed is None:
            return "empty", 0
        outcome = _run_row(claimed[0], claimed[1], contact, factory)
        return outcome, 0 if outcome in ("yielded", "lost", "lookup_failed") else 1
    finally:
        mutex.release()
        with _cv:
            _active -= 1
            _cv.notify_all()


def drain(contact_respond_id: str, *, session_factory: Callable[[], Any] | None = None) -> int:
    """Run this contact's queued rows in send order until none is left or shutdown began.
    Returns the rows finished; 0 at once when another drain holds the contact. (The pool
    runs `_drain_job`, one row per step; this is the same steps back to back.)"""
    contact = str(contact_respond_id or "")
    factory = _factory(session_factory)
    finished = idle = 0
    while contact and not _shutting_down.is_set() and idle < 3:
        held = _step(contact, factory)
        if held is None or held[0] == "lookup_failed":
            break
        finished += held[1]
        idle = 0 if held[1] or held[0] == "yielded" else idle + 1
        if not _has_queued(contact, factory):
            break
    return finished


# --------------------------------------------------------------------------- #
# Sweeper and shutdown
# --------------------------------------------------------------------------- #


def sweep(*, session_factory: Callable[[], Any] | None = None) -> int:
    """One sweeper pass: kick a drain for every contact with queued rows, or rows a dead
    process left open, and no live drain (the drain recovers those first). The least
    recently served contact goes first. Returns the contacts kicked."""
    if _shutting_down.is_set():
        return 0
    db = _factory(session_factory)()
    try:
        # Both arms sit inside the partial index `ix_chatbot_turns_inbox_open` (IQ-36).
        contacts = [
            str(c)
            for (c,) in db.query(ChatbotTurn.contact_respond_id)
            .filter(
                ChatbotTurn.is_test.is_(False),
                ChatbotTurn.status.in_((QUEUED, *OPEN_STATUSES)),
                or_(ChatbotTurn.status == QUEUED, ChatbotTurn.trace.contains(INBOX_MARKER)),
            )
            .distinct()
            .all()
        ]
    finally:
        db.close()
    with _cv:
        contacts.sort(key=lambda c: _last_served.get(c, 0.0))
    kicked = 0
    for contact in contacts:
        if _mutex_alive(contact) or _backing_off(contact):
            continue
        kick(contact)
        kicked += 1
    return kicked


def start_sweeper(interval: float = SWEEP_INTERVAL_SECONDS) -> None:
    """The process's sweeper thread: a pass at once, then every `interval` seconds."""
    global _sweeper
    if _sweeper is not None and _sweeper.is_alive():
        return
    _sweeper_stop.clear()

    def _loop() -> None:
        while not _sweeper_stop.is_set() and not _shutting_down.is_set():
            try:
                sweep()
            except Exception:  # noqa: BLE001 - the next pass tries again
                logger.warning("chatbot inbox: sweep failed", exc_info=True)
            _sweeper_stop.wait(interval)

    _sweeper = threading.Thread(target=_loop, name="chatbot-inbox-sweeper", daemon=True)
    _sweeper.start()


def in_use() -> bool:
    """Did this process run the queue (a sweeper, or a drain on the pool)?"""
    from app.tasks import chat_turns

    with _cv:
        return (_sweeper is not None and _sweeper.is_alive()) or _active > 0 or chat_turns._in_flight > 0


def begin_shutdown() -> None:
    """Stop taking rows: drains finish the row they are in, nothing new starts here."""
    _shutting_down.set()
    _sweeper_stop.set()


def wait_idle(timeout_s: float) -> bool:
    """Wait until every running drain has finished its current row and let go."""
    deadline = time.monotonic() + float(timeout_s)
    with _cv:
        while _active > 0:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            _cv.wait(remaining)
    return True


def _reset_for_tests() -> None:
    """Clear this process's shutdown flag and local drain state (a test's next process)."""
    _shutting_down.clear()
    _sweeper_stop.clear()
    with _cv:
        _last_served.clear()
