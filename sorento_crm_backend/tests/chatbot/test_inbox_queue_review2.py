"""CHAT-INBOX-QUEUE review round 2 (RED): IQ-38 .. IQ-46.

UAC `documentation/plans/chatbot/chat-inbox-queue-acceptance-criteria.md`, "Review round 2
additions". Written against ed0b0799dd, BEFORE the coder's round-2 fixes. The harness is the
one in `test_inbox_queue_order.py` (World, MediaWorker, injectors, recorders, the
cross-worker lock); `World.verdicts` routes a message to a lane (see review1).

Two tests reach for internals the contract does not name, and say so: IQ-39 presets the
lookup-failure counter (`chatbot:inbox:lookup-fails:{contact}`) and reads the backoff key
(`chatbot:inbox:backoff:{contact}`); IQ-41 injects the stale drain's `sending` stamp just
before recovery's requeue UPDATE (caught at the SQL layer, so it does not depend on which
function issues it).
"""
from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

import pytest
from sqlalchemy import event, text

from app.database import SessionLocal
from app.database import engine as db_engine
from app.services.chatbot import direct_ingress
from app.services.chatbot import engine as engine_mod
from app.services.media_extract import wording
from app.tasks import chat_turns
from tests.chatbot.test_inbox_queue_order import (  # noqa: F401 - fixtures used by name
    _CURRENT,
    MediaWorker,
    World,
    action_texts,
    assert_nothing_to_send,
    drain_key,
    iq,
    iq_serial,
    media_worker,
    redis_client,
    wait_until,
    world,
)
from tests.chatbot.test_inbox_queue_review1 import CASUAL

REAL_LOOKUP = direct_ingress._lookup_contact
OPEN_INDEX = "ix_chatbot_turns_inbox_open"
NORMAL_STAGES = {None, "queued", "received", "sending", "send_unconfirmed", "sent", "remembered", "replied"}


def _lookup_fails_key(contact: str) -> str:
    return f"chatbot:inbox:lookup-fails:{contact}"


def _backoff_key(contact: str) -> str:
    return f"chatbot:inbox:backoff:{contact}"


class _Lookup:
    """respond.io's contact lookup driven for real (`direct_ingress._lookup_contact`), with
    `RespondClient.for_identifier` failing while `down` and every attempt counted."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.services.integration_service import RespondClient

        self.down = True
        self.attempts = 0
        lookup = self

        def counting_lookup(db, contact_id):
            lookup.attempts += 1
            return REAL_LOOKUP(db, contact_id)

        class _Client:
            def get_contact_by_identifier(self, ident):
                return {"id": ident, "firstName": "Zzt", "custom_fields": [{"name": "is_human_intervened", "value": "false"}]}

        def for_identifier(cls, db, ident):
            if lookup.down:
                raise RuntimeError("zzt: respond.io is unreachable")
            return _Client()

        monkeypatch.setattr(direct_ingress, "_lookup_contact", counting_lookup)
        monkeypatch.setattr(RespondClient, "for_identifier", classmethod(for_identifier))


def _queue_held(world: World, contact: str, mids: list[int]) -> None:
    """Queue `mids` (via `/chat/turn`, no stale cut) while shutdown holds every drain off."""
    iq().begin_shutdown()
    for mid in mids:
        response, _ = world.chat_turn(world.body(contact, mid), bound=5.0)
        assert_nothing_to_send(response)
    assert wait_until(
        lambda: [(world.row_for(contact, m) or {}).get("status") for m in mids] == ["queued"] * len(mids),
        timeout=3,
    )


# --------------------------------------------------------------------------- #
# IQ-38: the sweep query uses the partial index
# --------------------------------------------------------------------------- #


def test_the_real_sweep_query_plans_onto_the_inbox_open_index(iq_serial):
    """IQ-38: the SQL `sweep()` actually sends, EXPLAINed with sequential scans off, runs on
    `ix_chatbot_turns_inbox_open` (its `is_test` filter must match the index predicate)."""
    module = iq()
    module._reset_for_tests()
    captured: list[tuple[str, Any]] = []

    def grab(conn, cursor, statement, parameters, context, executemany):
        if "chatbot.turns" in statement and "DISTINCT" in statement.upper() and "contact_respond_id" in statement:
            captured.append((statement, parameters))

    event.listen(db_engine, "before_cursor_execute", grab)
    try:
        module.sweep()
    finally:
        event.remove(db_engine, "before_cursor_execute", grab)
    assert captured, "could not capture the sweep's query"
    statement, params = captured[0]
    with db_engine.connect() as conn:
        with conn.begin():
            conn.exec_driver_sql("SET LOCAL enable_seqscan = off")
            plan = "\n".join(str(r[0]) for r in conn.exec_driver_sql("EXPLAIN " + statement, params))
    assert OPEN_INDEX in plan, f"the sweep does not use {OPEN_INDEX}:\n{plan}\n-- for --\n{statement}"


# --------------------------------------------------------------------------- #
# IQ-39: bounded backoff, and a lookup that never recovers is closed
# --------------------------------------------------------------------------- #


def test_a_huge_lookup_failure_count_still_backs_off_with_a_bounded_delay(world, monkeypatch):
    """IQ-39: after very many failed lookups (counter preset to 2000) one more failure does
    not overflow the delay into no backoff at all (a hot loop): the drain is not re-run at
    once, and either a bounded backoff is set or the row is already closed for staff."""
    lookup = _Lookup(monkeypatch)
    contact = world.contact(covered=True)
    world.redis.set(_lookup_fails_key(contact), 2000, ex=900)
    mid = world.message(contact, time.time() - 5, "overflow")

    response, _ = world.chat_turn(world.body(contact, mid))
    assert_nothing_to_send(response)
    time.sleep(3.0)
    assert lookup.attempts <= 2, f"{lookup.attempts} lookups in 3 s: the backoff overflowed into a hot loop"
    assert world.posts_for(contact) == []
    row = world.row_for(contact, mid)
    if row["status"] == "queued":
        ttl = world.redis.pttl(_backoff_key(contact))
        assert 0 < ttl <= 60_000, f"backoff TTL {ttl} ms: missing or unbounded"
    else:
        assert row["status"] == "failed", (row["status"], row["stage"])


def test_a_row_whose_lookup_keeps_failing_is_closed_for_staff_and_the_next_row_continues(world, monkeypatch):
    """IQ-39: a row whose takeover lookup keeps failing past the age limit (it was sent a day
    ago) is closed `failed` and flagged for staff, never POSTed; once respond.io answers
    again the contact's next row is answered."""
    lookup = _Lookup(monkeypatch)
    contact = world.contact(covered=True)
    old = world.message(contact, time.time() - 86_400, "aged-lookup")
    fresh = world.message(contact, time.time() - 5, "after-aged-lookup")
    _queue_held(world, contact, [old, fresh])
    db = SessionLocal()
    try:
        db.execute(
            text("UPDATE chatbot.turns SET created_at = now() - interval '1 day' WHERE id = CAST(:i AS uuid)"),
            {"i": world.row_for(contact, old)["id"]},
        )
        db.commit()
    finally:
        db.close()
    iq()._reset_for_tests()

    with world.sweeper(interval=0.5):
        assert wait_until(lambda: world.row_for(contact, old)["status"] == "failed", timeout=30), (
            f"an aged row whose lookup keeps failing must be closed, got {world.row_for(contact, old)['status']}"
        )
        flagged = world.row_for(contact, old)
        assert any(isinstance(r, dict) and r.get("status") == "failed" for r in flagged["trace"]), (
            "the staff flag must be on the trace"
        )
        assert world.posts_for(contact) == []
        lookup.down = False
        world.wait_posts(1, contact, timeout=70)
    assert world.posted_messages(contact) == [str(fresh)]


# --------------------------------------------------------------------------- #
# IQ-40: `/chat/turn` is rate limited; a refused copy is never silent
# --------------------------------------------------------------------------- #


def _refusal(world: World, contact: str, mid: int) -> dict[str, Any]:
    rows = [r for r in world.rows(contact) if r["message_id"] == str(mid)]
    assert len(rows) == 1, f"a refused copy leaves exactly ONE row for its message: {len(rows)}"
    row = rows[0]
    assert row["status"] == "failed", f"a refused copy must leave a failed row, got {row['status']}"
    assert row["stage"] not in NORMAL_STAGES, f"the refusal needs a stage staff can tell apart: {row['stage']}"
    return row


def test_chat_turn_over_the_per_contact_rate_limit_is_refused_and_visible(world):
    """IQ-40: `/chat/turn`'s queue branch applies the webhook's per-contact rate limit; the
    refused copy leaves one failed, staff-visible row for its message (a second copy does
    not add another) and is never POSTed."""
    contact = world.contact(covered=True)
    mid = world.message(contact, time.time() - 5, "rate-limited-turn")
    world.redis.set(direct_ingress.rate_key(contact), direct_ingress.RATE_LIMIT_PER_SECOND, ex=10)

    response, _ = world.chat_turn(world.body(contact, mid))
    assert response.status_code in (200, 429), response.text
    time.sleep(1.5)
    assert world.posts_for(contact) == [], "a rate-limited copy is not answered"
    _refusal(world, contact, mid)
    world.chat_turn(world.body(contact, mid))
    time.sleep(0.5)
    _refusal(world, contact, mid)


def test_a_copy_refused_by_the_200_row_cap_leaves_one_failed_visible_row(world):
    """IQ-40: the 201st copy (IQ-33's cap) is not silent either: one failed, staff-visible
    row for that message, however many copies of it arrive."""
    from app.services.chatbot.contracts import Envelope

    module = iq()
    contact = world.contact(covered=True)
    module.begin_shutdown()
    base = time.time() - 60
    db = SessionLocal()
    try:
        for i in range(200):
            mid = world.message(contact, base + i * 0.01, f"cap{i:03d}")
            body = world.body(contact, mid)
            module.enqueue(db, Envelope(message=body, contact=body["contact"], ingress="webhook"))
    finally:
        db.close()
    extra = world.message(contact, base + 5, "cap-201")
    world.chat_turn(world.body(contact, extra), bound=10.0)
    world.chat_turn(world.body(contact, extra), ingress="poller", bound=10.0)
    _refusal(world, contact, extra)
    assert sum(1 for r in world.rows(contact) if r["status"] == "queued") == 200


# --------------------------------------------------------------------------- #
# IQ-41: recovery is a compare-and-set; every claim-ending write is fenced
# --------------------------------------------------------------------------- #


def test_recovery_never_requeues_a_row_its_old_drain_stamped_sending_meanwhile(world):
    """IQ-41: recovery READ a dead row at a pre-POST stage, but the old drain (its mutex lost,
    still alive) stamps `sending` and POSTs before recovery's UPDATE lands. The requeue must
    not apply under it: the message is POSTed once, never twice."""
    module = iq()
    contact = world.contact(covered=True)
    mid = world.message(contact, time.time() - 10, "cas")
    _queue_held(world, contact, [mid])
    row_id = world.row_for(contact, mid)["id"]
    db = SessionLocal()
    try:
        claimed_at = db.execute(
            text(
                "UPDATE chatbot.turns SET status = 'processing', stage = 'received', started_at = clock_timestamp() "
                "WHERE id = CAST(:i AS uuid) RETURNING started_at"
            ),
            {"i": row_id},
        ).scalar()
        db.commit()
    finally:
        db.close()

    injected = threading.Event()

    def old_drain_posts_first(conn, cursor, statement, parameters, context, executemany):
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
            actions=[{"kind": "send_message", "text": "ZZT answer from the old drain", "dry_run": False}],
            reply=None,
            branch_kind=None,
        )

    world.redis.delete(drain_key(contact))
    module._reset_for_tests()
    event.listen(db_engine, "before_cursor_execute", old_drain_posts_first)
    try:
        module.sweep()
        with world.sweeper(interval=0.5):
            wait_until(lambda: len(world.posts_for(contact)) >= 2, timeout=6)
    finally:
        event.remove(db_engine, "before_cursor_execute", old_drain_posts_first)
    assert injected.is_set(), "recovery never tried to requeue the dead row (test setup)"
    assert len(world.posts_for(contact)) == 1, (
        f"{len(world.posts_for(contact))} POSTs: recovery requeued a row its old drain had stamped `sending`"
    )


def test_a_takeover_skip_writes_nothing_once_the_claim_is_lost(world, monkeypatch):
    """IQ-41: while a drain checks takeover, its claim is lost (another drain re-claimed the
    row). Its skip must write nothing: no `skipped` record on the trace, no close."""
    contact = world.contact(covered=True)
    mid = world.message(contact, time.time() - 5, "skip-fence")

    def reclaimed_then_taken_over(db, contact_id):
        side = SessionLocal()
        try:
            side.execute(
                text(
                    "UPDATE chatbot.turns SET started_at = clock_timestamp() "
                    "WHERE contact_respond_id = :c AND status = 'processing'"
                ),
                {"c": contact_id},
            )
            side.commit()
        finally:
            side.close()
        return {"id": contact_id, "custom_fields": [{"name": "is_human_intervened", "value": "true"}]}

    monkeypatch.setattr(direct_ingress, "_lookup_contact", reclaimed_then_taken_over)
    response, _ = world.chat_turn(world.body(contact, mid))
    assert_nothing_to_send(response)
    time.sleep(2.0)
    row = world.row_for(contact, mid)
    skipped = [
        r for r in row["trace"]
        if isinstance(r, dict) and (r.get("status") == "skipped" or (r.get("facts") or {}).get("skipped"))
    ]
    assert skipped == [], f"a drain that lost its claim wrote a skip record: {skipped}"
    assert row["status"] == "processing", f"a lost claim must not close the row: {row['status']}"
    assert world.posts_for(contact) == []


# --------------------------------------------------------------------------- #
# IQ-42: a key that does not decrypt is no sender
# --------------------------------------------------------------------------- #


def test_a_sender_key_that_does_not_decrypt_keeps_the_sync_path(world):
    """IQ-42: the stored sender key is corrupt (does not decrypt). Queue mode does not apply:
    `/chat/turn` answers synchronously and the webhook copy queues nothing."""
    contact = world.contact(covered=True)
    world.workspace.chatbot_sender_key_ciphertext = "zzt-not-a-valid-fernet-token"
    base = time.time() - 10
    m1 = world.message(contact, base, "bad-key-1")
    m2 = world.message(contact, base + 1, "bad-key-2")

    response, _ = world.chat_turn(world.body(contact, m1), bound=20.0)
    assert response.status_code == 200, response.text
    assert response.json()["duplicate"] is False and response.json()["actions"], (
        f"a sender key that does not decrypt must keep the sync path: {response.json()}"
    )
    world.webhook(world.body(contact, m2))
    time.sleep(1.5)
    assert world.row_for(contact, m2) is None
    assert world.posts_for(contact) == []


# --------------------------------------------------------------------------- #
# IQ-43: the shutdown budget runs from the signal
# --------------------------------------------------------------------------- #


def test_the_drain_shutdown_wait_runs_from_the_signal_not_from_lifespan_start(world, monkeypatch):
    """IQ-43: SIGTERM (its hook calls `begin_shutdown`) with no connection open, so the
    lifespan shutdown starts at once. A drain whose sender POST outlasts the old short
    lifespan wait (patched to 1 s here) but is well inside the budget from the signal still
    finishes: the handler returns only after that POST and the done mark."""
    from app import main as main_mod

    monkeypatch.setattr(chat_turns, "INBOX_SHUTDOWN_GRACE_SECONDS", 1.0)
    monkeypatch.setattr(chat_turns.stop_inbox_queue, "__defaults__", (1.0,))
    contact = world.contact(covered=True)
    mid = world.message(contact, time.time() - 5, "budget")
    world.post_delay = 3.0

    world.gate.clear()
    response, _ = world.chat_turn(world.body(contact, mid))
    assert_nothing_to_send(response)
    assert world.wait_parse_started(mid, timeout=10)
    iq().begin_shutdown()  # what the SIGTERM hook does, at t0
    world.gate.set()

    seen: dict[str, Any] = {}

    def _lifespan_shutdown() -> None:
        asyncio.run(main_mod.shutdown_event())
        seen["returned_at"] = time.monotonic()
        seen["posts"] = list(world.posts_for(contact))
        seen["status"] = (world.row_for(contact, mid) or {}).get("status")

    handler = threading.Thread(target=_lifespan_shutdown, daemon=True)
    handler.start()
    handler.join(30)
    assert not handler.is_alive(), "the shutdown handler never returned"
    assert len(seen["posts"]) == 1, "the handler returned before the running row's POST"
    assert seen["posts"][0]["t_end"] <= seen["returned_at"]
    assert seen["status"] == "done", f"the handler returned before the done mark: {seen['status']}"


# --------------------------------------------------------------------------- #
# IQ-44: a queued row whose lane delegates is closed, whatever its ingress
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("ingress", ["webhook", "poller"], ids=["spine", "inject"])
def test_a_queued_turn_whose_lane_delegates_is_closed_not_left_delegated(world, monkeypatch, ingress):
    """IQ-44 (ports the deleted `test_a_delegating_direct_turn_is_closed_not_left_delegated`):
    a `/chat/turn`-queued row whose lane still delegates (no n8n spine waits on a queued
    turn) is closed like a direct-ingress one, never left `delegated` for recovery to re-run
    and re-send: through a drain and two sweeps, at most one POST."""
    monkeypatch.setattr(engine_mod, "CRM_COMPLETED_BRANCH_KINDS", frozenset())
    contact = world.contact(covered=True)
    mid = world.message(contact, time.time() - 5, f"delegating-{ingress}")

    response, _ = world.chat_turn(world.body(contact, mid), ingress=ingress)
    assert_nothing_to_send(response)
    wait_until(lambda: (world.row_for(contact, mid) or {}).get("status") not in ("queued", "processing"), timeout=15)
    for _ in range(2):
        time.sleep(1.0)
        iq().sweep()
    time.sleep(2.0)
    assert len(world.posts_for(contact)) <= 1, f"{len(world.posts_for(contact))} POSTs for one delegating row"
    row = world.row_for(contact, mid)
    assert row["status"] == "failed", f"a delegating queued row must be closed failed, got {row['status']}/{row['stage']}"


# --------------------------------------------------------------------------- #
# IQ-45: a turn that gives way writes no profile facts
# --------------------------------------------------------------------------- #


def test_a_casual_turn_that_gives_way_writes_no_profile_fact(world, media_worker, monkeypatch):
    """IQ-45: a later casual text T stating a profile fact is mid-run when an earlier photo P
    is queued. T gives way; its abandoned run must not have saved the fact (the casual lane
    remembers statements before its first checkpoint today). The re-run saves it, once."""
    from app.services.chatbot.turn import profile_facts as profile_facts_mod

    applied: dict[str | None, int] = {}
    real_apply = profile_facts_mod.apply_statement

    def counting_apply(*args, **kwargs):
        mid_ = getattr(_CURRENT, "message_id", None)
        applied[mid_] = applied.get(mid_, 0) + 1
        return real_apply(*args, **kwargs)

    monkeypatch.setattr(profile_facts_mod, "apply_statement", counting_apply)
    contact = world.contact(covered=True, media=True)
    world.set_mode("contacts", media_burst_limit=1000)
    base = time.time() - 10
    photo = world.message(contact, base, "facts-photo")
    later = world.message(contact, base + 2, "facts-text")
    world.verdicts[str(later)] = {**CASUAL, "profile_statements": [{"key": "role", "value": "purchaser"}]}
    seen: dict[str, Any] = {}

    def facts_when_photo_runs(mid_: str, block: str) -> None:
        db = SessionLocal()
        try:
            seen["profile"] = db.execute(
                text("SELECT chatbot_profile FROM respond_contacts WHERE respond_io_id = :c"), {"c": contact}
            ).scalar()
        finally:
            db.close()

    world.parse_hooks[str(photo)] = facts_when_photo_runs
    world.gate.clear()
    world.webhook(world.body(contact, later, text_value="I am the purchaser here (facts-text)"))
    assert world.wait_parse_started(later, timeout=10)
    world.webhook(world.body(contact, photo, photo=True))
    assert wait_until(lambda: (world.row_for(contact, photo) or {}).get("status") == "queued", timeout=5)
    world.gate.set()

    world.wait_posts(2, contact, timeout=30)
    assert world.posted_messages(contact) == [str(photo), str(later)]
    facts = ((seen.get("profile") or {}).get("facts")) or []
    assert not any(f.get("key") == "role" for f in facts), (
        f"T's abandoned run saved its profile fact before giving way: {facts}"
    )
    assert applied.get(str(later), 0) == 1, f"the fact was applied {applied.get(str(later), 0)} times"


# --------------------------------------------------------------------------- #
# IQ-46: a read stalled across parked runs is read again, not answered as failed
# --------------------------------------------------------------------------- #


def test_a_read_stalled_across_parked_runs_is_read_again_not_answered_as_failed(world, media_worker, monkeypatch):
    """IQ-46: the photo's read hangs (`running`, RQ job not failed) and its row is parked
    (sync wait 1 s). While it sits parked the hang crosses every threshold (the test dates
    the job's `started_at` an hour back at the moment the row is parked), so the next run's
    idempotent replay meets `reclaim_stranded_job`, which today marks the job failed. The
    photo must be read again once and answered from that read, never with the failed-read
    reply."""
    from app.services import media_access_service

    monkeypatch.setattr(media_access_service, "SYNC_WAIT_MIN_SECONDS", 1)
    contact = world.contact(covered=True, media=True)
    world.set_mode("contacts", media_sync_wait_seconds=1, media_burst_limit=1000)
    media_worker.mode = "stall_first"
    media_worker.stall_minutes = 0
    media_worker.delay = 0.2
    photo = world.message(contact, time.time() - 5, "stalled-parked")
    aged = threading.Event()

    def age_the_hang_when_parked(conn, cursor, statement, parameters, context, executemany):
        if aged.is_set() or not media_worker.calls or not statement.lstrip().upper().startswith("UPDATE"):
            return
        row = world.row_for(contact, photo)
        values = list(parameters.values()) if isinstance(parameters, dict) else list(parameters or [])
        if row is None or "queued" not in values or not any(str(v) == row["id"] for v in values):
            return
        aged.set()
        side = SessionLocal()
        try:
            side.execute(
                text(
                    "UPDATE media_extraction_job SET started_at = now() - interval '1 hour' "
                    "WHERE id = CAST(:i AS uuid) AND status = 'running'"
                ),
                {"i": media_worker.calls[0]},
            )
            side.commit()
        finally:
            side.close()

    event.listen(db_engine, "before_cursor_execute", age_the_hang_when_parked)
    try:
        with world.sweeper(interval=0.5):
            world.webhook(world.body(contact, photo, photo=True))
            posts = world.wait_posts(1, contact, timeout=40, settle=1.5)
    finally:
        event.remove(db_engine, "before_cursor_execute", age_the_hang_when_parked)
    assert aged.is_set(), "the photo row was never parked (test setup)"
    assert len(posts) == 1, f"one photo, one POST: got {len(posts)}"
    texts = action_texts(posts[0])
    assert wording.nothing_read() not in texts, f"answered with the failed-read reply: {texts}"
    assert len(media_worker.calls) == 2, f"read once, then again once: {media_worker.calls}"
    assert [media_worker.message_of_job(j) for j in media_worker.calls] == [str(photo), str(photo)]
