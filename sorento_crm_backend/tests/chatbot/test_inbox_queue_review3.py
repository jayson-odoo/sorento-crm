"""CHAT-INBOX-QUEUE review round 3 (RED): IQ-47 and IQ-41 (completed).

UAC `documentation/plans/chatbot/chat-inbox-queue-acceptance-criteria.md`, "Review round 3".
Written against 058f0fe683, BEFORE the coder's round-3 fixes. Harness: `test_inbox_queue_order.py`;
the recovery race is injected the way round 2's IQ-41 test does it, at the SQL layer just
before recovery's requeue UPDATE.
"""
from __future__ import annotations

import threading
import time
from typing import Any

from sqlalchemy import event, text

from app.database import SessionLocal
from app.database import engine as db_engine
from app.services import queue_service
from app.services.chatbot import direct_ingress
from tests.chatbot.test_inbox_queue_order import (  # noqa: F401 - fixtures used by name
    SENDER_URL,
    assert_nothing_to_send,
    drain_key,
    iq,
    iq_serial,
    redis_client,
    wait_until,
    world,
)
from tests.chatbot.test_inbox_queue_review2 import _queue_held

RATE_REFUSAL_STAGE = "refused_rate_limit"


def test_a_redis_error_in_the_rate_limiter_never_refuses_a_message(world, monkeypatch):
    """IQ-47: the per-contact rate limiter cannot reach Redis (its script call raises). A
    covered `/chat/turn` copy is still QUEUED, not refused (no `refused_rate_limit` row, no
    429), and is answered once Redis works again; a later webhook copy of the same message
    adds nothing."""
    real_eval = queue_service.redis_conn.eval
    state = {"down": True, "rate_calls": 0}

    def eval_with_a_broken_rate_script(script, *args, **kwargs):
        if script == direct_ingress._RATE_SCRIPT:
            state["rate_calls"] += 1
            if state["down"]:
                raise ConnectionError("zzt: redis is unreachable")
        return real_eval(script, *args, **kwargs)

    monkeypatch.setattr(queue_service.redis_conn, "eval", eval_with_a_broken_rate_script)
    contact = world.contact(covered=True)
    mid = world.message(contact, time.time() - 5, "redis-blip")

    response, _ = world.chat_turn(world.body(contact, mid))
    assert response.status_code == 200, f"a Redis error must not refuse the copy: {response.status_code}"
    assert_nothing_to_send(response)
    assert state["rate_calls"] >= 1, "the queue never asked the rate limiter (test setup)"
    rows = [r for r in world.rows(contact) if r["message_id"] == str(mid)]
    assert len(rows) == 1, rows
    assert (rows[0]["status"], rows[0]["stage"]) != ("failed", RATE_REFUSAL_STAGE), (
        "a Redis error refused the message as rate-limited"
    )

    state["down"] = False
    posts = world.wait_posts(1, contact, timeout=20, settle=1.0)
    assert [world.message_of_turn(p["turn_id"]) for p in posts] == [str(mid)]
    world.webhook(world.body(contact, mid))
    time.sleep(1.5)
    assert len([r for r in world.rows(contact) if r["message_id"] == str(mid)]) == 1
    assert len(world.posts_for(contact)) == 1


def test_recovery_resend_branch_never_requeues_a_row_its_old_drain_resent_meanwhile(world):
    """IQ-41 (completed): an old drain lost its mutex but runs on. Its first POST was
    refused (logged), so recovery reads `refused` and decides to send again; meanwhile the
    old drain stamps its second attempt and delivers. The `should_resend` requeue must be a
    compare-and-set on what recovery read: exactly one delivered POST, never two."""
    module = iq()
    contact = world.contact(covered=True)
    mid = world.message(contact, time.time() - 10, "resend-cas")
    _queue_held(world, contact, [mid])
    row_id = world.row_for(contact, mid)["id"]

    db = SessionLocal()
    try:
        claimed_at = db.execute(
            text(
                "UPDATE chatbot.turns SET status = 'processing', stage = 'sending', "
                "started_at = clock_timestamp(), finished_at = now() - interval '2 seconds' "
                "WHERE id = CAST(:i AS uuid) RETURNING started_at"
            ),
            {"i": row_id},
        ).scalar()
        db.commit()
        # Attempt 1, refused before anything left: the sender's own failure log line.
        direct_ingress._log_call(
            db, row_id, contact, SENDER_URL, {"turn_id": row_id}, None, direct_ingress.REFUSED_ERROR
        )
    finally:
        db.close()

    injected = threading.Event()

    def old_drain_resends_first(conn, cursor, statement, parameters, context, executemany):
        if injected.is_set() or not statement.lstrip().upper().startswith("UPDATE"):
            return
        values = list(parameters.values()) if isinstance(parameters, dict) else list(parameters or [])
        if "queued" not in values or not any(str(v) == row_id for v in values):
            return
        injected.set()
        side = SessionLocal()
        try:
            side.execute(
                text(
                    "UPDATE chatbot.turns SET stage = 'sending', finished_at = now() "
                    "WHERE id = CAST(:i AS uuid) AND started_at = :c"
                ),
                {"i": row_id, "c": claimed_at},
            )
            side.commit()
        finally:
            side.close()
        direct_ingress.send_outcome(
            SessionLocal,
            turn_id=row_id,
            contact_id=contact,
            actions=[{"kind": "send_message", "text": "ZZT attempt 2 from the old drain", "dry_run": False}],
            reply=None,
            branch_kind=None,
        )

    world.redis.delete(drain_key(contact))
    module._reset_for_tests()
    event.listen(db_engine, "before_cursor_execute", old_drain_resends_first)
    try:
        module.sweep()
        with world.sweeper(interval=0.5):
            wait_until(lambda: len(world.posts_for(contact)) >= 2, timeout=6)
    finally:
        event.remove(db_engine, "before_cursor_execute", old_drain_resends_first)
    assert injected.is_set(), "recovery never tried to requeue the refused row (test setup)"
    assert len(world.posts_for(contact)) == 1, (
        f"{len(world.posts_for(contact))} delivered POSTs: the resend requeue applied under the "
        "old drain's second attempt"
    )
