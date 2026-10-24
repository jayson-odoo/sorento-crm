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

from sqlalchemy import and_, or_, text, update
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

# The mutex lives as long as `dispatch`'s alive stamp (clears the redis socket timeout)
# and is refreshed on the same beat.
MUTEX_TTL_SECONDS = 15.0
HEARTBEAT_INTERVAL_SECONDS = 4.0
# A single row held longer than this is hung (the photo wait alone caps at 10 minutes):
# the heartbeat stops so another process can recover the contact.
MAX_ROW_HOLD_SECONDS = 900.0
SWEEP_INTERVAL_SECONDS = 1.5
# A refused connection proves nothing left, so it is sent again, a bounded number of times.
MAX_SEND_ATTEMPTS = 3
RESEND_BACKOFF_SECONDS = 0.5

_REFRESH_LUA = (
    "if redis.call('GET', KEYS[1]) == ARGV[1] then "
    "return redis.call('PEXPIRE', KEYS[1], ARGV[2]) else return 0 end"
)
_RELEASE_LUA = (
    "if redis.call('GET', KEYS[1]) == ARGV[1] then "
    "return redis.call('DEL', KEYS[1]) else return 0 end"
)


class TurnYielded(BaseException):
    """The running turn gives way to an earlier-sent queued message (look-ahead).

    A BaseException on purpose: every `except Exception` in the engine and its lanes turns
    a failure into an error reply and a closed row, and a yield must pass all of them with
    nothing written."""


# --------------------------------------------------------------------------- #
# Process state
# --------------------------------------------------------------------------- #

_cv = threading.Condition()
_shutting_down = threading.Event()
_active = 0
_local = threading.local()
_sweeper: threading.Thread | None = None
_sweeper_stop = threading.Event()


class _RowRun:
    """The row the current drain thread is running, read by the engine's seams."""

    def __init__(self, turn_id: str, contact: str, send_key: float | None, factory: Callable[[], Any]):
        self.turn_id = turn_id
        self.contact = contact
        self.send_key = send_key
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


def accepts(db: Any, envelope: Any) -> bool:
    """Does this `/chat/turn` envelope go to the queue? A live message of a covered
    contact, with a sender to answer through and on the default workspace (the sender
    speaks for that one only). Test and console turns never do."""
    from app.services.chatbot import engine

    if envelope.dry_run or envelope.ingress == "console":
        return False
    contact = engine._contact_respond_id(envelope)
    if not contact or engine._message_id(envelope) is None:
        return False
    if not queue_mode_for(db, contact):
        return False
    if not direct_ingress._sender_url(db):
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


def enqueue(db: Any, envelope: Any) -> tuple[str, bool]:
    """Insert this message's `queued` row, or find the one already there. Never runs it.

    Returns `(turn_id, created)`. A failed row an operator asked to retry gets its next
    attempt queued (the Retry copy), once however many copies arrive."""
    from app.services.chatbot import engine

    contact = engine._contact_respond_id(envelope)
    message_id = engine._message_id(envelope)
    existing = engine._select_turn(db, contact_respond_id=contact, message_id=message_id, is_test=False)
    retrying = existing if engine._awaiting_retry(existing) else None
    if existing is not None and retrying is None:
        return str(existing.id), False
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
    live (it re-reads the queue after letting go, so the new row is not missed); a full
    pool leaves the rows queued for the sweeper to re-arm."""
    from app.tasks import chat_turns

    contact = str(contact_respond_id or "")
    if not contact or _shutting_down.is_set() or _mutex_alive(contact):
        return
    try:
        chat_turns._submit(_drain_job, contact)
    except Exception:  # noqa: BLE001 - the sweeper re-arms it
        logger.warning("chatbot inbox: could not schedule a drain for %s", contact, exc_info=True)


def _drain_job(contact: str) -> None:
    drain(contact)


# --------------------------------------------------------------------------- #
# The mutex
# --------------------------------------------------------------------------- #


def _redis() -> Any:
    from app.services.queue_service import redis_conn

    return redis_conn


def _mutex_key(contact: str) -> str:
    return f"chatbot:drain:{contact}"


def _mutex_alive(contact: str) -> bool:
    try:
        return bool(_redis().exists(_mutex_key(contact)))
    except Exception:  # noqa: BLE001 - unreadable reads as held: nothing is started on it
        logger.warning("chatbot inbox: drain mutex unreadable for %s", contact, exc_info=True)
        return True


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
# The drain
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
    rows = (
        db.query(ChatbotTurn.id, ChatbotTurn.envelope, ChatbotTurn.created_at)
        .filter(
            ChatbotTurn.contact_respond_id == contact,
            ChatbotTurn.status == QUEUED,
            ChatbotTurn.is_test.is_(False),
        )
        .all()
    )
    return sorted(((_send_key(env, created), created, str(rid)) for rid, env, created in rows), key=lambda k: (k[0], k[1]))


def _claim_next(contact: str, factory: Callable[[], Any]) -> str | None:
    """Take the contact's oldest-sent queued row (`queued` -> `processing`)."""
    db = factory()
    try:
        for _ in range(5):
            keys = _queued_keys(db, contact)
            if not keys:
                return None
            turn_id = keys[0][2]
            result = db.execute(
                update(ChatbotTurn)
                .where(ChatbotTurn.id == turn_id, ChatbotTurn.status == QUEUED)
                .values(status="processing", stage=CLAIMED_STAGE)
            )
            db.commit()
            if result.rowcount:
                return turn_id
        return None
    finally:
        db.close()


def checkpoint(turn_id: str | None = None) -> None:
    """The look-ahead (rule 4), called by the engine right before the turn writes
    conversation state or closes. On the inbox drain, an earlier-sent queued row of the
    same contact makes this turn yield; once a checkpoint passes, the turn is committed."""
    run = current_run(turn_id)
    if run is None or run.committed:
        return
    if run.send_key is not None:
        db = run.factory()
        try:
            earlier = [k for k in _queued_keys(db, run.contact) if k[0] < run.send_key]
        finally:
            db.close()
        if earlier:
            raise TurnYielded(earlier[0][2])
    run.committed = True


def _set_row(factory: Callable[[], Any], turn_id: str, *, only_status: str = "processing", **values: Any) -> bool:
    db = factory()
    try:
        result = db.execute(
            update(ChatbotTurn)
            .where(ChatbotTurn.id == turn_id, ChatbotTurn.status == only_status)
            .values(**values)
        )
        db.commit()
        return bool(result.rowcount)
    finally:
        db.close()


def _requeue(factory: Callable[[], Any], turn_id: str) -> None:
    _set_row(factory, turn_id, status=QUEUED, stage=QUEUED, finished_at=None)


def _stamp_sending(factory: Callable[[], Any], turn_id: str) -> None:
    # `finished_at` doubles as the stamp's time, so recovery reads only this attempt's log.
    from sqlalchemy import func

    _set_row(factory, turn_id, stage=SENDING_STAGE, finished_at=func.now())


def _finish(factory: Callable[[], Any], turn_id: str, status: str, stage: str | None) -> None:
    """The done mark: the engine's own close, applied once the POST has returned."""
    from sqlalchemy import func

    from app.services.chatbot import engine

    if not _set_row(factory, turn_id, status=status, stage=stage, finished_at=func.now()):
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


def _flag_for_staff(factory: Callable[[], Any], turn_id: str, outcome: str | None) -> None:
    """A POST that may have reached the sender is not sent again: `failed` at
    `send_unconfirmed`, with a failed record on the trace for staff."""
    from app.services.chatbot import engine

    db = factory()
    try:
        row = db.query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).first()
        if row is None:
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


def _post(factory: Callable[[], Any], turn_id: str, contact: str, result: Any, status: str, stage: str | None) -> str:
    """POST the turn's actions to the sender, then mark the row (IQ-16)."""
    outcome: str | None = None
    for attempt in range(1, MAX_SEND_ATTEMPTS + 1):
        _stamp_sending(factory, turn_id)
        outcome = direct_ingress.send_outcome(
            factory,
            turn_id=turn_id,
            contact_id=contact,
            actions=list(result.actions or []),
            reply=result.reply,
            branch_kind=result.branch_kind,
        )
        if outcome == direct_ingress.SEND_OK:
            _finish(factory, turn_id, status, stage)
            return "done"
        if attempt >= MAX_SEND_ATTEMPTS or not should_resend(outcome):
            break
        time.sleep(RESEND_BACKOFF_SECONDS * attempt)
    _flag_for_staff(factory, turn_id, outcome)
    return "flagged"


def _close_skipped(factory: Callable[[], Any], turn_id: str, reason: str) -> None:
    """A row nobody answers (human takeover): closed `done`, no turn, no POST."""
    _append_record(
        factory,
        turn_id,
        status="skipped",
        summary="A person has taken over this conversation; sent no reply.",
        why="The chatbot stays silent while staff handle the conversation.",
        facts={"skipped": reason},
    )
    _finish(factory, turn_id, "done", CLAIMED_STAGE)


def _run_row(turn_id: str, contact: str, factory: Callable[[], Any]) -> str:
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
        # The takeover flag is read when the row comes up, as the direct-ingress job does.
        record = direct_ingress._lookup_contact(db, contact)
    finally:
        db.close()
    block = dict(record) if isinstance(record, dict) else dict(stored.get("contact") or {})
    block["id"] = str(block.get("id") or contact)
    if direct_ingress._human_intervened(block) is True:
        _close_skipped(factory, turn_id, "human_intervened")
        return "skipped"

    run = _RowRun(turn_id, contact, send_key, factory)
    _local.run = run
    try:
        envelope = Envelope(**{**stored, "contact": block})
        result = engine.run_turn(envelope, session_factory=factory, offload=False, queued_turn_id=turn_id)
    except TurnYielded:
        _requeue(factory, turn_id)
        return "yielded"
    except Exception as exc:  # noqa: BLE001 - the engine records its own failures; this is past it
        logger.exception("chatbot inbox: turn %s raised", turn_id)
        _set_row(factory, turn_id, status="failed", error=f"{type(exc).__name__}: {exc}")
        return "failed"
    finally:
        _local.run = None
    status, stage = run.close or (str(result.status or "done"), result.stage)
    if result.duplicate or not result.actions:
        _finish(factory, turn_id, status, stage)
        return "done"
    return _post(factory, turn_id, contact, result, status, stage)


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
    """Under the contact's mutex, every `processing` row this module owns is dead (its
    drain let go of the mutex, or its process died). Nothing posted: back to `queued`.
    Stamped `sending`: `should_resend` decides (rule 6)."""
    db = factory()
    try:
        dead = (
            db.query(ChatbotTurn.id, ChatbotTurn.stage, ChatbotTurn.finished_at)
            .filter(
                ChatbotTurn.contact_respond_id == contact,
                ChatbotTurn.status == "processing",
                ChatbotTurn.is_test.is_(False),
                ChatbotTurn.trace.contains(INBOX_MARKER),
            )
            .all()
        )
        outcomes = {
            str(rid): _last_send_outcome(db, str(rid), at) for rid, stage, at in dead if stage == SENDING_STAGE
        }
    finally:
        db.close()
    for rid, stage, _at in dead:
        turn_id = str(rid)
        if stage != SENDING_STAGE:
            logger.warning("chatbot inbox: recovering turn %s of %s (nothing was sent)", turn_id, contact)
            _requeue(factory, turn_id)
        elif should_resend(outcomes.get(turn_id)):
            logger.warning("chatbot inbox: turn %s of %s is sent again", turn_id, contact)
            _requeue(factory, turn_id)
        else:
            logger.warning("chatbot inbox: turn %s of %s may have been sent; flagged", turn_id, contact)
            _flag_for_staff(factory, turn_id, outcomes.get(turn_id))


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


def _drain_held(contact: str, factory: Callable[[], Any]) -> tuple[int, int] | None:
    """One hold of the contact's mutex: recover its dead rows, then run its queued rows.
    Returns (rows claimed, rows finished), or None when another drain holds it."""
    global _active
    mutex = _Mutex(contact)
    try:
        if not mutex.acquire():
            return None
    except Exception:  # noqa: BLE001 - the sweeper re-arms it
        logger.warning("chatbot inbox: drain mutex unavailable for %s", contact, exc_info=True)
        return None
    with _cv:
        _active += 1
    claimed = finished = 0
    try:
        mutex.start_heartbeat()
        _recover_dead_rows(contact, factory)
        while not _shutting_down.is_set():
            turn_id = _claim_next(contact, factory)
            if turn_id is None:
                break
            claimed += 1
            mutex.row_started = time.monotonic()
            if _run_row(turn_id, contact, factory) != "yielded":
                finished += 1
    finally:
        mutex.release()
        with _cv:
            _active -= 1
            _cv.notify_all()
    return claimed, finished


def drain(contact_respond_id: str, *, session_factory: Callable[[], Any] | None = None) -> int:
    """Run this contact's queued rows in send order until none is left or shutdown began.
    Returns the rows finished; 0 at once when another drain holds the contact."""
    contact = str(contact_respond_id or "")
    factory = _factory(session_factory)
    finished = 0
    idle_holds = 0
    while contact and not _shutting_down.is_set() and idle_holds < 3:
        held = _drain_held(contact, factory)
        if held is None:
            break
        finished += held[1]
        idle_holds = 0 if held[0] else idle_holds + 1
        # Read again AFTER letting go: a row enqueued while this drain held the mutex was
        # kicked into a no-op, so it is this drain's to take.
        if _shutting_down.is_set() or not _has_queued(contact, factory):
            break
    return finished


# --------------------------------------------------------------------------- #
# Sweeper and shutdown
# --------------------------------------------------------------------------- #


def sweep(*, session_factory: Callable[[], Any] | None = None) -> int:
    """One sweeper pass: kick a drain for every contact with queued rows, or rows a dead
    process left `processing`, and no live drain (the drain recovers those first).
    Returns the contacts kicked."""
    if _shutting_down.is_set():
        return 0
    db = _factory(session_factory)()
    try:
        contacts = [
            str(c)
            for (c,) in db.query(ChatbotTurn.contact_respond_id)
            .filter(
                ChatbotTurn.is_test.is_(False),
                or_(
                    ChatbotTurn.status == QUEUED,
                    and_(ChatbotTurn.status == "processing", ChatbotTurn.trace.contains(INBOX_MARKER)),
                ),
            )
            .distinct()
            .all()
        ]
    finally:
        db.close()
    kicked = 0
    for contact in contacts:
        if _mutex_alive(contact):
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
    """Did this process run the queue (a sweeper, or a drain scheduled or running)?"""
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
