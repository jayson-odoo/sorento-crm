"""CHAT-INBOX-QUEUE review round 1 (RED): IQ-26 .. IQ-36.

UAC `documentation/plans/chatbot/chat-inbox-queue-acceptance-criteria.md`, "Review round 1
additions". Written against 817cb53f75, BEFORE the coder's round-1 fixes. The harness (World,
MediaWorker, the injectors and recorders, the cross-worker lock) is the one in
`test_inbox_queue_order.py`; read its docstring for the seams. New here:

* `World.verdicts[message_id]` makes the stubbed parser return a given verdict, so a turn can
  route to the casual (`low_signal`) lane or the escalation (`out_of_scope`) lane instead of
  the business arm every earlier test used.
* The escalation lane is replaced at `engine.run_escalation_lane` (the module-level name the
  engine documents for this) by a stub that counts its calls per message. The real lane
  draws a round-robin assignee and commits an SLA row inside that call, so ONE call is one
  draw and one SLA row (IQ-27).
* IQ-26's oracle is the sync path itself: the same verdict, through `/chat/turn` for a
  contact the switch does not cover, gives the actions the queue must POST for a covered one.
"""
from __future__ import annotations

import logging
import os
import socket
import subprocess
import sys
import textwrap
import threading
import time
import uuid
from collections import defaultdict
from typing import Any

import httpx
import pytest
from sqlalchemy import text

from app.database import SessionLocal
from app.services.chatbot import direct_ingress
from app.services.chatbot import engine as engine_mod
from app.tasks import chat_turns
from tests.chatbot.test_inbox_queue_order import (  # noqa: F401 - fixtures used by name
    _CURRENT,
    SENDER_URL,
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
    wait_until,
    world,
)

BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# The real lookup, captured before any World replaces it (IQ-31 drives it for real).
REAL_LOOKUP = direct_ingress._lookup_contact

CASUAL = {"message_type": "casual", "domain_hint": None, "intent_hint": None, "entities": []}
WANTS_A_HUMAN = {
    "message_type": "request_for_help",
    "intent_hint": None,
    "domain_hint": None,
    "scope_intent": None,
    "user_goal": "wants a human",
    "entities": [],
    "routing": {"suggested_team": "customer_service", "suggested_agent": "general_enquiries", "team_source": "inferred"},
    "escalation": {"is_escalation_confirmation": True, "company_pick": None},
}
CLARIFY_TEXT = "ZZT which company should take this, Alpha or Beta?"
ROUTED_TEXT = "ZZT a colleague will reply to you here shortly."


class EscalationLane:
    """Stands in for `lanes.escalation.run`; one call is one draw + one SLA row."""

    def __init__(self, arm: str) -> None:
        self.arm = arm
        self.calls: dict[str | None, int] = defaultdict(int)

    def __call__(self, ctx, item, *, dry_run=False, session_factory=None):
        self.calls[getattr(_CURRENT, "message_id", None)] += 1
        if self.arm == "clarify":
            return {
                "arm": "clarify",
                "clarify": {
                    "branch_kind": "out_of_scope",
                    "team": "customer_service",
                    "routing_source": "multi_company_unpicked",
                    "clarify_company": True,
                    "clarify_text": CLARIFY_TEXT,
                },
                "actions": [{"kind": "send_message", "text": CLARIFY_TEXT, "quick_replies": None, "dry_run": dry_run}],
                "pending": {"kind": "company_clarify"},
                "routing": None,
            }
        return {
            "arm": "human-intervention",
            "clarify": None,
            "actions": [
                {"kind": "assign_conversation", "respond_user_id": "zzt-respond-user-1", "dry_run": dry_run},
                {"kind": "add_comment", "text": "ZZT escalated by the bot", "mention_user_ids": ["zzt-respond-user-1"], "dry_run": dry_run},
                {"kind": "send_message", "text": ROUTED_TEXT, "quick_replies": None, "dry_run": dry_run},
            ],
            "pending": None,
            "routing": None,
        }


def _shape(actions: list[dict[str, Any]]) -> list[tuple[str, str | None]]:
    return [(str(a.get("kind")), a.get("text")) for a in actions if isinstance(a, dict)]


def _queue_without_draining(world: World, contact: str, mids: list[int]) -> None:
    iq().begin_shutdown()
    for mid in mids:
        world.webhook(world.body(contact, mid))
    assert wait_until(
        lambda: [(world.row_for(contact, m) or {}).get("status") for m in mids] == ["queued"] * len(mids),
        timeout=3,
    )


# --------------------------------------------------------------------------- #
# IQ-26: every lane answers in queue mode exactly as in sync mode
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("lane", ["casual", "out_of_scope_clarify", "escalation_accept", "escalation_offer"])
def test_every_lane_answers_in_queue_mode_as_it_does_in_sync_mode(world, monkeypatch, lane):
    """IQ-26: a casual / low-signal verdict, an out-of-scope verdict (the lane's clarify
    arm), an escalation accept (assignment) and an escalation offer each POST, once, the
    actions the sync path returns for the same verdict, and the row ends `done`. Never the
    generic error reply because the row was queued."""
    verdict = {"casual": CASUAL, "escalation_offer": {}}.get(lane, WANTS_A_HUMAN)
    stub = EscalationLane("clarify" if lane == "out_of_scope_clarify" else "assign")
    monkeypatch.setattr(engine_mod, "run_escalation_lane", stub)

    sync_contact = world.contact(covered=False)
    queued_contact = world.contact(covered=True)
    base = time.time() - 10
    sync_mid = world.message(sync_contact, base, f"{lane}-sync")
    queued_mid = world.message(queued_contact, base, f"{lane}-queued")
    world.verdicts[str(sync_mid)] = verdict
    world.verdicts[str(queued_mid)] = verdict

    sync, _ = world.chat_turn(world.body(sync_contact, sync_mid, text_value=f"hello there ({lane}-sync)"), bound=20.0)
    assert sync.status_code == 200, sync.text
    expected = _shape(sync.json()["actions"])
    assert expected, f"the sync path answers this verdict: {sync.json()}"
    assert engine_mod.GENERIC_ERROR_REPLY not in [t for _, t in expected], "the oracle itself failed"

    queued, _ = world.chat_turn(world.body(queued_contact, queued_mid, text_value=f"hello there ({lane}-queued)"))
    assert_nothing_to_send(queued)
    posts = world.wait_posts(1, queued_contact, settle=1.5)
    assert len(posts) == 1, f"one message, one POST: {len(posts)}"
    assert engine_mod.GENERIC_ERROR_REPLY not in action_texts(posts[0]), (
        f"{lane} answered the generic error in queue mode: {posts[0]['actions']}"
    )
    assert _shape(posts[0]["actions"]) == expected, (posts[0]["actions"], expected)
    if lane == "escalation_accept":
        assert [a["kind"] for a in posts[0]["actions"]].count("assign_conversation") == 1
    row = world.row_for(queued_contact, queued_mid)
    assert row["status"] == "done", (row["status"], row["stage"], row["error"])


# --------------------------------------------------------------------------- #
# IQ-27: give way BEFORE a side effect that cannot be undone
# --------------------------------------------------------------------------- #


def test_escalation_gives_way_before_its_sla_row_and_draw(world, monkeypatch):
    """IQ-27: an escalation turn (E, sent second) is mid-run when an earlier-sent message P is
    queued. E gives way and runs again after P; across both runs the lane's SLA row and
    round-robin draw are made exactly once, and each message gets one POST, P first."""
    stub = EscalationLane("assign")
    monkeypatch.setattr(engine_mod, "run_escalation_lane", stub)
    contact = world.contact(covered=True)
    base = time.time() - 10
    p_mid = world.message(contact, base, "giveway-p")
    e_mid = world.message(contact, base + 2, "giveway-e")
    world.verdicts[str(e_mid)] = WANTS_A_HUMAN

    world.gate.clear()
    response, _ = world.chat_turn(world.body(contact, e_mid, text_value="talk to a person (giveway-e)"))
    assert_nothing_to_send(response)
    assert world.wait_parse_started(e_mid, timeout=10)
    response, _ = world.chat_turn(world.body(contact, p_mid), bound=3.0)
    assert_nothing_to_send(response)
    world.gate.set()

    world.wait_posts(2, contact, timeout=30, settle=1.5)
    assert world.posted_messages(contact) == [str(p_mid), str(e_mid)]
    assert world.parse_calls.count(str(e_mid)) == 2, "E gave way once and ran again"
    assert stub.calls[str(e_mid)] == 1, (
        f"the escalation's SLA row and draw were made {stub.calls[str(e_mid)]} times for one message"
    )


# --------------------------------------------------------------------------- #
# IQ-28: shutdown starts at the signal
# --------------------------------------------------------------------------- #

_SIGTERM_CHILD = textwrap.dedent(
    """
    import asyncio, os, signal, sys, threading, time
    sys.path.insert(0, os.getcwd())
    import httpx
    import uvicorn
    from starlette.responses import StreamingResponse
    from app.main import app
    from app.services.chatbot import inbox_queue

    began = []
    real_begin = inbox_queue.begin_shutdown

    def recording_begin():
        began.append(time.monotonic())
        real_begin()

    inbox_queue.begin_shutdown = recording_begin

    async def forever():
        while True:
            yield b"data: zzt\\n\\n"
            await asyncio.sleep(0.2)

    @app.get("/zzt-iq-stream")
    async def zzt_stream():
        return StreamingResponse(forever(), media_type="text/event-stream")

    port = int(sys.argv[1])
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", timeout_graceful_shutdown=6))

    def probe():
        while not server.started:
            time.sleep(0.05)
        got = threading.Event()

        def reader():
            try:
                with httpx.Client(trust_env=False, timeout=30) as client:
                    with client.stream("GET", f"http://127.0.0.1:{port}/zzt-iq-stream") as r:
                        for _ in r.iter_bytes():
                            got.set()
            except Exception:
                pass

        threading.Thread(target=reader, daemon=True).start()
        if not got.wait(15):
            print("STREAM_FAILED", flush=True)
            os._exit(3)
        sent = time.monotonic()
        os.kill(os.getpid(), signal.SIGTERM)
        flag = getattr(inbox_queue, "_shutting_down", None)
        while time.monotonic() < sent + 2.0 and not began:
            if flag is not None and flag.is_set():
                began.append(time.monotonic())
                break
            time.sleep(0.02)
        print("BEGUN_AFTER", (began[0] - sent) if began else -1, flush=True)

    threading.Thread(target=probe, daemon=True).start()
    server.run()
    print("EXITED", flush=True)
    """
)


def test_sigterm_begins_inbox_shutdown_at_once_even_with_a_stream_open(iq_serial, tmp_path):
    """IQ-28 (a): the real app under a real uvicorn server, with a long-lived streaming
    connection open (a staff event stream). On SIGTERM the inbox stops taking rows at once
    (`inbox_queue.begin_shutdown`), not only once every connection has closed and the
    lifespan shutdown finally runs."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    script = tmp_path / "zzt_iq_sigterm_child.py"
    script.write_text(_SIGTERM_CHILD)
    env = dict(os.environ)
    env.pop("ENABLE_SCHEDULER", None)
    proc = subprocess.run(
        [sys.executable, str(script), str(port)],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    lines = [line for line in proc.stdout.splitlines() if line.startswith(("BEGUN_AFTER", "STREAM_FAILED"))]
    assert lines and lines[0].startswith("BEGUN_AFTER"), (proc.stdout[-2000:], proc.stderr[-3000:])
    began_after = float(lines[0].split()[1])
    assert 0 <= began_after < 1.0, (
        f"begin_shutdown ran {began_after}s after SIGTERM (-1 = not within 2 s): the drains kept "
        "taking rows while a streaming connection held the server open"
    )


def test_shutdown_parks_a_row_waiting_on_a_photo_read(world, media_worker):
    """IQ-28 (b): a drain waiting on a photo read when shutdown begins parks the row (back to
    `queued`, no POST, nothing written) and lets go promptly; the next process answers it,
    once, when the read lands."""
    module = iq()
    contact = world.contact(covered=True, media=True)
    world.set_mode("contacts", media_burst_limit=1000)
    media_worker.mode = "manual"
    photo = world.message(contact, time.time() - 5, "park-photo")
    initial_state = world.session_vars(contact)

    world.webhook(world.body(contact, photo, photo=True))
    assert wait_until(lambda: media_worker.calls, timeout=10), "the read was never requested"
    time.sleep(0.5)

    started = time.monotonic()
    module.begin_shutdown()
    assert module.wait_idle(5) is True, "a drain waiting on a read must let go promptly on shutdown"
    assert time.monotonic() - started < 5
    row = world.row_for(contact, photo)
    assert row["status"] == "queued", f"the waiting row must be parked: {row['status']} / {row['stage']}"
    assert world.posts_for(contact) == []
    assert world.session_vars(contact) == initial_state

    module._reset_for_tests()  # the next process
    world.redis.delete(drain_key(contact))
    media_worker.complete(media_worker.calls[0])
    module.sweep()
    posts = world.wait_posts(1, contact, timeout=30, settle=1.5)
    assert [world.message_of_turn(p["turn_id"]) for p in posts] == [str(photo)]


# --------------------------------------------------------------------------- #
# IQ-29: one answer per row even when the mutex is lost
# --------------------------------------------------------------------------- #


def test_lost_mutex_mid_turn_still_answers_the_row_once(world):
    """IQ-29: the drain mutex disappears while a turn runs (Redis restart, eviction) and a
    sweep starts a second drain for the contact. The row is still answered exactly once."""
    contact = world.contact(covered=True)
    mid = world.message(contact, time.time() - 5, "lost-mutex")

    world.gate.clear()
    world.webhook(world.body(contact, mid))
    assert world.wait_parse_started(mid, timeout=10)
    world.redis.delete(drain_key(contact))
    iq().sweep()
    time.sleep(1.0)
    world.gate.set()

    posts = world.wait_posts(1, contact, timeout=20, settle=2.0)
    assert len(posts) == 1, f"one message, {len(posts)} POSTs after the mutex was lost"
    assert world.row_for(contact, mid)["status"] == "done"


# --------------------------------------------------------------------------- #
# IQ-30: fairness, parked photo reads, sender timeouts
# --------------------------------------------------------------------------- #


def test_a_long_backlog_does_not_hold_the_only_pool_thread(world, monkeypatch):
    """IQ-30: with one pool thread, contact A's six queued rows do not starve contact B,
    whose one row arrived after them: B is answered before A's last row."""
    assert wait_until(lambda: chat_turns._in_flight == 0, timeout=30), "a previous test left a drain on the pool"
    monkeypatch.setattr(chat_turns, "DIRECT_TURN_THREADS", 1)
    a = world.contact(covered=False)
    b = world.contact(covered=False)
    world.cover(a, b)
    world.parse_sleep = 0.3
    base = time.time() - 20
    a_mids = [world.message(a, base + i, f"fair-a{i}") for i in range(6)]
    b_mid = world.message(b, base + 10, "fair-b")

    world.gate.clear()
    for mid in a_mids:
        response, _ = world.chat_turn(world.body(a, mid), bound=3.0)
        assert_nothing_to_send(response)
    response, _ = world.chat_turn(world.body(b, b_mid), bound=3.0)
    assert_nothing_to_send(response)
    world.gate.set()

    with world.sweeper(interval=0.5):
        world.wait_posts(7, a, b, timeout=40, settle=1.0)
    order = [p["contact_id"] for p in world.posts_for(a, b)]
    assert order.count(a) == 6 and order.count(b) == 1, f"every row answered once: {order}"
    last_a = len(order) - 1 - order[::-1].index(a)
    assert order.index(b) < last_a, f"B waited behind A's whole backlog: {order}"


def test_a_pending_photo_read_frees_the_thread_and_still_goes_first(world, media_worker, monkeypatch):
    """IQ-30: with one pool thread, a photo read not finished within the sync wait parks its
    row and frees the thread, so another contact is answered meanwhile; when the read lands
    the photo is answered before that contact's later text."""
    from app.services import media_access_service

    assert wait_until(lambda: chat_turns._in_flight == 0, timeout=30), "a previous test left a drain on the pool"
    monkeypatch.setattr(chat_turns, "DIRECT_TURN_THREADS", 1)
    monkeypatch.setattr(media_access_service, "SYNC_WAIT_MIN_SECONDS", 1)
    a = world.contact(covered=False, media=True)
    b = world.contact(covered=False)
    world.cover(a, b)
    world.set_mode("contacts", media_sync_wait_seconds=1, media_burst_limit=1000)
    media_worker.mode = "manual"
    base = time.time() - 10
    photo = world.message(a, base, "park-a-photo")
    later = world.message(a, base + 2, "park-a-text")
    other = world.message(b, base + 3, "park-b-text")

    with world.sweeper(interval=0.5):
        world.webhook(world.body(a, photo, photo=True))
        assert wait_until(lambda: media_worker.calls, timeout=10), "A's photo read was never requested"
        world.webhook(world.body(a, later, text_value="check stock (park-a-text)"))
        world.webhook(world.body(b, other))
        assert wait_until(lambda: world.posts_for(b), timeout=15), (
            "B was never answered while A's photo read was pending: the read held the only thread"
        )
        assert world.posts_for(a) == []
        media_worker.complete(media_worker.calls[0])
        world.wait_posts(2, a, timeout=30)
    assert world.posted_messages(a) == [str(photo), str(later)]
    assert len(media_worker.calls) == 1, "the parked row resumed the same read"


def test_sender_connect_timeout_is_short_and_read_timeout_long(world, monkeypatch):
    """IQ-30: the sender POST gives up connecting within 5 s (a dead sender must not hold a
    pool thread for a minute) but still waits 60 s for an answer."""
    seen: dict[str, Any] = {}

    def capture(url, **kwargs):
        seen["timeout"] = kwargs.get("timeout")
        return world._fake_post(url, **kwargs)

    monkeypatch.setattr(httpx, "post", capture)
    contact = world.contact(covered=True)
    direct_ingress.send_outcome(
        SessionLocal,
        turn_id=str(uuid.uuid4()),
        contact_id=contact,
        actions=[{"kind": "send_message", "text": "zzt", "dry_run": False}],
        reply=None,
        branch_kind=None,
    )
    timeout = seen.get("timeout")
    if isinstance(timeout, httpx.Timeout):
        connect, read = timeout.connect, timeout.read
    else:
        connect = read = timeout
    assert connect is not None and connect <= 5, f"connect timeout {connect!r}"
    assert read is not None and read >= 60, f"read timeout {read!r}"


# --------------------------------------------------------------------------- #
# IQ-31: a failed takeover lookup never answers, and backs off
# --------------------------------------------------------------------------- #


def test_failed_contact_lookup_never_answers_and_backs_off(world, monkeypatch):
    """IQ-31: respond.io's contact lookup (the takeover check) fails. The row is not
    answered: it goes back to `queued`, and the contact backs off (a few attempts in 5 s,
    not one per sweep). Once the lookup works again the row is answered once."""
    from app.services.integration_service import RespondClient

    state = {"down": True, "attempts": 0}

    def counting_lookup(db, contact_id):
        state["attempts"] += 1
        return REAL_LOOKUP(db, contact_id)

    class _Client:
        def __init__(self, ident):
            self.ident = ident

        def get_contact_by_identifier(self, ident):
            return {"id": ident, "firstName": "Zzt", "custom_fields": [{"name": "is_human_intervened", "value": "false"}]}

    def for_identifier(cls, db, ident):
        if state["down"]:
            raise RuntimeError("zzt: respond.io is unreachable")
        return _Client(ident)

    monkeypatch.setattr(direct_ingress, "_lookup_contact", counting_lookup)
    monkeypatch.setattr(RespondClient, "for_identifier", classmethod(for_identifier))
    contact = world.contact(covered=True)
    mid = world.message(contact, time.time() - 5, "lookup-down")

    with world.sweeper(interval=0.5):
        world.webhook(world.body(contact, mid))
        time.sleep(5.0)
        assert world.posts_for(contact) == [], "a failed takeover check must not answer"
        assert world.row_for(contact, mid)["status"] == "queued", world.row_for(contact, mid)["status"]
        assert 1 <= state["attempts"] <= 4, f"{state['attempts']} lookups in 5 s: no backoff"
        state["down"] = False
        posts = world.wait_posts(1, contact, timeout=40, settle=1.5)
    assert len(posts) == 1
    assert world.row_for(contact, mid)["status"] == "done"


# --------------------------------------------------------------------------- #
# IQ-32, IQ-33: gates and the pile-up cap at enqueue
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("gate", ["outgoing", "staff", "not_whatsapp"])
def test_chat_turn_applies_the_structural_gates_before_queueing(world, gate):
    """IQ-32: `/chat/turn` queues incoming customer WhatsApp messages only."""
    contact = world.contact(covered=True)
    mid = world.message(contact, time.time() - 5, f"turn-gate-{gate}")
    body = world.body(contact, mid)
    if gate == "outgoing":
        body["event_type"] = "message.sent"
        body["message"]["traffic"] = "outgoing"
        body["message"]["sender"] = {"source": "api"}
    elif gate == "staff":
        body["message"]["sender"] = {"source": "user", "userId": 5}
    else:
        body["channel"] = {"id": 13, "name": "FB", "source": "facebook"}

    response, _ = world.chat_turn(body, bound=10.0)
    assert response.status_code in (200, 422), response.text
    time.sleep(2.0)
    queued = [r for r in world.rows(contact) if r["status"] == "queued" or iq().inbox_records(r["trace"])]
    assert queued == [], f"/chat/turn queued a `{gate}` message: {[(r['status'], r['stage']) for r in queued]}"
    assert world.posts_for(contact) == []


def test_a_contact_cannot_pile_up_more_than_200_queued_rows(world, caplog):
    """IQ-33: with 200 rows already queued for a contact, a further copy is not queued and is
    logged as an error."""
    from app.services.chatbot.contracts import Envelope

    module = iq()
    contact = world.contact(covered=True)
    module.begin_shutdown()  # nothing may drain the pile while the test builds it
    base = time.time() - 60
    db = SessionLocal()
    try:
        for i in range(200):
            mid = world.message(contact, base + i * 0.01, f"pile{i:03d}")
            body = world.body(contact, mid)
            module.enqueue(db, Envelope(message=body, contact=body["contact"], ingress="webhook"))
    finally:
        db.close()
    assert sum(1 for r in world.rows(contact) if r["status"] == "queued") == 200

    caplog.set_level(logging.ERROR)
    extra = world.message(contact, base + 5, "pile-201")
    response, _ = world.chat_turn(world.body(contact, extra), bound=10.0)
    assert response.status_code in (200, 429, 503), response.text
    refused = world.row_for(contact, extra)
    assert refused is None or not iq().inbox_records(refused["trace"]), "the 201st copy must not be queued"
    assert sum(1 for r in world.rows(contact) if r["status"] == "queued") == 200
    assert any(r.levelno >= logging.ERROR for r in caplog.records), "the refusal must be logged as an error"


# --------------------------------------------------------------------------- #
# IQ-34, IQ-35: recovery and stalled reads
# --------------------------------------------------------------------------- #


def test_recovered_row_whose_logged_send_was_ok_is_done_not_flagged(world):
    """IQ-34: a dead process left a row at stage `sending` whose sender POST was logged `ok`
    before it died. Recovery marks it done; it is neither re-posted nor flagged."""
    module = iq()
    contact = world.contact(covered=True)
    mid = world.message(contact, time.time() - 10, "recover-ok")
    _queue_without_draining(world, contact, [mid])
    row_id = world.row_for(contact, mid)["id"]

    db = SessionLocal()
    try:
        db.execute(
            text(
                "UPDATE chatbot.turns SET status = 'processing', stage = 'sending', "
                "finished_at = now() - interval '2 seconds' WHERE id = CAST(:i AS uuid)"
            ),
            {"i": row_id},
        )
        db.commit()
        # The sender's own success log line, written by the real writer.
        direct_ingress._log_call(db, row_id, contact, SENDER_URL, {"turn_id": row_id}, 200, None)
    finally:
        db.close()
    world.redis.delete(drain_key(contact))
    module._reset_for_tests()

    module.sweep()
    assert wait_until(lambda: world.row_for(contact, mid)["status"] != "processing", timeout=15)
    time.sleep(1.0)
    row = world.row_for(contact, mid)
    assert (row["status"], row["stage"]) != ("failed", "send_unconfirmed"), "a logged ok is not unconfirmed"
    assert row["status"] == "done", (row["status"], row["stage"])
    assert world.posts_for(contact) == [], "a POST logged ok is not sent again"


def test_a_stalled_read_is_read_again_without_waiting_for_rq(world, media_worker):
    """IQ-35: the photo's read job row has been `running` far longer than any read takes and
    RQ has NOT marked the job failed (its registry cleanup has not run). It is treated as
    abandoned and read again once; the photo is answered once."""
    contact = world.contact(covered=True, media=True)
    world.set_mode("contacts", media_burst_limit=1000)
    media_worker.mode = "stall_first"
    media_worker.delay = 0.3
    photo = world.message(contact, time.time() - 5, "stalled-photo")

    world.webhook(world.body(contact, photo, photo=True))
    posts = world.wait_posts(1, contact, timeout=40, settle=1.5)
    assert len(posts) == 1, f"one photo, one POST: got {len(posts)}"
    assert len(media_worker.calls) == 2, f"read once, then again once: {media_worker.calls}"
    assert [media_worker.message_of_job(j) for j in media_worker.calls] == [str(photo), str(photo)]
    assert world.row_for(contact, photo)["status"] == "done"


# --------------------------------------------------------------------------- #
# IQ-36: the sweeper's query has an index
# --------------------------------------------------------------------------- #


def test_the_sweeper_query_is_served_by_a_partial_index():
    """IQ-36: a partial index on `chatbot.turns` limited to `queued` / `processing` rows."""
    db = SessionLocal()
    try:
        defs = [
            row[0]
            for row in db.execute(
                text("SELECT indexdef FROM pg_indexes WHERE schemaname = 'chatbot' AND tablename = 'turns'")
            )
        ]
    finally:
        db.close()
    partial = [d for d in defs if " WHERE " in d.upper() and "queued" in d and "processing" in d]
    assert partial, f"no partial index on chatbot.turns over queued/processing rows: {defs}"


# --------------------------------------------------------------------------- #
# Round 1b. IQ-37: queue mode needs a configured sender
# --------------------------------------------------------------------------- #


def _sender_logs(turn_id: str) -> list[tuple[str, int | None]]:
    db = SessionLocal()
    try:
        return [
            (row[0], row[1])
            for row in db.execute(
                text(
                    "SELECT status, status_code FROM integration_log WHERE integration_channel = :ch "
                    "AND business_table = 'chatbot.turns' AND business_id = :b ORDER BY created_at"
                ),
                {"ch": direct_ingress.INTEGRATION_CHANNEL, "b": turn_id},
            )
        ]
    finally:
        db.close()


@pytest.mark.parametrize("missing", ["url_and_key", "key"])
def test_queue_mode_applies_only_with_a_configured_sender(world, missing):
    """IQ-37: the switch covers the contact but the workspace has no chatbot sender (no URL
    and key, or a URL with no key). `/chat/turn` keeps the sync path and returns the turn's
    actions; nothing is queued, so nothing can be stranded; the webhook copy queues nothing.

    Mode `contacts` listing this contact rather than `all`: the settings row is shared with
    other test files running beside this one, and `all` would cover their contacts too.
    """
    contact = world.contact(covered=True)
    world.workspace.chatbot_sender_key_ciphertext = None
    if missing == "url_and_key":
        world.workspace.chatbot_sender_url = None
    base = time.time() - 10
    m1 = world.message(contact, base, f"no-sender-{missing}-1")
    m2 = world.message(contact, base + 1, f"no-sender-{missing}-2")

    response, _ = world.chat_turn(world.body(contact, m1), bound=20.0)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["duplicate"] is False and body["actions"], (
        f"with no sender configured a covered /chat/turn must answer synchronously: {body}"
    )
    row = world.row_for(contact, m1)
    assert row["status"] == "done" and not iq().inbox_records(row["trace"]), (row["status"], row["stage"])

    world.webhook(world.body(contact, m2))
    time.sleep(1.5)
    assert world.row_for(contact, m2) is None, "with no sender configured the webhook queues nothing"
    assert world.posts_for(contact) == [] and world.stray_posts == []


# --------------------------------------------------------------------------- #
# Round 1b. Sender behaviour the deleted direct-ingress job tests covered, on the drain
# --------------------------------------------------------------------------- #


def test_sender_url_refused_by_the_guard_posts_nothing_flags_the_row_and_the_next_continues(world, monkeypatch):
    """Ported from `test_direct_ingress.py::test_sender_url_guarded`: the sender URL fails the
    outbound guard at use time (a loopback host). No POST leaves, the row ends flagged
    (`failed` / `send_unconfirmed`) with failed log rows; the contact's next row is still
    answered once the URL is fixed."""
    from app.services import outbound_url_guard

    real_guard = outbound_url_guard.assert_safe_outbound_url

    def guard(url: str, label: str) -> None:
        # The real guard for the refused URL; the test's own sender host does not resolve,
        # so the real guard would refuse it too once the URL is fixed.
        if url == SENDER_URL:
            return None
        real_guard(url, label=label)

    monkeypatch.setattr(direct_ingress, "assert_safe_outbound_url", guard)
    world.workspace.chatbot_sender_url = "https://127.0.0.1/webhook/zzt-iq"
    contact = world.contact(covered=True)
    base = time.time() - 10
    m1 = world.message(contact, base, "guard-1")
    m2 = world.message(contact, base + 1, "guard-2")

    def fix_the_url(mid: str, block: str) -> None:
        world.workspace.chatbot_sender_url = SENDER_URL

    world.parse_hooks[str(m2)] = fix_the_url
    world.gate.clear()
    for mid in (m1, m2):
        response, _ = world.chat_turn(world.body(contact, mid), bound=3.0)
        assert_nothing_to_send(response)
    world.gate.set()

    world.wait_posts(1, contact, timeout=30, settle=1.5)
    assert world.stray_posts == [], f"a POST left for a refused URL: {world.stray_posts}"
    assert world.posted_messages(contact) == [str(m2)], "only the second row, after the URL was fixed"
    flagged = world.row_for(contact, m1)
    assert (flagged["status"], flagged["stage"]) == ("failed", "send_unconfirmed"), flagged
    logs = _sender_logs(flagged["id"])
    assert logs and all(status == "failed" for status, _ in logs), logs
    assert world.row_for(contact, m2)["status"] == "done"


@pytest.mark.parametrize("failure", [502, "timeout"], ids=["http-502", "timeout"])
def test_a_failed_sender_post_writes_the_failed_log_row_and_the_sent_trace_record(world, failure):
    """Ported from `test_direct_ingress.py::test_sender_failure_is_recorded`: a failed POST
    writes ONE failed outbound integration log row (a final status, so nothing re-sends it)
    and a failed `sent` record on the turn's trace."""
    contact = world.contact(covered=True)
    mid = world.message(contact, time.time() - 5, f"recorded-{failure}")
    world.sender_script[contact].append(failure)

    response, _ = world.chat_turn(world.body(contact, mid))
    assert_nothing_to_send(response)
    world.wait_posts(1, contact, settle=1.5)
    row = world.row_for(contact, mid)
    logs = _sender_logs(row["id"])
    expected_code = failure if isinstance(failure, int) else None
    assert logs == [("failed", expected_code)], logs
    sent = [r for r in row["trace"] if isinstance(r, dict) and r.get("stage") == "sent" and r.get("status") == "failed"]
    assert sent, f"no failed `sent` record on the trace: {[r.get('stage') for r in row['trace']]}"


def test_the_sender_post_carries_the_key_no_redirects_and_names_turn_and_contact(world):
    """Ported from `test_direct_ingress.py::test_job_posts_actions_then_n8n_copy_is_duplicate`:
    the drain's POST carries the sender key header, follows no redirect, names the turn and
    the contact, carries the actions stored on the row, and logs one success row."""
    from tests.chatbot.test_inbox_queue_order import SENDER_KEY

    contact = world.contact(covered=True)
    mid = world.message(contact, time.time() - 5, "post-shape")
    response, _ = world.chat_turn(world.body(contact, mid))
    assert_nothing_to_send(response)
    posts = world.wait_posts(1, contact, settle=1.0)
    row = world.row_for(contact, mid)
    post = posts[0]
    assert post["headers"].get(direct_ingress.SENDER_KEY_HEADER) == SENDER_KEY
    assert post["follow_redirects"] is False
    assert (post["turn_id"], post["contact_id"]) == (row["id"], contact)
    assert post["actions"] and post["actions"] == (row["response"] or {}).get("actions")
    assert _sender_logs(row["id"]) == [("success", 200)]


def test_a_webhook_message_of_a_contact_on_another_workspace_is_not_queued(world, monkeypatch):
    """Ported from `test_direct_ingress.py::test_a_contact_of_another_workspace_runs_no_turn`
    (security review L3): the sender speaks for the default workspace only, so a contact
    stored against another workspace is not queued by the webhook and gets no POST."""
    contact = world.contact(covered=True)
    real = direct_ingress._on_default_workspace
    monkeypatch.setattr(
        direct_ingress, "_on_default_workspace", lambda db, cid: False if cid == contact else real(db, cid)
    )
    mid = world.message(contact, time.time() - 5, "other-workspace")
    world.webhook(world.body(contact, mid))
    time.sleep(1.5)
    assert world.row_for(contact, mid) is None
    assert world.posts_for(contact) == []
