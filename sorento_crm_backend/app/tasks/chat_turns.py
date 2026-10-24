"""The chatbot turn as an RQ job (AC-703).

`CHATBOT_TURN_ON_WORKER` moves the turn off the API thread and onto the `chat` queue; the
request still waits for it and still answers n8n with the finished turn. Nothing about the
turn changes here - this module is the seam that lets the work run in a different process,
which is why it is twenty lines and holds no logic of its own.

**One of the three files allowed to import `app.services.chatbot`**
(`tests/chatbot/test_import_boundary.py`). It is a doorway, not a caller with opinions.

`offload=False` on the call below is load-bearing: without it the worker would read the
same flag the API read, decide to offload, and enqueue the turn to the queue it is
currently draining - forever, at whatever rate redis can accept.
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Callable

logger = logging.getLogger(__name__)

# The queue name lives on the engine (`engine.CHAT_QUEUE`) so the enqueue site and the
# worker's registry cannot drift; re-exported here for anything reading the task module.
CHAT_QUEUE = "chat"

#: The nightly topic labeller's queue (chat analytics CA-2), drained by the batch worker.
ANALYTICS_QUEUE = "analytics"


def run_turn_job(
    envelope: dict[str, Any], session_factory: Callable[[], Any] | None = None
) -> dict[str, Any]:
    """Run one turn on the worker and return what the waiting request will answer with.

    The argument is the envelope as JSON (RQ pickles the arguments; a plain dict travels
    where a pydantic model's version-coupled pickle would be a deploy hazard), and the
    return is `TurnResult.as_dict()` plus the three fields the endpoint reads off the
    result object rather than the response body.

    `session_factory` is for in-process callers outside the module boundary (the live
    usage probe in `scripts/`, whose test hands it a test session factory); RQ never
    passes it, so the worker keeps `SessionLocal`.
    """
    from app.database import SessionLocal
    from app.services.chatbot import run_turn
    from app.services.chatbot.contracts import Envelope

    result = run_turn(
        Envelope(**envelope), session_factory=session_factory or SessionLocal, offload=False
    )
    payload = result.as_dict()
    # `as_dict` is the RESPONSE shape; the waiting request rebuilds a full `TurnResult`,
    # and the endpoint's own logging reads `status` / `stage` / `error` off it. Sending
    # them keeps an offloaded failure as legible as an in-process one.
    payload.update({"status": result.status, "stage": result.stage, "error": result.error})
    logger.info(
        "chatbot turn %s ran on the worker: status=%s stage=%s",
        payload.get("turn_id"),
        result.status,
        result.stage,
    )
    return payload


# CHAT-SPEED: direct turns run on a small pool of threads INSIDE the API process, not on RQ.
# Measured on a dev stack (18 Oct): an RQ work-horse is forked per job and paid ~0.85 s of
# cold start before the turn row existed, out of a 2.30 s saving; a warm thread pays ~0.01 s.
# It is also how `/chat/turn` already runs (an API thread per n8n call), and it keeps the
# turn off the single `worker_fast` process that `media` and `respond_io` share. Bounded:
# past `DIRECT_TURN_THREADS` turns in flight the message is left to the n8n copy, so a
# burst degrades to today's path instead of queueing here.
DIRECT_TURN_THREADS = 8
_pool: ThreadPoolExecutor | None = None
_pool_lock = threading.Lock()
_in_flight = 0


def _submit(func: Callable[..., Any], *args: Any) -> bool:
    """Run `func(*args)` on the direct-turn pool. False, running nothing, when it is full."""
    global _pool, _in_flight
    with _pool_lock:
        if _in_flight >= DIRECT_TURN_THREADS:
            return False
        if _pool is None:
            _pool = ThreadPoolExecutor(
                max_workers=DIRECT_TURN_THREADS, thread_name_prefix="direct-turn"
            )
        _in_flight += 1
        pool = _pool

    def _run() -> None:
        global _in_flight
        try:
            func(*args)
        except Exception:  # noqa: BLE001 - a thread has nobody to raise to
            logger.exception("direct ingress: the turn failed")
        finally:
            with _pool_lock:
                _in_flight -= 1

    try:
        pool.submit(_run)
    except Exception:
        with _pool_lock:
            _in_flight -= 1
        raise
    return True


def enqueue_direct_turn(
    db: Any,
    payload: dict[str, Any],
    *,
    contact_id: str,
    traffic: str,
    channel: str,
    already_existed: bool,
    hmac_signed: bool,
) -> bool:
    """CHAT-SPEED: start a webhook message's turn on the direct-turn pool, when the gate
    allows it.

    CHAT-INBOX-QUEUE: with the switch covering the contact, the message is put in the
    contact's inbox queue (`inbox_queue.enqueue`) and a drain is kicked; the drain answers
    it on the pool. Photos and voice notes are queued too.

    Called by the respond.io webhook AFTER the message is stored. A doorway, like the rest of
    this file: the gate lives in `app.services.chatbot.direct_ingress`. **Never raises**: the
    webhook's answer to respond.io must not depend on this, and anything not queued here is
    answered through another injector's copy. True when the message was queued.
    """
    try:
        from app.services.chatbot import direct_ingress, inbox_queue

        reason = direct_ingress.skip_reason(
            db,
            payload,
            contact_id=contact_id,
            traffic=traffic,
            channel=channel,
            already_existed=already_existed,
            hmac_signed=hmac_signed,
            queue_mode=True,
        )
        if reason is None and not direct_ingress._on_default_workspace(db, contact_id):
            reason = "non_default_workspace"
        if reason is None:
            inbox_queue.enqueue(db, direct_ingress.envelope_for(payload, dict(payload.get("contact") or {})))
            inbox_queue.kick(contact_id)
        if reason is not None:
            if reason not in ("off", "contact_not_listed"):
                logger.info("direct ingress: not started for %s (%s)", contact_id, reason)
            return False
        return True
    except Exception:  # noqa: BLE001 - see the docstring: the n8n copy is the fallback
        logger.warning("direct ingress: could not start the turn for %s", contact_id, exc_info=True)
        return False


# CHAT-INBOX-QUEUE grace on shutdown: under gunicorn's `graceful_timeout` (150 s).
INBOX_SHUTDOWN_GRACE_SECONDS = 140.0


def start_inbox_queue() -> None:
    """App start-up: this process's inbox sweeper (a pass at once, then every 1.5 s).

    Not under pytest: the sweep is global by contract, so a test process would take
    other test workers' queued rows. Tests drive `inbox_queue.sweep()` themselves."""
    import sys

    if "pytest" in sys.modules:
        return
    from app.services.chatbot import inbox_queue

    inbox_queue.start_sweeper()


def stop_inbox_queue(grace_seconds: float = INBOX_SHUTDOWN_GRACE_SECONDS) -> bool:
    """App shutdown: drains stop taking rows and finish the one they are in (its sender
    POST and done mark included). True when they did within the grace. A process that
    never ran the queue has nothing to stop."""
    from app.services.chatbot import inbox_queue

    if not inbox_queue.in_use():
        return True
    inbox_queue.begin_shutdown()
    idle = inbox_queue.wait_idle(grace_seconds)
    if not idle:
        logger.error("chatbot inbox: drains still running after %.0fs of shutdown grace", grace_seconds)
    return idle


def run_direct_turn_job(payload: dict[str, Any]) -> dict[str, Any]:
    """Run the webhook-started turn and hand its actions to the n8n sender (on a pool
    thread). The argument is the respond.io webhook body as JSON. Returns
    `{turn_id, status, duplicate, sent, skipped}` for the log.
    """
    from app.services.chatbot import direct_ingress

    outcome = direct_ingress.run(payload)
    logger.info(
        "direct ingress turn %s: status=%s duplicate=%s sent=%s",
        outcome.get("turn_id"),
        outcome.get("status"),
        outcome.get("duplicate"),
        outcome.get("sent"),
    )
    return outcome


def sweep_chat_facts(
    db: Any, *, since: datetime, until: datetime | None = None, rebuild: bool = False
) -> int:
    """Fill the chat analytics fact rows of every closed live turn in `[since, until)` that
    has none (CA-1). Returns the rows written.

    A doorway for the two callers that sit outside the chatbot package, the nightly
    scheduler tick and `scripts/chat_facts_sweep.py`: neither may import
    `app.services.chatbot`, and neither needs more than this one call. The writer is
    idempotent, so a repeat over the same range writes nothing. `rebuild` first deletes the
    range's fact rows and reloads them under the current rules (after a rule change).
    """
    from app.services.chatbot.analytics import facts

    return facts.sweep(db, since=since, until=until, rebuild=rebuild)


def label_chat_topics_job(limit: int | None = None) -> dict[str, Any]:
    """The nightly topic labeller as an RQ job on `analytics` (CA-2): label every ask with no
    topic or a stale taxonomy version. A doorway like the sweep above; the rules live in
    `app.services.chatbot.analytics.labeller`. Does nothing until taxonomy v1 has leaves."""
    from app.database import SessionLocal
    from app.services.chatbot.analytics import labeller

    db = SessionLocal()
    try:
        chat, model = labeller.production_chat(db)
        result = labeller.run(
            db, chat=chat, resolve=labeller.production_resolve(SessionLocal), model=model, limit=limit
        )
    finally:
        db.close()
    logger.info("chat topic labeller: %s", result)
    return result


def backfill_chat_history_job(
    era: str, *, limit: int | None = None, estimate: bool = False, relabel: bool = False
) -> dict[str, Any]:
    """The CA-4 history backfill of one era, in this process (no schedule: run by hand from
    `scripts/chat_backfill.py`). `estimate` counts and projects tokens and calls no model. A
    doorway like the labeller above; the rules live in
    `app.services.chatbot.analytics.backfill`."""
    from app.database import SessionLocal
    from app.services.chatbot.analytics import backfill, labeller

    db = SessionLocal()
    try:
        if estimate:
            result = backfill.estimate(db, era, relabel=relabel)
        else:
            chat, model = labeller.production_call(
                db, schema_name="chat_history_backfill", cache_key="chat-history-backfill"
            )
            result = backfill.run(
                db,
                era=era,
                chat=chat,
                resolve=labeller.production_resolve(SessionLocal),
                model=model,
                limit=limit,
                relabel=relabel,
            )
    finally:
        db.close()
    logger.info("chat history backfill: %s", result)
    return result


def enqueue_chat_topic_labeller() -> Any:
    """Queue `label_chat_topics_job` on `analytics` (the scheduler's 02:15 tick)."""
    from app.services.queue_service import enqueue_job

    return enqueue_job(label_chat_topics_job, queue_name=ANALYTICS_QUEUE, job_timeout=3 * 3600)
