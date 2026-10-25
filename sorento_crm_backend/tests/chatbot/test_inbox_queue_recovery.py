"""CHAT-INBOX-QUEUE: failures, crashes, shutdown, rollback and photo-read waits (RED).

Plan `documentation/plans/chatbot/PLAN-chat-inbox-queue.md` "Test list" items 9-13 and
15-17, "Zero-downtime deploy"; UAC IQ-15 .. IQ-25. The harness (World, MediaWorker, the
injectors, the recorders, the cross-worker lock) lives in `test_inbox_queue_order.py`; read
its docstring for the seams. Written BEFORE `app/services/chatbot/inbox_queue.py` exists.

Playing a dead process: rows are queued while `begin_shutdown()` holds every drain off, then
moved by SQL into the state a killed process leaves (`processing` at some stage, no drain
mutex key `chatbot:drain:{contact}`); `_reset_for_tests()` then stands in for the next
process, whose first `sweep()` must recover them. A `processing` row at stage `sending` is
one whose sender POST was stamped as attempted, with no logged result (a crash mid-POST, the
`should_resend(None)` case).
"""
from __future__ import annotations

import asyncio
import re
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from app.database import SessionLocal
from app.services.chatbot import direct_ingress
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import parser as parser_mod
from app.services.media_extract import wording
from tests.chatbot.test_inbox_queue_order import (  # noqa: F401 - fixtures used by name
    MediaWorker,
    World,
    action_texts,
    assert_nothing_to_send,
    assert_settled,
    drain_key,
    iq,
    iq_serial,
    media_worker,
    redis_client,
    send_order,
    wait_until,
    world,
)

PHOTO_TIMEOUT_SENTENCE = "I could not read that photo in time"
BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent


def _snapshot(row: dict[str, Any] | None) -> tuple:
    assert row is not None
    return (row["status"], row["stage"], row["attempt"], row["started_at"], len(row["trace"]))


def _play_dead(row_id: str, *, stage: str) -> None:
    """Leave a row the way a killed process leaves it: `processing` at `stage`."""
    db = SessionLocal()
    try:
        db.execute(
            text(
                "UPDATE chatbot.turns SET status = 'processing', stage = :s, started_at = now() "
                "WHERE id = CAST(:i AS uuid)"
            ),
            {"s": stage, "i": row_id},
        )
        db.commit()
    finally:
        db.close()


def _queued_behind(world: World, contact: str, mids: tuple[int, ...]) -> bool:
    """Every row of `mids` exists and is `queued` (the webhook inserts it synchronously)."""
    return bool(
        wait_until(
            lambda: [(world.row_for(contact, m) or {}).get("status") for m in mids] == ["queued"] * len(mids),
            timeout=3,
        )
    )


def _queue_without_draining(world: World, contact: str, mids: list[int]) -> None:
    """Queue `mids` through the webhook while every drain is held off by shutdown."""
    iq().begin_shutdown()
    for mid in mids:
        world.webhook(world.body(contact, mid))
    assert wait_until(
        lambda: [world.row_for(contact, m) and world.row_for(contact, m)["status"] for m in mids]
        == ["queued"] * len(mids),
        timeout=3,
    ), [world.row_for(contact, m) for m in mids]


# --------------------------------------------------------------------------- #
# should_resend: rule (a), one function (IQ-16, test list 10)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [("refused", True), ("timeout", False), ("http_error", False), ("ok", False), (None, False)],
)
def test_should_resend_is_true_only_when_the_post_never_left(outcome, expected):
    assert iq().should_resend(outcome) is expected


# --------------------------------------------------------------------------- #
# Failures (IQ-15, IQ-16)
# --------------------------------------------------------------------------- #


def test_engine_failure_posts_the_error_reply_once_and_the_next_row_continues(world):
    """IQ-15: a turn that fails in the engine posts the engine's error reply once, as a
    failed sync turn answers today; the contact's next row is answered after it."""
    contact = world.contact(covered=True)
    base = time.time() - 10
    m1 = world.message(contact, base, "engine-fail1")
    m2 = world.message(contact, base + 1, "engine-fail2")

    def provider_down(mid: str, block: str) -> None:
        raise parser_mod.ParserError("zzt: the provider is down")

    world.parse_hooks[str(m1)] = provider_down
    world.gate.clear()
    for mid in (m1, m2):
        response, _ = world.chat_turn(world.body(contact, mid), bound=3.0)
        assert_nothing_to_send(response)
    world.gate.set()

    posts = world.wait_posts(2, contact)
    assert world.posted_messages(contact) == [str(m1), str(m2)]
    assert engine_mod.GENERIC_ERROR_REPLY in action_texts(posts[0]), posts[0]["actions"]
    assert engine_mod.GENERIC_ERROR_REPLY not in action_texts(posts[1])
    assert world.row_for(contact, m1)["status"] == "failed"
    assert world.row_for(contact, m2)["status"] == "done"


def test_sender_refused_before_sending_is_sent_again_and_the_next_row_continues(world):
    """IQ-16, rule (a): connection refused proves the POST never left, so it is sent again;
    the contact's next row follows."""
    contact = world.contact(covered=True)
    base = time.time() - 10
    m1 = world.message(contact, base, "refused1")
    m2 = world.message(contact, base + 1, "refused2")
    world.sender_script[contact].extend(["refused", "ok", "ok"])

    for mid in (m1, m2):
        response, _ = world.chat_turn(world.body(contact, mid), bound=3.0)
        assert_nothing_to_send(response)

    world.wait_posts(3, contact)
    assert world.posted_messages(contact) == [str(m1), str(m1), str(m2)], (
        "m1 refused then re-sent once, then m2"
    )
    assert [p["behaviour"] for p in world.posts_for(contact)] == ["refused", "ok", "ok"]
    assert world.row_for(contact, m1)["status"] == "done"
    assert world.row_for(contact, m2)["status"] == "done"


@pytest.mark.parametrize("failure", ["timeout", 502], ids=["timeout", "http-502"])
def test_sender_timeout_or_error_answer_is_not_resent_and_is_flagged_for_staff(world, failure):
    """IQ-16: a timeout or an error answer may have left, so it is NOT sent again; the row is
    flagged for staff (`failed`, stage `send_unconfirmed`, a failed record on its trace) and
    the contact's next row continues."""
    contact = world.contact(covered=True)
    base = time.time() - 10
    m1 = world.message(contact, base, f"unconfirmed-{failure}-1")
    m2 = world.message(contact, base + 1, f"unconfirmed-{failure}-2")
    world.sender_script[contact].extend([failure, "ok", "ok"])

    for mid in (m1, m2):
        response, _ = world.chat_turn(world.body(contact, mid), bound=3.0)
        assert_nothing_to_send(response)

    world.wait_posts(2, contact, settle=1.5)
    assert world.posted_messages(contact) == [str(m1), str(m2)], "m1 must not be POSTed twice"
    flagged = world.row_for(contact, m1)
    assert (flagged["status"], flagged["stage"]) == ("failed", "send_unconfirmed"), flagged
    assert any(r.get("status") == "failed" for r in flagged["trace"] if isinstance(r, dict)), (
        "the staff flag must be on the turn trace"
    )
    assert world.row_for(contact, m2)["status"] == "done"


# --------------------------------------------------------------------------- #
# Crash and restart (IQ-17, IQ-18)
# --------------------------------------------------------------------------- #


def test_restart_answers_queued_rows_once_in_order_and_never_reposts_a_sending_row(world):
    """(e) IQ-17, IQ-18. A dead process left: contact A with a row at stage `sending` (its
    POST stamped as attempted, result never logged) and two queued rows; contact B with a
    row `processing` at a pre-POST stage and two queued rows; no drain mutex. The next
    process's sweep answers everything once, in send order. A's `sending` row is NOT
    re-posted (`should_resend(None)` is False) and is flagged `failed` / `send_unconfirmed`;
    B's half-run row runs again."""
    module = iq()
    a = world.contact(covered=True)
    b = world.contact(covered=True)
    base = time.time() - 20
    a_mids = [world.message(a, base + i, f"restart-a{i}") for i in range(3)]
    b_mids = [world.message(b, base + i, f"restart-b{i}") for i in range(3)]
    _queue_without_draining(world, a, a_mids)
    _queue_without_draining(world, b, b_mids)

    _play_dead(world.row_for(a, a_mids[0])["id"], stage="sending")
    _play_dead(world.row_for(b, b_mids[0])["id"], stage="understood")
    world.redis.delete(drain_key(a), drain_key(b))
    module._reset_for_tests()  # the next process

    kicked = module.sweep()
    assert kicked >= 2, f"sweep must kick both contacts, kicked {kicked}"

    world.wait_posts(5, a, b, timeout=30, settle=1.5)
    assert world.posted_messages(a) == [str(a_mids[1]), str(a_mids[2])], (
        "A: the `sending` row must not be posted again; the rest in send order"
    )
    assert world.posted_messages(b) == [str(m) for m in b_mids], "B: all three, in send order, once"
    flagged = world.row_for(a, a_mids[0])
    assert (flagged["status"], flagged["stage"]) == ("failed", "send_unconfirmed"), flagged
    for contact, mids in ((a, a_mids[1:]), (b, b_mids)):
        for mid in mids:
            assert world.row_for(contact, mid)["status"] == "done"


def test_recovery_asks_should_resend_so_rule_b_is_a_one_line_flip(world, monkeypatch):
    """Final rule 6: the crash re-send policy is ONE function. Flipped to rule (b) (always
    re-send), the same crashed `sending` row IS posted, once."""
    module = iq()
    monkeypatch.setattr(module, "should_resend", lambda outcome: True)
    contact = world.contact(covered=True)
    base = time.time() - 20
    mids = [world.message(contact, base + i, f"rule-b{i}") for i in range(2)]
    _queue_without_draining(world, contact, mids)
    _play_dead(world.row_for(contact, mids[0])["id"], stage="sending")
    world.redis.delete(drain_key(contact))
    module._reset_for_tests()

    module.sweep()
    world.wait_posts(2, contact, timeout=30, settle=1.5)
    assert world.posted_messages(contact) == [str(m) for m in mids]
    assert world.row_for(contact, mids[0])["status"] == "done"


def test_sweep_leaves_a_sync_turn_in_flight_alone(world):
    """Never double-answer: a `processing` row of the SYNC path (mode off for the contact,
    no drain mutex by nature) is not a dead queue row; a sweep must not re-run it."""
    contact = world.contact(covered=False)
    world.set_mode("off")
    mid = world.message(contact, time.time() - 5, "sync-in-flight")
    box: dict[str, Any] = {}

    world.gate.clear()

    def _call() -> None:
        box["response"], _ = world.chat_turn(world.body(contact, mid), bound=60)

    caller = threading.Thread(target=_call, daemon=True)
    caller.start()
    assert world.wait_parse_started(mid, timeout=10)
    iq().sweep()
    time.sleep(0.5)
    iq().sweep()
    world.gate.set()
    caller.join(30)

    assert box["response"].status_code == 200
    assert box["response"].json()["actions"], "the sync caller still gets its actions"
    time.sleep(1.5)
    assert world.posts_for(contact) == [], "the sweeper must not answer a sync turn a second time"
    assert [(r["status"], r["attempt"]) for r in world.rows(contact)] == [("done", 1)]
    assert world.parse_calls.count(str(mid)) == 1


# --------------------------------------------------------------------------- #
# Shutdown (IQ-19, IQ-20, IQ-25)
# --------------------------------------------------------------------------- #


def test_sigterm_mid_turn_finishes_that_row_and_leaves_later_rows_queued(world):
    """(g) IQ-19: shutdown begins while a turn is mid-run. That row gets exactly one POST
    and is marked done; the contact's later rows stay queued and untouched;
    `wait_idle` reports the drains idle."""
    module = iq()
    contact = world.contact(covered=True)
    base = time.time() - 10
    m1, m2, m3 = (world.message(contact, base + i, f"sigterm{i}") for i in range(3))

    world.gate.clear()
    world.webhook(world.body(contact, m1))
    assert world.wait_parse_started(m1, timeout=10)
    world.webhook(world.body(contact, m2))
    world.webhook(world.body(contact, m3))
    assert _queued_behind(world, contact, (m2, m3)), "m2 and m3 must be queued behind the running m1"
    before = {m: _snapshot(world.row_for(contact, m)) for m in (m2, m3)}

    module.begin_shutdown()
    world.gate.set()
    assert module.wait_idle(20) is True

    time.sleep(1.0)
    assert world.posted_messages(contact) == [str(m1)], "exactly one POST: the row that was running"
    assert world.row_for(contact, m1)["status"] == "done"
    after = {m: _snapshot(world.row_for(contact, m)) for m in (m2, m3)}
    assert after == before, f"later rows must stay queued and untouched: {before} -> {after}"
    assert str(m2) not in world.parse_calls and str(m3) not in world.parse_calls


def test_message_enqueued_during_shutdown_is_answered_by_the_next_process_in_send_order(world):
    """(h) IQ-20: messages arriving while a process shuts down are only queued; the next
    process answers them, in send order."""
    module = iq()
    contact = world.contact(covered=True)
    base = time.time() - 10
    mids = [world.message(contact, base + i, f"next-proc{i}") for i in range(3)]

    module.begin_shutdown()
    world.webhook(world.body(contact, mids[2]))
    response, _ = world.chat_turn(world.body(contact, mids[0]), bound=3.0)
    assert_nothing_to_send(response)
    world.webhook(world.body(contact, mids[1]))
    time.sleep(1.5)
    assert world.posts_for(contact) == [], "a shutting-down process takes no new rows"
    assert [world.row_for(contact, m)["status"] for m in mids] == ["queued"] * 3

    module._reset_for_tests()  # the next process
    world.redis.delete(drain_key(contact))
    module.sweep()
    world.wait_posts(3, contact, timeout=30)
    assert world.posted_messages(contact) == [str(m) for m in mids]
    assert_settled(world, contact)


def test_app_shutdown_handler_returns_only_after_the_running_row_is_posted_and_done(world):
    """(17) IQ-25: the FastAPI shutdown handler (`app.main.shutdown_event`) does not return
    while a drain is mid-turn; it returns after that row's sender POST and done mark."""
    from app import main as main_mod

    contact = world.contact(covered=True)
    base = time.time() - 10
    m1 = world.message(contact, base, "app-shutdown1")
    m2 = world.message(contact, base + 1, "app-shutdown2")

    world.gate.clear()
    world.webhook(world.body(contact, m1))
    assert world.wait_parse_started(m1, timeout=10)
    world.webhook(world.body(contact, m2))

    seen: dict[str, Any] = {}

    def _shutdown() -> None:
        asyncio.run(main_mod.shutdown_event())
        seen["returned_at"] = time.monotonic()
        seen["posts"] = list(world.posts_for(contact))
        seen["status"] = (world.row_for(contact, m1) or {}).get("status")

    handler = threading.Thread(target=_shutdown, name="zzt-iq-shutdown", daemon=True)
    handler.start()
    time.sleep(1.0)
    assert handler.is_alive(), "the shutdown handler returned while a drain was mid-turn"
    assert world.posts_for(contact) == []

    released_at = time.monotonic()
    world.gate.set()
    handler.join(30)
    assert not handler.is_alive(), "the shutdown handler never returned"
    assert seen["returned_at"] > released_at
    assert [world.message_of_turn(p["turn_id"]) for p in seen["posts"]] == [str(m1)], (
        "by the time the handler returns, the running row's POST has happened, and only it"
    )
    assert seen["posts"][0]["t_end"] <= seen["returned_at"]
    assert seen["status"] == "done", "by the time the handler returns, the row is marked done"
    assert world.row_for(contact, m2)["status"] == "queued"


def test_deploy_grace_is_above_the_longest_queued_turn():
    """IQ-21 / IQ-25 (plan "Zero-downtime deploy"): gunicorn's graceful_timeout covers the
    longest queued turn, and the deploy script stops the OLD colour with a timeout above
    gunicorn's grace, so Docker never SIGKILLs a drain that is finishing its row."""
    namespace: dict[str, Any] = {"__file__": str(BACKEND / "gunicorn.conf.py")}
    exec(compile((BACKEND / "gunicorn.conf.py").read_text(), "gunicorn.conf.py", "exec"), namespace)
    grace = namespace.get("graceful_timeout")
    assert isinstance(grace, (int, float)) and grace >= 150, f"graceful_timeout = {grace!r}"

    script = (REPO / "scripts" / "blue_green_deploy.sh").read_text()
    match = re.search(r"docker compose stop -t (\d+)[^\n]*backend_\$\{OLD\}", script)
    assert match, "the OLD colour must be stopped with an explicit `docker compose stop -t <s>`"
    assert int(match.group(1)) > grace, (match.group(0), grace)


def test_sender_timeout_lets_the_sender_answer_after_its_last_node():
    """Plan "Zero-downtime deploy": the sender answers after its last node now, so the POST
    timeout rises from 10 s to 60 s."""
    assert direct_ingress.SENDER_TIMEOUT_SECONDS >= 60


# --------------------------------------------------------------------------- #
# Rollback and Retry (IQ-22, IQ-23)
# --------------------------------------------------------------------------- #


def test_rollback_to_off_still_answers_queued_rows_once_and_new_messages_go_sync(world):
    """IQ-23: the mode is switched off with rows still queued. They are still answered,
    once, in order; a new message after that takes the sync path."""
    contact = world.contact(covered=True)
    base = time.time() - 10
    m1, m2, m3, m4 = (world.message(contact, base + i, f"rollback{i}") for i in range(4))

    world.gate.clear()
    world.webhook(world.body(contact, m1))
    assert world.wait_parse_started(m1, timeout=10)
    world.webhook(world.body(contact, m2))
    world.webhook(world.body(contact, m3))
    assert _queued_behind(world, contact, (m2, m3)), "m2 and m3 must be queued behind the running m1"

    world.set_mode("off")
    world.gate.set()
    with world.sweeper(interval=1.0):
        world.wait_posts(3, contact, timeout=30)
    assert world.posted_messages(contact) == [str(m1), str(m2), str(m3)]

    response, _ = world.chat_turn(world.body(contact, m4), bound=10.0)
    assert response.status_code == 200, response.text
    assert response.json()["duplicate"] is False and response.json()["actions"], response.json()
    time.sleep(1.5)
    assert len(world.posts_for(contact)) == 3, "the sync answer goes back to n8n, not the sender"
    assert_settled(world, contact)


def test_retry_of_a_failed_queued_turn_answers_once_even_if_the_copy_arrives_twice(world):
    """IQ-22: a queued turn failed in the engine (its error reply was POSTed); an operator
    presses Retry (the row gets `retry_requested_at`) and the Retry copy reaches `/chat/turn`
    twice at once. The message is answered once more, on attempt 2, with one POST."""
    contact = world.contact(covered=True)
    mid = world.message(contact, time.time() - 10, "retry")
    calls = {"n": 0}

    def fail_first(mid_: str, block: str) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise parser_mod.ParserError("zzt: the provider is down")

    world.parse_hooks[str(mid)] = fail_first
    response, _ = world.chat_turn(world.body(contact, mid), bound=3.0)
    assert_nothing_to_send(response)
    world.wait_posts(1, contact)
    first = world.row_for(contact, mid)
    assert first["status"] == "failed", first

    db = SessionLocal()
    try:
        db.execute(
            text("UPDATE chatbot.turns SET retry_requested_at = now() WHERE id = CAST(:i AS uuid)"),
            {"i": first["id"]},
        )
        db.commit()
    finally:
        db.close()

    answers: list[Any] = []

    def _retry_copy() -> None:
        answers.append(world.chat_turn(world.body(contact, mid), bound=5.0)[0])

    copies = [threading.Thread(target=_retry_copy) for _ in range(2)]
    for copy in copies:
        copy.start()
    for copy in copies:
        copy.join(10)
    assert len(answers) == 2
    for answer in answers:
        assert_nothing_to_send(answer)

    posts = world.wait_posts(2, contact, timeout=20, settle=1.5)
    assert len(posts) == 2, f"the error reply, then ONE answer for the retry: {len(posts)} POSTs"
    assert engine_mod.GENERIC_ERROR_REPLY not in action_texts(posts[1])
    attempts = sorted((r["attempt"], r["status"]) for r in world.rows(contact))
    assert attempts == [(1, "failed"), (2, "done")], attempts


# --------------------------------------------------------------------------- #
# Photo reads across a worker restart (IQ-24, test list 15-16)
# --------------------------------------------------------------------------- #


def test_photo_read_slower_than_the_sync_wait_is_waited_for_not_timed_out(world, media_worker, monkeypatch):
    """(15) IQ-24: queue mode, the photo's read is not finished within
    `media_sync_wait_seconds` (1 s here; the worker is down). No "could not read it in time"
    reply goes out; the row keeps waiting for the same read (on the drain, or parked, IQ-30);
    when the read lands the photo is answered once, and the contact's later text, queued
    behind it, after it."""
    from app.services import media_access_service

    monkeypatch.setattr(media_access_service, "SYNC_WAIT_MIN_SECONDS", 1)
    contact = world.contact(covered=True, media=True)
    world.set_mode("contacts", media_sync_wait_seconds=1, media_burst_limit=1000)
    media_worker.mode = "manual"
    base = time.time() - 10
    photo = world.message(contact, base, "slow-photo")
    later = world.message(contact, base + 2, "slow-text")

    world.webhook(world.body(contact, photo, photo=True))
    assert wait_until(lambda: media_worker.calls, timeout=10), "the photo's read was never requested"
    assert media_worker.message_of_job(media_worker.calls[0]) == str(photo), "the read is the photo's"
    world.webhook(world.body(contact, later, text_value="check stock (slow-text)"))

    time.sleep(3.0)  # three times the sync wait
    assert world.posts_for(contact) == [], (
        "nothing may be POSTed while the read is pending: no timeout reply, no overtaking text"
    )
    # Waiting (`processing`) or parked to free the thread (`queued`, IQ-30); never closed.
    assert world.row_for(contact, photo)["status"] in ("processing", "queued")
    assert world.row_for(contact, later)["status"] == "queued"
    iq().sweep()
    time.sleep(1.0)
    assert len(media_worker.calls) == 1, (
        "a sweep (or a parked row's next run) resumes the same read; it never starts a second one"
    )
    assert world.posts_for(contact) == []

    media_worker.complete(media_worker.calls[0])
    posts = world.wait_posts(2, contact, timeout=30)
    assert world.posted_messages(contact) == [str(photo), str(later)]
    for post in posts:
        assert not any(PHOTO_TIMEOUT_SENTENCE in t for t in action_texts(post)), post["actions"]
    assert world.row_for(contact, photo)["status"] == "done"


def test_abandoned_read_job_is_read_again_once_and_answered_once(world, media_worker):
    """(16) IQ-24: the worker abandoned the photo's read (killed mid-job: the job row stays
    `running`, the RQ job ends `failed` with no result). The read is attempted again once,
    and the photo is answered once from it."""
    contact = world.contact(covered=True, media=True)
    world.set_mode("contacts", media_burst_limit=1000)
    media_worker.mode = "abandon_first"
    media_worker.delay = 0.3
    photo = world.message(contact, time.time() - 5, "abandoned-photo")

    world.webhook(world.body(contact, photo, photo=True))
    posts = world.wait_posts(1, contact, timeout=60, settle=1.5)
    assert len(posts) == 1, f"one photo, one POST: got {len(posts)}"
    assert len(media_worker.calls) == 2, f"read once, then again once: {media_worker.calls}"
    assert [media_worker.message_of_job(j) for j in media_worker.calls] == [str(photo), str(photo)], (
        "the second read must be the re-read of the same photo"
    )
    texts = action_texts(posts[0])
    assert not any(PHOTO_TIMEOUT_SENTENCE in t for t in texts), texts
    assert wording.nothing_read() not in texts, "an abandoned read is not a failed read"
    assert world.row_for(contact, photo)["status"] == "done"
