"""S7 - thin spine + CRM per-contact ordering + optional worker offload (RED, tester-first).

Covers AC-701, AC-703, AC-704, AC-709, AC-710, AC-713, H12; a best-effort static check for
H6. AC-702, AC-705 and AC-712 already have tests elsewhere on this lane
(`test_chat_turn_endpoint.py::TestDryRunEndpointZeroWrites`, `test_d15_duplicate_race.py`) and
are deliberately NOT duplicated here. AC-706 to AC-708, AC-711, AC-714 are n8n/E2E and out of
scope for pytest.

**Written BEFORE `app/services/chatbot/dispatch.py` exists.** As of this commit the lane head
(4a5920f66) has no `dispatch` module - the plan's own S7 section names it
(`documentation/plans/chatbot/PLAN-chatbot-turn-engine.md` line 604: "`dispatch.py`: redis
ticket FIFO per contact inside the request") but nothing has built it yet. A `dispatch.py`
carrying `reinject_envelope` (AC-705) exists on the separate, unmerged
`feat/chatbot-turn-engine-s2b` worktree - that is a different function for a different AC and
is untouched here; do not assume it lands as part of this file going green.

**The contract this file locks in for the coder** (the plan's prose, made concrete):

* Redis keys, per contact: `chatbot:seq:{contact}` (INCR'd ticket counter, 1h TTL),
  `chatbot:done:{contact}` (last-completed ticket, absent == 0), `chatbot:running:{contact}`
  (present while a ticket is actively being worked; absent otherwise - deleted, not expired,
  so its ABSENCE is the death signal `wait_for_turn` watches for).
* `dispatch.contact_ticket(redis, contact) -> int` - `INCR chatbot:seq:{contact}`, then
  `EXPIRE` 3600s, returns the new ticket.
* `dispatch.mark_running(redis, contact, ticket) -> None` - sets `chatbot:running:{contact}`.
* `dispatch.mark_done(redis, contact, ticket) -> None` - sets `chatbot:done:{contact} = ticket`
  and clears `chatbot:running:{contact}`. Called in the engine's `finally`, so a mid-turn
  exception still releases the next waiter (AC-704).
* `dispatch.wait_for_turn(redis, contact, ticket, *, timeout_s) -> None` - polls every
  `dispatch.POLL_INTERVAL_SECONDS` (200 ms) until `chatbot:done:{contact} >= ticket - 1`.
  While waiting, if `chatbot:running:{contact}` has been ABSENT for more than
  `dispatch.STALL_GRACE_SECONDS` (2 s) - tracked by the poller itself, not stored in redis -
  it self-heals: sets `done = ticket - 1` and returns, rather than waiting out the predecessor
  that will never finish. Exceeding `timeout_s` with no repair raises `dispatch.QueueWait`.
  Both constants are module-level so a test can shrink them.
* `engine.run_turn`, at the top of the wrapped stage-runner (`stage[0]` already exists for
  exactly this reason - the generic `except Exception` in `run_turn` records whatever
  `stage[0]` says), sets `stage[0] = "queued"` and - only when
  `settings.chatbot_ordering_enabled` is `True` (default `False` until S7 promotes) - calls
  `dispatch.contact_ticket` then `dispatch.wait_for_turn(timeout_s=settings.
  chatbot_queue_wait_seconds)`. A `QueueWait` propagates out of the ordering call exactly like
  any other exception the existing handler already catches - `stage[0]` is `"queued"`, so the
  turn closes `failed`, `stage="queued"`, and the caller still gets `GENERIC_ERROR_REPLY` as a
  `send_message` action (AC-710's second half; the shape is `engine._failed_result`, already
  covered for other stages by `test_engine_failure_paths.py`). On success it calls
  `dispatch.mark_running`, sets `stage[0] = "received"`, and wraps the rest of the turn in a
  `finally: dispatch.mark_done(...)` so a later exception still releases the ticket (AC-704).
  With the flag off (default), `dispatch` is never imported or called (AC-701).
* Worker offload: `settings.chatbot_turn_on_worker` (default `False`). When `True`,
  `run_turn` enqueues via `app.services.queue_service.enqueue_job(..., queue_name="chat")`
  (imported into `engine.py` at module level, same shape as `app/api/v1/external/media.py`'s
  `enqueue_job` import) instead of running in-process, and waits up to `settings.
  chatbot_turn_wait_seconds` (default 60) for the result - this file asserts only the
  observable contract (`queue_name="chat"`, the job's result becomes the returned
  `TurnResult`), not a specific polling primitive, so the coder is free to reuse
  `app.services.queue_service.get_job_status` or poll `rq.job.Job` directly.
* `chat` joins `worker.QUEUES` (a `fast` role - it is request-latency-bound the same way
  `respond_io` and `media` are) and therefore `worker.DEFAULT_QUEUES`; extended (not
  duplicated) in `tests/test_worker_queue_defaults.py`.

Nothing here reaches an LLM, n8n or respond.io. Concurrency tests use real, committed
Postgres via `SessionLocal` and a real local Redis (`settings.redis_url` - confirmed reachable
in this environment via `redis-cli ping`), the same reasoning `test_d15_duplicate_race.py`
gives for why a single-connection rollback-scoped fixture cannot show two real threads racing.
Marker-prefixed (`ZZT-`) and cleaned up by hand in `finally`.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from typing import Any

import pydantic
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import settings
from app.database import SessionLocal
from app.models.chatbot_turn import ChatbotTurn
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.contracts import Envelope, TurnRequest
from app.services.chatbot.head import parser as parser_mod
from tests.chatbot.test_engine import (  # noqa: F401  - fixtures used by name
    CONTACT_ID,
    _envelope,
    _parser_output,
    seeded,
    stub_access,
    stub_parser,
)

REDIS_URL = settings.redis_url


def _redis_client():
    import redis

    return redis.from_url(REDIS_URL, decode_responses=True)


def _seq_key(contact: str) -> str:
    return f"chatbot:seq:{contact}"


def _done_key(contact: str) -> str:
    return f"chatbot:done:{contact}"


def _running_key(contact: str) -> str:
    return f"chatbot:running:{contact}"


def _clear_contact_keys(client, contact: str) -> None:
    client.delete(_seq_key(contact), _done_key(contact), _running_key(contact))


def _envelope_for(contact: str, message_id: str, *, ingress: str = "webhook") -> Envelope:
    return Envelope(
        contact={"id": contact, "firstName": "ZZT", "custom_fields": []},
        message={
            "event_type": "message.received",
            "contact": {"id": contact},
            "message": {
                "messageId": message_id,
                "contactId": contact,
                "channelId": "whatsapp",
                "traffic": "incoming",
                "message": {"type": "text", "text": "price for SRTWC8517"},
            },
        },
        ingress=ingress,
    )


@pytest.fixture()
def redis_client():
    client = _redis_client()
    yield client
    client.close()


@pytest.fixture()
def real_contacts(redis_client):
    """Seed N real, committed `respond_contacts` rows; clean up DB + redis in `finally`."""
    created: list[str] = []

    def _seed(suffix: str) -> str:
        contact = f"ZZT-contact-s7-{suffix}"
        db = SessionLocal()
        try:
            db.execute(
                text(
                    "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
                    "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb)) "
                    "ON CONFLICT DO NOTHING"
                ),
                {"cid": contact, "phone": f"+6000000{suffix}", "sv": json.dumps({"variables": {}})},
            )
            db.commit()
        finally:
            db.close()
        created.append(contact)
        return contact

    yield _seed

    cleanup = SessionLocal()
    try:
        for contact in created:
            cleanup.query(ChatbotTurn).filter(
                ChatbotTurn.contact_respond_id == contact
            ).delete(synchronize_session=False)
            cleanup.execute(
                text("DELETE FROM respond_contacts WHERE respond_io_id = :cid"), {"cid": contact}
            )
        cleanup.commit()
    finally:
        cleanup.close()
    for contact in created:
        _clear_contact_keys(redis_client, contact)


@pytest.fixture()
def stub_engine_seams(monkeypatch):
    """Same seam stack as `test_d15_duplicate_race.py`'s `stub_engine_seams`."""

    def fake_resolve_config(db, *, current_date):
        return parser_mod.ParserConfig(
            system_prompt="stub", prompt_version=1, provider="openai", model="gpt-test", api_key="sk-test",
        )

    monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
    monkeypatch.setattr(
        engine_mod,
        "check_access",
        lambda db, *, agent_code, contact_id, space_id: {
            "allowed": True,
            "decision": "allow",
            "agent_name": "General Enquiries",
            "attributes": None,
            "all_attributes_allowed": None,
        },
    )
    monkeypatch.setattr(engine_mod, "default_space_id", lambda db: "364817")


def _enable_ordering(monkeypatch, *, queue_wait_seconds: float = 45.0) -> None:
    """Isolates the two `AttributeError`s these tests are RED on today.

    `settings.chatbot_ordering_enabled` / `settings.chatbot_queue_wait_seconds` do not exist
    on `Settings` yet - `monkeypatch.setattr(settings, name, value, raising=False)` still goes
    through pydantic's own `__setattr__`, which rejects an undeclared field with
    `ValueError: "Settings" object has no field "..."` regardless of `raising`. That IS this
    suite's red reason for every test that calls this helper, until the coder adds both
    fields to `app.config.Settings`.
    """
    monkeypatch.setattr(settings, "chatbot_ordering_enabled", True, raising=False)
    monkeypatch.setattr(settings, "chatbot_queue_wait_seconds", queue_wait_seconds, raising=False)


class TestOrderingFlagDefaultOffBypassesTickets:
    """AC-701. Off by default, and off must mean OFF - no redis, no dispatch import cost."""

    def test_ordering_flag_default_off_bypasses_tickets(
        self, session_factory, seeded, stub_parser, stub_access, monkeypatch
    ) -> None:
        assert settings.chatbot_ordering_enabled is False, (
            "this test assumes the field defaults False once it exists; if this line itself "
            "is the failure, the field is missing entirely (also a valid red reason)"
        )

        from app.services.chatbot import dispatch  # noqa: F401 - may not exist yet (RED)

        for name in ("contact_ticket", "wait_for_turn", "mark_running", "mark_done"):
            monkeypatch.setattr(dispatch, name, lambda *a, **k: pytest.fail(
                f"dispatch.{name} was called with the ordering flag OFF"
            ))

        stub_parser()
        stub_access()
        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.status in ("delegated", "failed")  # ran to completion either way
        assert result.branch_kind == "business_query"


class TestPerContactOrdering:
    """AC-709 / H30 / H31. Same contact serialises; different contacts run in parallel."""

    def test_same_contact_runs_in_arrival_order(
        self, real_contacts, stub_engine_seams, monkeypatch
    ) -> None:
        _enable_ordering(monkeypatch)
        contact = real_contacts("order-a")

        lock = threading.Lock()
        timeline: list[tuple[str, float]] = []
        SLOW_SECONDS = 0.4

        def fake_parse(config, user_block):
            with lock:
                timeline.append(("start", time.monotonic()))
            time.sleep(SLOW_SECONDS)
            with lock:
                timeline.append(("end", time.monotonic()))
            return _parser_output()

        monkeypatch.setattr(parser_mod, "parse", fake_parse)

        results: list[Any] = [None, None]
        errors: list[BaseException | None] = [None, None]

        def _call(slot: int, message_id: str) -> None:
            try:
                results[slot] = engine_mod.run_turn(
                    _envelope_for(contact, message_id), session_factory=SessionLocal
                )
            except BaseException as exc:  # noqa: BLE001
                errors[slot] = exc

        t1 = threading.Thread(target=_call, args=(0, "ZZT-msg-order-a-1"))
        t2 = threading.Thread(target=_call, args=(1, "ZZT-msg-order-a-2"))
        t1.start()
        time.sleep(0.05)
        t2.start()
        t1.join(timeout=15)
        t2.join(timeout=15)

        assert errors == [None, None], f"unexpected exception(s): {errors}"
        assert results[0] is not None and results[1] is not None

        starts = [ts for kind, ts in timeline if kind == "start"]
        ends = [ts for kind, ts in timeline if kind == "end"]
        assert len(starts) == 2 and len(ends) == 2, timeline
        # The whole point of AC-709: the second parser call must not START until the
        # first one has ENDED. Today, with no ordering wired in, both start ~50ms apart
        # and this fails because starts[1] < ends[0].
        assert starts[1] >= ends[0], (
            f"the second turn's parser call started before the first finished: {timeline}"
        )

        client = _redis_client()
        try:
            assert client.get(_seq_key(contact)) == "2"
        finally:
            client.close()

    def test_different_contacts_run_concurrently(
        self, real_contacts, stub_engine_seams, monkeypatch
    ) -> None:
        contact_a = real_contacts("par-a")
        contact_b = real_contacts("par-b")
        _enable_ordering(monkeypatch)

        lock = threading.Lock()
        intervals: dict[str, tuple[float, float]] = {}
        SLOW_SECONDS = 0.4

        # One shared `parser_mod.parse` (it is a module-level function, not per-call), so
        # each thread tells it which contact it is via a thread-local rather than a
        # parser argument - `parse`'s signature carries no contact. Both threads write
        # disjoint dict keys under the lock, so this is race-free for what it measures.
        current_contact = threading.local()

        def shared_fake_parse(config, user_block):
            start = time.monotonic()
            time.sleep(SLOW_SECONDS)
            end = time.monotonic()
            with lock:
                intervals[current_contact.value] = (start, end)
            return _parser_output()

        monkeypatch.setattr(parser_mod, "parse", shared_fake_parse)

        def _run(contact: str) -> None:
            current_contact.value = contact
            engine_mod.run_turn(
                _envelope_for(contact, f"ZZT-msg-{contact}"), session_factory=SessionLocal
            )

        t1 = threading.Thread(target=_run, args=(contact_a,))
        t2 = threading.Thread(target=_run, args=(contact_b,))
        t1.start()
        t2.start()
        t1.join(timeout=15)
        t2.join(timeout=15)

        assert set(intervals) == {contact_a, contact_b}
        (a_start, a_end) = intervals[contact_a]
        (b_start, b_end) = intervals[contact_b]
        overlap = min(a_end, b_end) - max(a_start, b_start)
        assert overlap > 0, (
            f"two different contacts must run concurrently, got no overlap: {intervals}"
        )


class TestStalledCounterRepair:
    """AC-710 / H30 / H31."""

    def test_stalled_counter_is_repaired(self, redis_client, monkeypatch) -> None:
        from app.services.chatbot import dispatch

        monkeypatch.setattr(dispatch, "STALL_GRACE_SECONDS", 0.2, raising=False)
        monkeypatch.setattr(dispatch, "POLL_INTERVAL_SECONDS", 0.02, raising=False)

        contact = "ZZT-contact-s7-stall"
        _clear_contact_keys(redis_client, contact)
        redis_client.set(_seq_key(contact), 2)
        # Ticket 1's predecessor never marked itself running (or died and its key was
        # reaped) - `chatbot:running:{contact}` is simply absent from the start.
        assert redis_client.exists(_running_key(contact)) == 0
        redis_client.delete(_done_key(contact))

        started = time.monotonic()
        dispatch.wait_for_turn(redis_client, contact, ticket=2, timeout_s=5)
        elapsed = time.monotonic() - started

        assert elapsed >= dispatch.STALL_GRACE_SECONDS, (
            "must wait out the grace window before repairing, not repair instantly"
        )
        assert elapsed < 2.0, "must not wait anywhere near the full timeout to self-heal"
        assert redis_client.get(_done_key(contact)) == "1", (
            "the stalled predecessor's ticket must be repaired to done=ticket-1"
        )
        _clear_contact_keys(redis_client, contact)

    def test_queue_wait_timeout_is_failed_turn(
        self, real_contacts, stub_engine_seams, monkeypatch, redis_client
    ) -> None:
        _enable_ordering(monkeypatch, queue_wait_seconds=0.3)
        from app.services.chatbot import dispatch

        # Keep the stall repair from firing before the (shorter) queue-wait timeout does:
        # a running predecessor is present for the whole window, so the ONLY way out is
        # the timeout, never the repair.
        monkeypatch.setattr(dispatch, "STALL_GRACE_SECONDS", 10.0, raising=False)
        monkeypatch.setattr(dispatch, "POLL_INTERVAL_SECONDS", 0.02, raising=False)

        contact = real_contacts("queue-timeout")
        redis_client.set(_seq_key(contact), 1)  # this run's ticket becomes 2
        redis_client.set(_running_key(contact), 1)  # ticket 1 looks genuinely in progress
        redis_client.delete(_done_key(contact))  # ticket 1 never finishes

        result = engine_mod.run_turn(
            _envelope_for(contact, "ZZT-msg-queue-timeout"), session_factory=SessionLocal
        )

        assert result.status == "failed"
        assert result.stage == "queued"
        assert [a["kind"] for a in result.actions] == ["send_message"]
        assert result.actions[0]["text"] == engine_mod.GENERIC_ERROR_REPLY

        row = SessionLocal().query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).first()
        assert row is not None, "a queued-timeout must still leave a recorded row, never a 500"
        assert row.status == "failed"
        assert row.stage == "queued"


class TestFailureReleasesOrdering:
    """AC-704. A mid-turn exception must still release the ticket (`finally` semantics)."""

    def test_failure_releases_ordering(
        self, real_contacts, stub_engine_seams, stub_parser, monkeypatch
    ) -> None:
        _enable_ordering(monkeypatch)
        contact = real_contacts("fail-release")

        stub_parser()
        monkeypatch.setattr(
            engine_mod,
            "check_access",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("access service down")),
        )

        first = engine_mod.run_turn(
            _envelope_for(contact, "ZZT-msg-fail-release-1"), session_factory=SessionLocal
        )
        assert first.status == "failed"

        client = _redis_client()
        try:
            done = client.get(_done_key(contact))
            assert done == "1", (
                "ticket 1 must be marked done even though the turn failed, or every "
                f"later ticket for this contact deadlocks forever; got done={done!r}"
            )
        finally:
            client.close()

        # The next ticket for the SAME contact must proceed without waiting out the
        # whole queue-wait timeout - it only needs done to have advanced.
        started = time.monotonic()
        second = engine_mod.run_turn(
            _envelope_for(contact, "ZZT-msg-fail-release-2"), session_factory=SessionLocal
        )
        elapsed = time.monotonic() - started
        assert second.status == "failed"  # check_access is still broken
        assert elapsed < 5.0, f"second ticket waited {elapsed}s - ticket 1 was never released"


class TestWorkerOffloadFlag:
    """AC-703. `chat` queue offload, optional, default off."""

    def test_flag_off_runs_in_process_no_enqueue(
        self, session_factory, seeded, stub_parser, stub_access, monkeypatch
    ) -> None:
        assert settings.chatbot_turn_on_worker is False

        called = {"count": 0}
        monkeypatch.setattr(
            engine_mod,
            "enqueue_job",
            lambda *a, **k: called.__setitem__("count", called["count"] + 1),
            raising=False,
        )
        stub_parser()
        stub_access()

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert called["count"] == 0, "the flag is off - enqueue_job must never be called"
        assert result.branch_kind == "business_query"

    def test_flag_on_enqueues_on_chat_and_returns_the_job_result(
        self, session_factory, seeded, monkeypatch
    ) -> None:
        monkeypatch.setattr(settings, "chatbot_turn_on_worker", True, raising=False)
        monkeypatch.setattr(settings, "chatbot_turn_wait_seconds", 60, raising=False)

        canned_turn_id = str(uuid.uuid4())
        canned_result = {
            "turn_id": canned_turn_id,
            "ctx": {"contact": {"id": CONTACT_ID}, "text": {}, "session": {}, "parse": {}, "access": {}, "media": None},
            "item": {"branch_kind": "business_query", "allowed": True, "decision": "allow"},
            "branch_kind": "business_query",
            "delegate": "business_query",
            "delegate_payload": None,
            "reply": None,
            "actions": [{"kind": "send_message", "text": "hi", "quick_replies": [], "dry_run": False}],
            "session_patch": None,
            "duplicate": False,
            "status": "delegated",
            "stage": "routed",
            "error": None,
        }

        enqueue_calls: list[dict[str, Any]] = []

        class _FakeJob:
            id = "fake-job-id"

        def fake_enqueue_job(*args, **kwargs):
            enqueue_calls.append(kwargs)
            return _FakeJob()

        # `raising=False`: `engine.py` may not import `enqueue_job` at module level yet
        # (it does not exist there today - this whole test is RED on that alone until
        # the coder wires the media.py-style module-level import in).
        monkeypatch.setattr(engine_mod, "enqueue_job", fake_enqueue_job, raising=False)
        monkeypatch.setattr(
            engine_mod,
            "get_job_status",
            lambda job_id: {"status": "finished", "result": canned_result, "exc_info": None},
            raising=False,
        )

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert enqueue_calls, "chatbot_turn_on_worker=True must enqueue, not run in-process"
        assert enqueue_calls[0].get("queue_name") == "chat", (
            f"must enqueue on the 'chat' queue, got kwargs={enqueue_calls[0]!r}"
        )
        assert result.turn_id == canned_turn_id
        assert result.status == "delegated"
        assert result.actions == canned_result["actions"]


class TestPollerBatchAndLiveMessageKeepOrder:
    """AC-713 / D15. A poller batch plus one interleaved webhook message, same contact."""

    def test_poller_batch_and_live_message_keep_order(
        self, real_contacts, stub_engine_seams, monkeypatch
    ) -> None:
        _enable_ordering(monkeypatch, queue_wait_seconds=5.0)
        contact = real_contacts("batch-order")

        ingresses = ["poller", "poller", "webhook", "poller", "poller", "poller"]
        results = []
        started = time.monotonic()
        for i, ingress in enumerate(ingresses, start=1):
            result = engine_mod.run_turn(
                _envelope_for(contact, f"ZZT-msg-batch-order-{i}", ingress=ingress),
                session_factory=SessionLocal,
            )
            results.append(result)
        elapsed = time.monotonic() - started

        assert elapsed < 5.0, (
            f"six sequential same-contact turns took {elapsed}s - something is waiting "
            "on a ticket that should already be free"
        )
        assert [r.status for r in results] == ["delegated"] * 6, [r.error for r in results]

        client = _redis_client()
        try:
            assert client.get(_seq_key(contact)) == "6"
            assert client.get(_done_key(contact)) == "6"
        finally:
            client.close()

        rows = {
            row.id: row
            for row in SessionLocal()
            .query(ChatbotTurn)
            .filter(ChatbotTurn.contact_respond_id == contact)
            .all()
        }
        by_created = sorted(rows.values(), key=lambda r: r.created_at)
        assert [r.ingress for r in by_created] == ingresses, (
            f"trace rows must carry the ingress each turn actually arrived through, "
            f"got {[r.ingress for r in by_created]}"
        )


class TestEmptyOrMalformedEnvelopeIsExplicit422:
    """H12: n8n's old dispatcher treated an empty pop as silent success. The CRM's version
    of that hazard is a caller that omits the inner message entirely and gets a phantom
    'success' with nothing understood - it must be an explicit, legible 422 instead, same
    as `test_engine_failure_paths.py::TestEnvelopeValidation`'s `contact.id` case."""

    def test_a_turn_request_with_no_message_key_is_refused_at_the_schema(self) -> None:
        with pytest.raises(pydantic.ValidationError) as excinfo:
            TurnRequest(envelope={"contact": {"id": "ZZT-contact-s7-h12"}})
        errors = excinfo.value.errors()
        assert any("message" in ".".join(str(p) for p in e["loc"]) for e in errors), errors

    def test_the_endpoint_answers_422_naming_message_not_a_500(self) -> None:
        api = FastAPI()

        @api.post("/turn")
        def turn(payload: TurnRequest):  # pragma: no cover - never reached
            return {"ok": True}

        client = TestClient(api, raise_server_exceptions=False)
        response = client.post(
            "/turn", json={"envelope": {"contact": {"id": "ZZT-contact-s7-h12"}}}
        )
        assert response.status_code == 422, response.text
        assert "message" in response.text


class TestSingleTrigger:
    """H6: 'second unlocked spine entry' - fix S7 by giving the thin spine exactly ONE
    trigger. Best-effort static check: the external chat router exposes exactly one route
    that can start/advance a turn (S7 collapses `/turn` + `/complete` into `/turn` and
    deletes `delegate.py`, per the plan's S7 section). NOTE for whoever reads this red: as
    of this commit there is only ONE route already (`POST /turn`; no `/complete` route
    exists in code, only in the `ChatbotTurn` model's docstring describing the pre-S7
    design) - so this assertion is plausibly GREEN today, not RED. Kept as a named
    regression guard per the tester brief's own escape hatch ("skip if untestable, say
    so") rather than skipped outright, since it directly encodes the S7 exit condition and
    costs nothing to leave in.
    """

    def test_exactly_one_turn_creating_route_on_the_external_chat_router(self) -> None:
        from app.api.v1.external import chat as chat_router_mod

        post_routes = [
            route.path
            for route in chat_router_mod.router.routes
            if "POST" in getattr(route, "methods", set())
        ]
        assert post_routes == ["/turn"], (
            f"the thin spine must have exactly one turn-creating trigger, found {post_routes}"
        )
