"""CHAT-INBOX-QUEUE: the CRM owns each contact's message queue (RED, tester-first).

Plan `documentation/plans/chatbot/PLAN-chat-inbox-queue.md` ("Final rules", "Contract",
"Test list"), UAC `chat-inbox-queue-acceptance-criteria.md` (IQ-1 .. IQ-25). This file holds
enqueue, dedupe, per-contact and global order and the photo look-ahead (test list items
1-8, 14); `test_inbox_queue_recovery.py` holds should_resend, restart, shutdown, rollback,
failures and the photo-read waits (items 9-13, 15-17). Both import the harness below.

**Written BEFORE `app/services/chatbot/inbox_queue.py` exists.** The module is reached
through `iq()` (a lazy import) so every test fails on its own, at the assertion or the
missing function, instead of the whole file failing at collection.

What the harness fixes for the coder (the plan's seams, made concrete):

* The turn is the REAL engine (`engine.run_turn`) with its provider seams stubbed, as the
  S7 tests do: `parser.resolve_config`, `parser.parse`, `engine.check_access`,
  `engine.default_space_id`, `engine._ai_allowed`. A "running turn" is a parse call; a test
  blocks it on `World.gate` (a `threading.Event`). Which message a parse belongs to is read
  from a thread-local set by a wrapper around `engine._run_turn`, so the drain must run each
  row through `engine.run_turn` / `engine._run_turn` on the drain's own thread.
* The sender is `direct_ingress.send` for real; only `httpx.post` is replaced, and it RECORDS
  every POST (turn_id, contact_id, actions, start/end clock). `direct_ingress._default_workspace`
  returns a workspace carrying the sender URL and key; the outbound URL guard is stubbed.
* The takeover check is `direct_ingress._lookup_contact` (`is_human_intervened`), as the
  direct-ingress job does today; `World.takeover` flips it per contact.
* Injectors are the real routers mounted on a bare FastAPI app (no module guard, no
  permission lookup, no lifespan, so no app sweeper runs here): the signed respond.io webhook
  (`app/api/v1/public/respond_webhook.py`) and `/chat/turn` (`app/api/v1/external/chat.py`).
* The switch is the real `system_settings` row (`chatbot_direct_ingress_mode` =
  `contacts`, listing only this test's synthetic contact ids, so no other test's contact is
  covered). The row is created when the database has none and removed again at teardown.
* Photos run the real `media_intake.run`; only the RQ enqueue in
  `app/api/v1/external/media.py` is replaced by `MediaWorker`, which plays the worker by
  writing the `media_extraction_job` row (and a real RQ job record in Redis, never put on a
  queue, so no worker anywhere can pick it up).

Postgres via `SessionLocal` (committed rows, real concurrent connections) and the real local
Redis, like `test_s7_ordering_and_offload.py`. Contacts are synthetic (`iq-test-<hex>`); every
row and Redis key they produced is removed at teardown. Tests in BOTH files hold one Redis
lock while they run (`iq_serial`): `inbox_queue.sweep()` is global by contract, so a sweep in
one xdist worker would otherwise kick the other worker's queued contacts.
"""
from __future__ import annotations

import contextlib
import hashlib
import hmac
import importlib
import json
import logging
import random
import threading
import time
import types
import uuid
from collections import defaultdict, deque
from typing import Any, Callable, Iterator

import httpx
import pytest
import redis as redis_lib
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app as _app  # noqa: F401 - import first: app.dependencies alone is circular
from app.config import settings
from app.database import SessionLocal
from app.dependencies import get_db, get_external_api_user
from app.models.chatbot_turn import ChatbotTurn
from app.models.user import SystemSetting
from app.services import conversation_event_bus as bus
from app.services.chatbot import direct_ingress
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import parser as parser_mod
from app.tasks import chat_turns
from app.utils.field_encryption import encrypt_secret
from tests.chatbot.test_engine import _parser_output

WEBHOOK_URL = "/api/v1/public/respond/webhook"
TURN_URL = "/api/v1/external/chat/turn"
WEBHOOK_SECRET = "zzt-iq-webhook-secret-not-real-0003"  # made up; >= 24 chars
SENDER_URL = "https://automate-zzt.example.com/webhook/chatbot-sender-iq"
SENDER_KEY = "ZZT-iq-plain-sender-key-0001"
SERIAL_LOCK_KEY = "zzt:tests:inbox-queue:serial"
SESSION_WRITE_TABLE = "respond_contacts.session_vars"
PHOTO_URL = "https://media.example-zzt.com/iq/photo.jpg"


def iq():
    """The module under test. A lazy import, so a missing module fails one test, not all."""
    return importlib.import_module("app.services.chatbot.inbox_queue")


def iq_or_none():
    try:
        return iq()
    except ImportError:
        return None


def drain_key(contact: str) -> str:
    """The drain mutex key the contract names (a test deletes it to play a dead process)."""
    return f"chatbot:drain:{contact}"


def wait_until(predicate: Callable[[], Any], *, timeout: float, interval: float = 0.05) -> Any:
    """Poll `predicate` until it is truthy or `timeout` passes; returns its last value."""
    deadline = time.monotonic() + timeout
    value = predicate()
    while not value and time.monotonic() < deadline:
        time.sleep(interval)
        value = predicate()
    return value


# --------------------------------------------------------------------------- #
# respond.io bodies and n8n envelopes
# --------------------------------------------------------------------------- #


def message_id_at(epoch_seconds: float) -> int:
    """A respond.io message id IS its send time, in epoch microseconds."""
    return int(epoch_seconds * 1_000_000)


def respond_body(
    contact: str,
    message_id: int,
    *,
    text_value: str | None = None,
    photo_url: str | None = None,
    phone: str = "+60000000000",
) -> dict[str, Any]:
    """A signed respond.io `message.received` body, the shape the webhook stores and the
    n8n producer forwards verbatim as `envelope.message`."""
    if photo_url is not None:
        inner: dict[str, Any] = {
            "type": "attachment",
            "attachment": {"type": "image", "url": photo_url, "mimeType": "image/jpeg", "size": 2048},
        }
    else:
        inner = {"type": "text", "text": text_value or "price for SRTWC8517"}
    return {
        "event_type": "message.received",
        "event_id": f"evt-{message_id}",
        "contact": {"id": contact, "firstName": "Zzt", "lastName": "Queue", "phone": phone},
        "message": {
            "messageId": message_id,
            "contactId": contact,
            "channelId": 12,
            "traffic": "incoming",
            "timestamp": message_id // 1000,
            "message": inner,
            "sender": {"source": "contact"},
        },
        "channel": {"id": 12, "name": "ZZT WA", "source": "whatsapp_cloud"},
    }


# --------------------------------------------------------------------------- #
# The world one test runs in
# --------------------------------------------------------------------------- #

_CURRENT = threading.local()


class World:
    """Contacts, switch, stubs, injectors and recorders for one test."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, redis_client: Any) -> None:
        self.monkeypatch = monkeypatch
        self.redis = redis_client
        self.lock = threading.RLock()
        self.contacts: list[str] = []
        self.contact_pk: dict[str, str] = {}
        self.phone: dict[str, str] = {}
        self.covered: set[str] = set()
        self.takeover: set[str] = set()
        # message id (str) -> contact, and a label the test chose for it.
        self.contact_of: dict[str, str] = {}
        self.label_of: dict[str, str] = {}
        # Recorders.
        self.posts: list[dict[str, Any]] = []
        self.stray_posts: list[dict[str, Any]] = []
        self.events: list[tuple[str, str | None, float]] = []
        self.parse_calls: list[str | None] = []
        self.parse_started: dict[str, threading.Event] = defaultdict(threading.Event)
        self.in_flight: dict[str, int] = defaultdict(int)
        self.max_in_flight: dict[str, int] = defaultdict(int)
        self.global_in_flight = 0
        self.max_global_in_flight = 0
        # Controls.
        self.gate = threading.Event()
        self.gate.set()
        self.parse_sleep = 0.0
        self.parse_hooks: dict[str, Callable[[str, str], None]] = {}
        self.sender_script: dict[str, deque] = defaultdict(deque)
        self.post_delay = 0.03
        self._settings_snapshot: dict[str, Any] | None = None
        self._settings_created_id: str | None = None
        self._callers: list[threading.Thread] = []
        self._install_stubs()
        self.client = self._client()

    # ------------------------------------------------------------------ setup

    def _install_stubs(self) -> None:
        mp = self.monkeypatch
        mp.setattr(settings, "respond_webhook_secret", WEBHOOK_SECRET, raising=False)
        from app.services import runtime_settings

        real_get = runtime_settings.get

        def _get(name: str, db: Any = None) -> Any:
            if name == "respond_webhook_secret":
                return WEBHOOK_SECRET
            return real_get(name, db)

        mp.setattr(runtime_settings, "get", _get)

        def fake_resolve_config(db, *, current_date, override_version_id=None):
            return parser_mod.ParserConfig(
                system_prompt="stub", prompt_version=1, provider="openai", model="gpt-test", api_key="sk-test",
            )

        mp.setattr(parser_mod, "resolve_config", fake_resolve_config)
        mp.setattr(parser_mod, "parse", self._fake_parse)
        mp.setattr(
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
        mp.setattr(engine_mod, "default_space_id", lambda db: "364817")
        mp.setattr(engine_mod, "_ai_allowed", lambda session_factory, contact: True)

        real_run_turn = engine_mod._run_turn

        def wrapped_run_turn(envelope: Any, *args: Any, **kwargs: Any) -> Any:
            previous = getattr(_CURRENT, "message_id", None)
            _CURRENT.message_id = engine_mod._message_id(envelope)
            try:
                return real_run_turn(envelope, *args, **kwargs)
            finally:
                _CURRENT.message_id = previous

        mp.setattr(engine_mod, "_run_turn", wrapped_run_turn)

        workspace = types.SimpleNamespace(
            id="zzt-iq-workspace",
            chatbot_sender_url=SENDER_URL,
            chatbot_sender_key_ciphertext=encrypt_secret(SENDER_KEY),
        )
        mp.setattr(direct_ingress, "_default_workspace", lambda db: workspace)
        mp.setattr(direct_ingress, "assert_safe_outbound_url", lambda url, label: None)
        mp.setattr(direct_ingress, "_lookup_contact", self._fake_lookup)
        mp.setattr(httpx, "post", self._fake_post)
        # The stubbed parser names a product the empty test DB does not hold, so every turn's
        # lookup logs an embedding miss and a refused MCP probe. Both are handled; quietened
        # so a failure here prints the queue's story, not those.
        self._log_levels: dict[str, int] = {}
        for name in ("app.services.entity_resolver", "app.services.chatbot.lanes.business"):
            logger = logging.getLogger(name)
            self._log_levels[name] = logger.level
            logger.setLevel(logging.CRITICAL)

        class _NullTransport:
            def publish(self, channel, payload):
                pass

            def subscribe(self, channel):  # pragma: no cover
                raise NotImplementedError

        bus.set_transport(_NullTransport())

    def _client(self) -> TestClient:
        from app.api.v1.external import chat as chat_router_mod
        from app.api.v1.public import respond_webhook

        api = FastAPI()
        api.include_router(chat_router_mod.router, prefix="/api/v1/external/chat")
        api.include_router(respond_webhook.router, prefix="/api/v1/public/respond")

        def _db() -> Iterator[Any]:
            db = SessionLocal()
            try:
                yield db
            finally:
                db.close()

        api.dependency_overrides[get_db] = _db
        api.dependency_overrides[get_external_api_user] = lambda: {"id": "zzt-iq-principal"}
        return TestClient(api, raise_server_exceptions=False)

    # ------------------------------------------------------------- contacts

    def contact(self, *, covered: bool = True, media: bool = False) -> str:
        cid = f"iq-test-{uuid.uuid4().hex[:12]}"
        phone = f"+600{uuid.uuid4().int % 10**9:09d}"
        db = SessionLocal()
        try:
            pk = db.execute(
                text(
                    "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars, chatbot_allowed) "
                    "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb), true) RETURNING id"
                ),
                {"cid": cid, "phone": phone, "sv": json.dumps({"variables": {}})},
            ).scalar()
            if media:
                db.execute(
                    text(
                        "INSERT INTO contact_media_limit (id, contact_id, modality, is_allowed) "
                        "VALUES (gen_random_uuid(), :pk, 'image', true)"
                    ),
                    {"pk": pk},
                )
            db.commit()
        finally:
            db.close()
        with self.lock:
            self.contacts.append(cid)
            self.contact_pk[cid] = str(pk)
            self.phone[cid] = phone
        if covered:
            self.cover(cid)
        return cid

    def cover(self, *contacts: str) -> None:
        self.covered.update(contacts)
        self.set_mode("contacts")

    def set_mode(self, mode: str, **extra: Any) -> None:
        """Write the switch on the real settings row (created if the DB has none)."""
        db = SessionLocal()
        try:
            row = db.query(SystemSetting).first()
            if row is None:
                row = SystemSetting(id=str(uuid.uuid4()), name="ZZT IQ Co")
                db.add(row)
                db.flush()
                self._settings_created_id = str(row.id)
            elif self._settings_snapshot is None and self._settings_created_id is None:
                self._settings_snapshot = {
                    "id": str(row.id),
                    "chatbot_direct_ingress_mode": row.chatbot_direct_ingress_mode,
                    "chatbot_direct_ingress_contacts": row.chatbot_direct_ingress_contacts,
                    "media_sync_wait_seconds": row.media_sync_wait_seconds,
                    "media_burst_limit": row.media_burst_limit,
                }
            row.chatbot_direct_ingress_mode = mode
            row.chatbot_direct_ingress_contacts = "\n".join(sorted(self.covered))
            for key, value in extra.items():
                setattr(row, key, value)
            db.commit()
        finally:
            db.close()

    def session_vars(self, contact: str) -> Any:
        db = SessionLocal()
        try:
            return db.execute(
                text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :c"), {"c": contact}
            ).scalar()
        finally:
            db.close()

    # ------------------------------------------------------------- messages

    def message(self, contact: str, sent_at: float, label: str) -> int:
        """Register a message id for `contact` sent at `sent_at` (epoch s)."""
        mid = message_id_at(sent_at)
        with self.lock:
            self.contact_of[str(mid)] = contact
            self.label_of[str(mid)] = label
        return mid

    def body(self, contact: str, mid: int, *, photo: bool = False, text_value: str | None = None) -> dict:
        return respond_body(
            contact,
            mid,
            text_value=text_value or f"price for SRTWC8517 ({self.label_of.get(str(mid), 'x')})",
            photo_url=PHOTO_URL if photo else None,
            phone=self.phone.get(contact, "+60000000000"),
        )

    def webhook(self, body: dict) -> httpx.Response:
        raw = json.dumps(body).encode("utf-8")
        sig = hmac.new(WEBHOOK_SECRET.encode("utf-8"), raw, hashlib.sha256).hexdigest()
        response = self.client.post(
            WEBHOOK_URL,
            content=raw,
            headers={"x-respond-signature": sig, "content-type": "application/json"},
        )
        assert response.status_code == 200, response.text
        return response

    def chat_turn(
        self,
        body: dict,
        *,
        ingress: str = "webhook",
        is_test: bool = False,
        intervened: bool = False,
        bound: float = 5.0,
    ) -> tuple[httpx.Response, float]:
        """n8n's `/chat/turn` copy of a message: the respond.io body plus the looked-up
        contact record. Returns the response and how long the call took."""
        contact = str(body["contact"]["id"])
        envelope: dict[str, Any] = {
            "message": body,
            "contact": {
                "id": contact,
                "firstName": "Zzt",
                "custom_fields": [{"name": "is_human_intervened", "value": "true" if intervened else "false"}],
            },
            "ingress": ingress,
        }
        if is_test:
            envelope["is_test"] = True
        box: dict[str, Any] = {}

        def _call() -> None:
            started = time.monotonic()
            box["response"] = self.client.post(TURN_URL, json={"envelope": envelope})
            box["elapsed"] = time.monotonic() - started

        # Bounded: a covered `/chat/turn` must answer at once (IQ-5). A call that is still
        # inside a turn after `bound` seconds is an assertion failure here, not a hung test;
        # the thread finishes once the teardown opens the gate.
        thread = threading.Thread(target=_call, name="zzt-iq-chat-turn", daemon=True)
        self._callers.append(thread)
        thread.start()
        thread.join(bound)
        assert "response" in box, (
            f"/chat/turn did not answer within {bound}s: it is running the turn instead of "
            "queueing it (IQ-5)"
        )
        return box["response"], box["elapsed"]

    # ------------------------------------------------------------- stubs

    def _message_from_block(self, user_block: str) -> str | None:
        """Fallback when the thread-local is unset: the label in the current message."""
        first_line = (user_block or "")
        for mid, label in list(self.label_of.items()):
            if f"({label})" in first_line:
                return mid
        return None

    def _fake_parse(self, config: Any, user_block: str) -> Any:
        mid = getattr(_CURRENT, "message_id", None) or self._message_from_block(user_block)
        contact = self.contact_of.get(str(mid)) if mid else None
        now = time.monotonic()
        with self.lock:
            self.parse_calls.append(mid)
            self.events.append(("parse_start", mid, now))
            if contact is not None:
                self.in_flight[contact] += 1
                self.max_in_flight[contact] = max(self.max_in_flight[contact], self.in_flight[contact])
            self.global_in_flight += 1
            self.max_global_in_flight = max(self.max_global_in_flight, self.global_in_flight)
        if mid is not None:
            self.parse_started[str(mid)].set()
        try:
            hook = self.parse_hooks.get(str(mid)) if mid else None
            if hook is not None:
                hook(str(mid), user_block)
            if not self.gate.wait(timeout=90):
                raise RuntimeError("zzt: the test gate never opened")
            if self.parse_sleep:
                time.sleep(self.parse_sleep)
            return _parser_output()
        finally:
            with self.lock:
                if contact is not None:
                    self.in_flight[contact] -= 1
                self.global_in_flight -= 1
                self.events.append(("parse_end", mid, time.monotonic()))

    def _fake_lookup(self, db: Any, contact_id: str) -> dict[str, Any]:
        value = "true" if contact_id in self.takeover else "false"
        return {
            "id": contact_id,
            "firstName": "Zzt",
            "custom_fields": [{"name": "is_human_intervened", "value": value}],
        }

    def _fake_post(self, url: str, **kwargs: Any) -> httpx.Response:
        body = kwargs.get("json") or {}
        record = {
            "url": url,
            "turn_id": str(body.get("turn_id")),
            "contact_id": str(body.get("contact_id")),
            "actions": list(body.get("actions") or []),
            "t_start": time.monotonic(),
        }
        if url != SENDER_URL:
            with self.lock:
                self.stray_posts.append(record)
            raise RuntimeError(f"zzt: unexpected outbound POST to {url}")
        with self.lock:
            script = self.sender_script.get(record["contact_id"])
            behaviour = script.popleft() if script else "ok"
            self.events.append(("post_start", record["turn_id"], record["t_start"]))
        time.sleep(self.post_delay)
        record["t_end"] = time.monotonic()
        record["behaviour"] = behaviour
        with self.lock:
            self.posts.append(record)
            self.events.append(("post_end", record["turn_id"], record["t_end"]))
        if behaviour == "refused":
            raise httpx.ConnectError("[Errno 61] Connection refused (zzt)")
        if behaviour == "timeout":
            raise httpx.ReadTimeout("timed out (zzt)")
        status_code = behaviour if isinstance(behaviour, int) else 200
        return httpx.Response(status_code, text="ok", request=httpx.Request("POST", url))

    # ------------------------------------------------------------- readers

    def posts_for(self, *contacts: str) -> list[dict[str, Any]]:
        wanted = set(contacts) if contacts else set(self.contacts)
        with self.lock:
            return [p for p in self.posts if p["contact_id"] in wanted]

    def wait_posts(self, n: int, *contacts: str, timeout: float = 20.0, settle: float = 0.8) -> list[dict]:
        """Wait for at least `n` POSTs for `contacts`, then a little longer, so a second
        (double) answer has the chance to show up before the test counts."""
        wait_until(lambda: len(self.posts_for(*contacts)) >= n, timeout=timeout)
        if settle:
            time.sleep(settle)
        return self.posts_for(*contacts)

    def rows(self, contact: str) -> list[dict[str, Any]]:
        db = SessionLocal()
        try:
            found = (
                db.query(ChatbotTurn)
                .filter(ChatbotTurn.contact_respond_id == contact)
                .order_by(ChatbotTurn.created_at, ChatbotTurn.attempt)
                .all()
            )
            return [
                {
                    "id": str(r.id),
                    "message_id": r.message_id,
                    "status": r.status,
                    "stage": r.stage,
                    "attempt": r.attempt,
                    "ingress": r.ingress,
                    "is_test": r.is_test,
                    "started_at": r.started_at,
                    "trace": r.trace or [],
                    "response": r.response,
                    "error": r.error,
                }
                for r in found
            ]
        finally:
            db.close()

    def row_for(self, contact: str, mid: int, *, attempt: int | None = None) -> dict[str, Any] | None:
        matches = [r for r in self.rows(contact) if r["message_id"] == str(mid)]
        if attempt is not None:
            matches = [r for r in matches if r["attempt"] == attempt]
        return matches[-1] if matches else None

    def message_of_turn(self, turn_id: str) -> str | None:
        db = SessionLocal()
        try:
            return db.execute(
                text("SELECT message_id FROM chatbot.turns WHERE id = CAST(:t AS uuid)"), {"t": turn_id}
            ).scalar()
        finally:
            db.close()

    def posted_messages(self, *contacts: str) -> list[str | None]:
        """The respond message id behind each recorded POST, in POST order."""
        return [self.message_of_turn(p["turn_id"]) for p in self.posts_for(*contacts)]

    def session_writes(self, turn_id: str) -> int:
        db = SessionLocal()
        try:
            return int(
                db.execute(
                    text(
                        "SELECT count(*) FROM integration_log "
                        "WHERE business_table = :t AND business_id = :b"
                    ),
                    {"t": SESSION_WRITE_TABLE, "b": turn_id},
                ).scalar()
                or 0
            )
        finally:
            db.close()

    def wait_parse_started(self, mid: int, timeout: float = 20.0) -> bool:
        return self.parse_started[str(mid)].wait(timeout)

    @contextlib.contextmanager
    def sweeper(self, interval: float = 1.0) -> Iterator[None]:
        """Play the process's own sweeper (contract: at start-up and at least every 2 s);
        the bare test app runs no lifespan, so nothing else sweeps here."""
        stop = threading.Event()

        def _loop() -> None:
            while not stop.is_set():
                try:
                    iq().sweep()
                except Exception:  # noqa: BLE001 - a red module must not kill the loop silently
                    pass
                stop.wait(interval)

        thread = threading.Thread(target=_loop, name="zzt-iq-sweeper", daemon=True)
        thread.start()
        try:
            yield
        finally:
            stop.set()
            thread.join(timeout=10)

    # ------------------------------------------------------------- teardown

    def close(self) -> None:
        self.gate.set()
        module = iq_or_none()
        if module is not None:
            with contextlib.suppress(Exception):
                module.begin_shutdown()
            with contextlib.suppress(Exception):
                module.wait_idle(20)
        # Anything still on the direct-turn pool (a drain, or today's direct-ingress job on
        # a red run) and any `/chat/turn` call still inside a turn finishes before its rows
        # are removed.
        wait_until(lambda: chat_turns._in_flight == 0, timeout=30)
        for caller in self._callers:
            caller.join(30)
        for name, level in self._log_levels.items():
            logging.getLogger(name).setLevel(level)
        bus.set_transport(None)
        db = SessionLocal()
        try:
            for cid in self.contacts:
                pk = self.contact_pk.get(cid)
                db.execute(text("DELETE FROM chatbot.turns WHERE contact_respond_id = :c"), {"c": cid})
                db.execute(text("DELETE FROM integration_log WHERE external_reference = :c"), {"c": cid})
                db.execute(text("DELETE FROM chat_histories WHERE contact_id = :c"), {"c": cid})
                if pk:
                    db.execute(
                        text(
                            "DELETE FROM media_extraction_job WHERE usage_id IN "
                            "(SELECT id FROM contact_media_usage WHERE contact_id = :pk)"
                        ),
                        {"pk": pk},
                    )
                    db.execute(text("DELETE FROM contact_media_usage WHERE contact_id = :pk"), {"pk": pk})
                    db.execute(text("DELETE FROM contact_media_limit WHERE contact_id = :pk"), {"pk": pk})
                db.execute(text("DELETE FROM respond_contacts WHERE respond_io_id = :c"), {"c": cid})
            if self._settings_created_id is not None:
                db.execute(text("DELETE FROM system_settings WHERE id = :i"), {"i": self._settings_created_id})
            elif self._settings_snapshot is not None:
                snap = dict(self._settings_snapshot)
                row = db.query(SystemSetting).filter(SystemSetting.id == snap.pop("id")).first()
                if row is not None:
                    for key, value in snap.items():
                        setattr(row, key, value)
            db.commit()
        finally:
            db.close()
        for cid in self.contacts:
            for key in list(self.redis.scan_iter(f"*{cid}*")):
                self.redis.delete(key)
        if module is not None:
            with contextlib.suppress(Exception):
                module._reset_for_tests()


@pytest.fixture()
def redis_client() -> Iterator[Any]:
    client = redis_lib.from_url(settings.redis_url, decode_responses=True)
    yield client
    client.close()


@pytest.fixture()
def iq_serial(redis_client) -> Iterator[None]:
    """One inbox-queue test at a time across xdist workers (see the module docstring)."""
    lock = redis_client.lock(SERIAL_LOCK_KEY, timeout=900, blocking_timeout=900)
    assert lock.acquire(), "could not take the inbox-queue test lock"
    try:
        yield
    finally:
        with contextlib.suppress(Exception):
            lock.release()


@pytest.fixture()
def world(iq_serial, monkeypatch, redis_client) -> Iterator[World]:
    w = World(monkeypatch, redis_client)
    try:
        yield w
    finally:
        w.close()


class MediaWorker:
    """Plays the RQ `media` worker for photo turns, at the enqueue seam of
    `app/api/v1/external/media.py` (`enqueue_job`). Every read the CRM asks for is recorded;
    `mode` decides what the "worker" does with it:

    * `complete`: the job row turns `completed` with a read result after `delay` seconds.
    * `manual`: nothing happens until the test calls `complete(job_id)` (worker down).
    * `abandon_first`: the FIRST read is abandoned the way a killed work-horse leaves it
      (the job row stays `running`, the RQ job ends `failed` with no result); every later
      read completes.
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch, *, mode: str = "complete", delay: float = 0.2) -> None:
        import app.api.v1.external.media as media_route
        from app.services import queue_service

        self.mode = mode
        self.delay = delay
        self.calls: list[str] = []
        self.lock = threading.Lock()
        self._timers: list[threading.Timer] = []
        monkeypatch.setattr(media_route, "enqueue_job", self._fake_enqueue)
        monkeypatch.setattr(queue_service, "enqueue_job", self._fake_enqueue)

    def _rq_job(self, job_id: str) -> Any:
        from rq.job import Job

        from app.services.queue_service import redis_conn

        job = Job.create(
            "app.tasks.media_tasks.process_media_extraction",
            args=(job_id,),
            id=job_id,
            connection=redis_conn,
        )
        job.save()
        return job

    def _fake_enqueue(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        job_id = str(kwargs.get("job_id") or (args[0] if args else uuid.uuid4()))
        with self.lock:
            self.calls.append(job_id)
            nth = len(self.calls)
        job = self._rq_job(job_id)
        if self.mode == "complete" or (self.mode == "abandon_first" and nth > 1):
            self._later(self.delay, self.complete, job_id)
        elif self.mode == "abandon_first":
            self._later(self.delay, self.abandon, job_id)
        return job

    def _later(self, delay: float, fn: Callable[..., None], *args: Any) -> None:
        timer = threading.Timer(delay, fn, args)
        timer.daemon = True
        self._timers.append(timer)
        timer.start()

    def complete(self, job_id: str, rendered_text: str = "SRTWC8517") -> None:
        from rq.job import Job, JobStatus

        from app.services.queue_service import redis_conn

        db = SessionLocal()
        try:
            db.execute(
                text(
                    "UPDATE media_extraction_job SET status = 'completed', error = NULL, "
                    "result = CAST(:r AS jsonb) WHERE id = CAST(:i AS uuid)"
                ),
                {
                    "i": job_id,
                    "r": json.dumps(
                        {"rendered_text": rendered_text, "entities": [{"raw": "SRTWC8517"}], "caption": None}
                    ),
                },
            )
            db.commit()
        finally:
            db.close()
        with contextlib.suppress(Exception):
            Job.fetch(job_id, connection=redis_conn).set_status(JobStatus.FINISHED)

    def abandon(self, job_id: str) -> None:
        from rq.job import Job, JobStatus

        from app.services.queue_service import redis_conn

        db = SessionLocal()
        try:
            db.execute(
                text(
                    "UPDATE media_extraction_job SET status = 'running', started_at = now() "
                    "WHERE id = CAST(:i AS uuid) AND status = 'queued'"
                ),
                {"i": job_id},
            )
            db.commit()
        finally:
            db.close()
        job = Job.fetch(job_id, connection=redis_conn)
        job.set_status(JobStatus.FAILED)

    def job_status(self, job_id: str) -> str | None:
        db = SessionLocal()
        try:
            return db.execute(
                text("SELECT status FROM media_extraction_job WHERE id = CAST(:i AS uuid)"), {"i": job_id}
            ).scalar()
        finally:
            db.close()

    def close(self) -> None:
        from app.services.queue_service import redis_conn

        for timer in self._timers:
            timer.cancel()
        for job_id in self.calls:
            with contextlib.suppress(Exception):
                redis_conn.delete(f"rq:job:{job_id}")


@pytest.fixture()
def media_worker(world, monkeypatch) -> Iterator[MediaWorker]:
    worker = MediaWorker(monkeypatch)
    try:
        yield worker
    finally:
        worker.close()


def action_texts(post: dict[str, Any]) -> list[str]:
    return [str(a.get("text") or "") for a in post.get("actions") or [] if isinstance(a, dict)]




def assert_nothing_to_send(response: httpx.Response) -> None:
    """IQ-5: the shape the spine's `head-arm` already treats as nothing to send."""
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["duplicate"] is True, f"a covered /chat/turn must answer duplicate: true, got {body}"
    assert body["actions"] == [], f"a covered /chat/turn must carry no actions, got {body['actions']}"
    assert body.get("delegate") is None


def assert_settled(world: World, contact: str) -> None:
    """Nothing of this contact is left waiting or half-run."""
    left = [(r["message_id"], r["status"], r["stage"]) for r in world.rows(contact) if r["status"] in ("queued", "processing")]
    assert left == [], f"rows left unanswered: {left}"


def send_order(world: World, mids: list[int]) -> list[str]:
    return [str(m) for m in sorted(mids)]


# --------------------------------------------------------------------------- #
# Switch (IQ-1, IQ-2, IQ-3)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("mode", "listed", "contact", "expected"),
    [
        ("off", "", "iq-test-a", False),
        ("off", "iq-test-a", "iq-test-a", False),
        ("contacts", "iq-test-a\niq-test-b", "iq-test-a", True),
        ("contacts", "iq-test-a, iq-test-b", "iq-test-c", False),
        ("contacts", "", "iq-test-a", False),
        ("all", "", "iq-test-anyone", True),
    ],
)
def test_queue_mode_for_reads_the_existing_direct_ingress_switch(mode, listed, contact, expected):
    """IQ-2: the switch is `chatbot_direct_ingress_mode` (+ its contact list), nothing new."""
    from tests._pg_fixture import blank_session

    with blank_session() as db:
        db.add(SystemSetting(
            id=str(uuid.uuid4()), name="ZZT IQ Co",
            chatbot_direct_ingress_mode=mode, chatbot_direct_ingress_contacts=listed,
        ))
        db.commit()
        assert iq().queue_mode_for(db, contact) is expected


def test_queue_mode_for_with_no_settings_row_is_off():
    from tests._pg_fixture import blank_session

    with blank_session() as db:
        assert iq().queue_mode_for(db, "iq-test-a") is False


def test_mode_off_chat_turn_answers_synchronously_and_queues_nothing(world):
    """(f) IQ-1: off is today, exactly. `/chat/turn` runs the turn and returns its actions;
    the webhook starts no turn; the sender gets nothing."""
    contact = world.contact(covered=False)
    world.set_mode("off")
    base = time.time() - 20
    m1 = world.message(contact, base, "off1")
    m2 = world.message(contact, base + 1, "off2")

    response, _ = world.chat_turn(world.body(contact, m1))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["duplicate"] is False
    assert body["actions"], "mode off: /chat/turn returns the finished turn's actions to n8n"
    row = world.row_for(contact, m1)
    assert row is not None and row["status"] == "done", row

    world.webhook(world.body(contact, m2))
    time.sleep(1.5)
    assert world.row_for(contact, m2) is None, "mode off: the webhook starts no turn"
    assert [r for r in world.rows(contact) if r["status"] == "queued"] == []
    assert world.posts_for(contact) == [], "mode off: nothing is POSTed to the sender"

    db = SessionLocal()
    try:
        assert iq().queue_mode_for(db, contact) is False
    finally:
        db.close()


def test_contacts_mode_queues_only_listed_contacts(world):
    """IQ-2: a listed contact is queued (answered by the sender), an unlisted one keeps the
    sync path."""
    listed = world.contact(covered=True)
    unlisted = world.contact(covered=False)
    base = time.time() - 20
    a1 = world.message(listed, base, "listed1")
    b1 = world.message(unlisted, base, "unlisted1")

    queued, _ = world.chat_turn(world.body(listed, a1))
    assert_nothing_to_send(queued)
    sync, _ = world.chat_turn(world.body(unlisted, b1))
    assert sync.status_code == 200, sync.text
    assert sync.json()["duplicate"] is False and sync.json()["actions"], sync.json()

    posts = world.wait_posts(1, listed)
    assert [world.message_of_turn(p["turn_id"]) for p in posts] == [str(a1)]
    assert world.posts_for(unlisted) == [], "an unlisted contact is never sent through the sender"
    assert_settled(world, listed)


@pytest.mark.parametrize("ingress", ["webhook", "console"])
def test_is_test_turns_are_never_queued(world, ingress):
    """IQ-3: a test or console turn of a COVERED contact stays synchronous."""
    contact = world.contact(covered=True)
    mid = world.message(contact, time.time() - 5, f"test-{ingress}")

    response, _ = world.chat_turn(world.body(contact, mid), ingress=ingress, is_test=True)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["is_test"] is True
    assert body["duplicate"] is False
    assert body["actions"], "a test turn answers synchronously with its (dry-run) actions"
    time.sleep(1.5)
    assert world.posts_for(contact) == []
    rows = world.rows(contact)
    assert [(r["is_test"], r["status"]) for r in rows] == [(True, "done")], rows
    db = SessionLocal()
    try:
        assert iq().queue_mode_for(db, contact) is True, "the contact IS covered; is_test alone keeps it sync"
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Enqueue once, answer at once (IQ-4, IQ-5, IQ-6, IQ-7, IQ-22)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "order",
    [
        ("webhook", "n8n", "inject", "retry"),
        ("inject", "retry", "n8n", "webhook"),
        ("n8n", "webhook", "retry", "inject"),
    ],
    ids=["webhook-first", "inject-first", "n8n-first"],
)
def test_same_message_from_every_injector_makes_one_row_and_one_post(world, order):
    """(d) IQ-4: webhook, n8n spine (`/chat/turn`), INJECT (`/chat/turn` again) and a Retry
    copy of ONE message, in mixed order, two of them while its turn is running: one row,
    one sender POST, and every `/chat/turn` copy answered with nothing to send."""
    contact = world.contact(covered=True)
    mid = world.message(contact, time.time() - 5, "dup")
    body = world.body(contact, mid)
    ingress_of = {"n8n": "webhook", "inject": "poller", "retry": "retry"}

    def deliver(copy: str) -> None:
        if copy == "webhook":
            world.webhook(body)
        else:
            response, _ = world.chat_turn(body, ingress=ingress_of[copy])
            assert_nothing_to_send(response)

    world.gate.clear()
    deliver(order[0])
    assert world.wait_parse_started(mid, timeout=10), "the first copy never started a turn"
    deliver(order[1])
    world.gate.set()
    wait_until(lambda: (world.row_for(contact, mid) or {}).get("status") == "done", timeout=20)
    deliver(order[2])
    deliver(order[3])

    posts = world.wait_posts(1, contact, settle=1.5)
    assert len(posts) == 1, f"one message, one POST: got {len(posts)}"
    assert [r["message_id"] for r in world.rows(contact)] == [str(mid)], world.rows(contact)
    assert world.row_for(contact, mid)["status"] == "done"
    db = SessionLocal()
    try:
        assert iq().queue_mode_for(db, contact) is True
    finally:
        db.close()


def test_covered_chat_turn_answers_within_one_second_while_the_turn_runs(world):
    """IQ-5: `/chat/turn` never waits for a turn: neither for the running copy of its own
    message nor for a new message queued behind it."""
    contact = world.contact(covered=True)
    base = time.time() - 10
    m1 = world.message(contact, base, "fast1")
    m2 = world.message(contact, base + 1, "fast2")

    world.gate.clear()
    world.webhook(world.body(contact, m1))
    assert world.wait_parse_started(m1, timeout=10), "the webhook copy never started a turn"

    copy, elapsed = world.chat_turn(world.body(contact, m1), bound=3.0)
    assert_nothing_to_send(copy)
    assert elapsed < 1.0, f"/chat/turn for a running message took {elapsed:.2f}s"

    fresh, elapsed = world.chat_turn(world.body(contact, m2), bound=3.0)
    assert_nothing_to_send(fresh)
    assert elapsed < 1.0, f"/chat/turn for a new message behind a running turn took {elapsed:.2f}s"
    assert world.row_for(contact, m2)["status"] == "queued"

    world.gate.set()
    world.wait_posts(2, contact)
    assert world.posted_messages(contact) == [str(m1), str(m2)]


def test_photo_from_the_webhook_is_queued_and_read_in_its_own_turn(world, media_worker):
    """IQ-6: direct ingress's text-only skip does not apply in queue mode; the photo is read
    inside its own turn on the drain and answered once."""
    contact = world.contact(covered=True, media=True)
    mid = world.message(contact, time.time() - 5, "photo")

    world.webhook(world.body(contact, mid, photo=True))
    assert wait_until(lambda: world.row_for(contact, mid), timeout=3), (
        "a covered photo must be queued by the webhook (no `not_text` skip in queue mode)"
    )
    posts = world.wait_posts(1, contact)
    assert [world.message_of_turn(p["turn_id"]) for p in posts] == [str(mid)]
    assert len(media_worker.calls) == 1, f"one read for one photo, got {media_worker.calls}"
    row = world.row_for(contact, mid)
    assert row["status"] == "done", row
    assert any(r.get("stage") == "media_intake" for r in row["trace"]), "the read ran inside the turn"


@pytest.mark.parametrize(
    "gate", ["bad_signature", "unsigned", "outgoing", "not_whatsapp", "staff", "stale", "rate_limited"]
)
def test_webhook_gates_still_apply_and_another_injector_can_queue_it(world, gate):
    """IQ-7: the webhook's own gates still refuse its copy in queue mode; the n8n copy of a
    message the webhook skipped is still queued and answered once."""
    contact = world.contact(covered=True)
    sent = time.time() - (121 if gate == "stale" else 5)
    mid = world.message(contact, sent, f"gate-{gate}")
    body = world.body(contact, mid)

    if gate == "bad_signature":
        raw = json.dumps(body).encode("utf-8")
        sig = hmac.new(b"zzt-not-the-configured-key-xxxxxx", raw, hashlib.sha256).hexdigest()
        response = world.client.post(
            WEBHOOK_URL, content=raw, headers={"x-respond-signature": sig, "content-type": "application/json"}
        )
        assert response.status_code == 401
    elif gate == "unsigned":
        response = world.client.post(
            WEBHOOK_URL,
            content=json.dumps(body).encode("utf-8"),
            headers={"x-respond-webhook-secret": WEBHOOK_SECRET, "content-type": "application/json"},
        )
        assert response.status_code == 200, response.text
    else:
        if gate == "outgoing":
            body["event_type"] = "message.sent"
            body["message"]["traffic"] = "outgoing"
            body["message"]["sender"] = {"source": "api"}
        elif gate == "not_whatsapp":
            body["channel"] = {"id": 13, "name": "FB", "source": "facebook"}
        elif gate == "staff":
            body["message"]["sender"] = {"source": "user", "userId": 5}
        elif gate == "rate_limited":
            world.redis.set(direct_ingress.rate_key(contact), direct_ingress.RATE_LIMIT_PER_SECOND, ex=5)
        world.webhook(body)

    time.sleep(1.0)
    assert world.row_for(contact, mid) is None, f"the webhook's `{gate}` gate must still refuse its copy"
    assert world.posts_for(contact) == []

    if gate in ("unsigned", "rate_limited"):
        world.redis.delete(direct_ingress.rate_key(contact))
        response, _ = world.chat_turn(world.body(contact, mid))
        assert_nothing_to_send(response)
        posts = world.wait_posts(1, contact)
        assert [world.message_of_turn(p["turn_id"]) for p in posts] == [str(mid)]
    else:
        db = SessionLocal()
        try:
            assert iq().queue_mode_for(db, contact) is True
        finally:
            db.close()


# --------------------------------------------------------------------------- #
# Order per contact (IQ-8, IQ-9, IQ-10, IQ-11, IQ-14)
# --------------------------------------------------------------------------- #


def test_burst_of_12_shuffled_from_one_contact_posts_12_in_send_order_one_at_a_time(world):
    """(a) IQ-8, IQ-9, IQ-10: 12 messages of one contact reach the webhook in shuffled order
    while the first of them is mid-turn. The sender gets 12 POSTs, one per message, in SEND
    order; no two turns of the contact ever run at once; each row starts only after the
    previous row's POST returned."""
    contact = world.contact(covered=True)
    base = time.time() - 30
    mids = [world.message(contact, base + 0.1 * i, f"b12-{i:02d}") for i in range(12)]
    arrival = list(mids)
    random.Random(20261025).shuffle(arrival)
    if arrival[0] == mids[0]:
        arrival.append(arrival.pop(0))  # the first to arrive is never the earliest sent

    world.gate.clear()
    for mid in arrival:
        world.webhook(world.body(contact, mid))
    assert wait_until(lambda: len(world.rows(contact)) >= 12, timeout=3), (
        f"the webhook must queue every covered message: {len(world.rows(contact))} rows for 12"
    )
    world.gate.set()

    posts = world.wait_posts(12, contact, timeout=60)
    posted = [world.message_of_turn(p["turn_id"]) for p in posts]
    assert posted == send_order(world, mids), f"POSTs out of send order or missing: {posted}"
    assert len(set(posted)) == 12, "each message answered exactly once"
    assert world.max_in_flight[contact] == 1, (
        f"two turns of one contact ran at once (max {world.max_in_flight[contact]})"
    )

    # IQ-10: row k+1's (last) run starts only after row k's POST has returned.
    with world.lock:
        events = list(world.events)
    turn_of = {world.message_of_turn(p["turn_id"]): p for p in posts}
    for earlier, later in zip(send_order(world, mids), send_order(world, mids)[1:]):
        later_starts = [t for kind, m, t in events if kind == "parse_start" and m == later]
        assert later_starts, f"no turn ran for {world.label_of[later]}"
        assert turn_of[earlier]["t_end"] <= later_starts[-1], (
            f"{world.label_of[later]} started before {world.label_of[earlier]}'s POST returned"
        )
    assert_settled(world, contact)


def test_global_burst_40_contacts_x3_posts_120_once_each_in_order_within_the_pool(world):
    """(b) IQ-12: 40 contacts x 3 messages arrive at once through `/chat/turn`, each
    contact's three shuffled. All 120 are answered exactly once, each contact in send order;
    turns running at once never exceed the direct-turn pool; a row that cannot start yet
    stays queued until the sweeper re-arms it (never dropped, never left to n8n)."""
    contacts = [world.contact(covered=False) for _ in range(40)]
    world.cover(*contacts)
    world.parse_sleep = 0.05
    base = time.time() - 30
    planned: dict[str, list[int]] = {}
    for ci, contact in enumerate(contacts):
        planned[contact] = [world.message(contact, base + ci * 0.01 + mi * 0.5, f"g{ci:02d}-{mi}") for mi in range(3)]

    rng = random.Random(1025)
    arrivals: list[tuple[str, int]] = []
    for contact in contacts:
        mine = list(planned[contact])
        rng.shuffle(mine)
        arrivals.extend((contact, mid) for mid in mine)

    world.gate.clear()
    for contact, mid in arrivals:
        response, _ = world.chat_turn(world.body(contact, mid), bound=3.0)
        assert_nothing_to_send(response)
    world.gate.set()

    with world.sweeper(interval=1.0):
        world.wait_posts(120, *contacts, timeout=120, settle=1.0)

    posts = world.posts_for(*contacts)
    assert len(posts) == 120, f"120 messages, got {len(posts)} POSTs"
    by_contact: dict[str, list[str | None]] = defaultdict(list)
    for post in posts:
        by_contact[post["contact_id"]].append(world.message_of_turn(post["turn_id"]))
    for contact in contacts:
        assert by_contact[contact] == send_order(world, planned[contact]), (
            f"{contact}: answered {by_contact[contact]}, sent {send_order(world, planned[contact])}"
        )
    assert world.max_global_in_flight <= chat_turns.DIRECT_TURN_THREADS, (
        f"{world.max_global_in_flight} turns ran at once; the pool is {chat_turns.DIRECT_TURN_THREADS}"
    )
    for contact in contacts:
        assert world.max_in_flight[contact] <= 1
        assert_settled(world, contact)


def test_late_earlier_sent_photo_is_answered_before_the_running_text(world, media_worker):
    """(c) IQ-13: text T (sent second) is mid-turn when photo P (sent first) is queued. T's
    run is abandoned before it writes any conversation state or posts; P is answered; T
    runs again and sees what P left. The sender gets P's POST, then T's, each once."""
    contact = world.contact(covered=True, media=True)
    base = time.time() - 10
    photo = world.message(contact, base, "late-photo")
    text_mid = world.message(contact, base + 2, "late-text")
    initial_state = world.session_vars(contact)
    seen: dict[str, Any] = {}

    def at_photo_parse(mid: str, block: str) -> None:
        seen.setdefault("state_when_photo_ran", world.session_vars(contact))

    def at_text_parse(mid: str, block: str) -> None:
        seen.setdefault("text_runs", []).append(world.session_vars(contact))

    world.parse_hooks[str(photo)] = at_photo_parse
    world.parse_hooks[str(text_mid)] = at_text_parse

    world.gate.clear()
    world.webhook(world.body(contact, text_mid, text_value="check stock (late-text)"))
    assert world.wait_parse_started(text_mid, timeout=10), "T never started"
    world.webhook(world.body(contact, photo, photo=True))
    assert wait_until(
        lambda: (world.row_for(contact, photo) or {}).get("status") == "queued", timeout=5
    ), "P must be queued while T runs"
    world.gate.set()

    posts = world.wait_posts(2, contact, timeout=30)
    t_row = world.row_for(contact, text_mid)
    p_row = world.row_for(contact, photo)
    assert [p["turn_id"] for p in posts] == [p_row["id"], t_row["id"]], (
        f"expected P's POST then T's, got {world.posted_messages(contact)}"
    )
    calls = [m for m in world.parse_calls if m in (str(photo), str(text_mid))]
    assert calls == [str(text_mid), str(photo), str(text_mid)], f"T must run, yield to P, then run again: {calls}"
    assert seen["state_when_photo_ran"] == initial_state, (
        "T's abandoned first run wrote conversation state before P ran"
    )
    assert world.session_writes(t_row["id"]) == 1, "T writes state once, on its second run only"
    assert world.session_writes(p_row["id"]) == 1
    assert len(seen["text_runs"]) == 2 and seen["text_runs"][1] != initial_state, (
        "T's second run must start after P's state was written (it sees what P left)"
    )
    assert p_row["status"] == "done" and t_row["status"] == "done"


def test_nothing_earlier_queued_posts_at_once(world):
    """IQ-14: with nothing earlier queued, a finished turn posts with no added wait."""
    contact = world.contact(covered=True)
    mid = world.message(contact, time.time() - 5, "at-once")
    response, _ = world.chat_turn(world.body(contact, mid))
    assert_nothing_to_send(response)
    posts = world.wait_posts(1, contact, settle=0)
    assert posts, "the message was never answered"
    with world.lock:
        parse_end = max(t for kind, m, t in world.events if kind == "parse_end" and m == str(mid))
    gap = posts[0]["t_start"] - parse_end
    assert gap < 1.5, f"{gap:.2f}s between the turn's parse and its POST: something waited"


def test_takeover_at_drain_time_posts_nothing(world):
    """IQ-11: a contact under human takeover when its row comes up gets no POST, and its
    later rows are handled the same way."""
    contact = world.contact(covered=True)
    base = time.time() - 10
    m1 = world.message(contact, base, "takeover1")
    m2 = world.message(contact, base + 1, "takeover2")
    m3 = world.message(contact, base + 2, "takeover3")

    world.gate.clear()
    world.webhook(world.body(contact, m1))
    assert world.wait_parse_started(m1, timeout=10)
    world.webhook(world.body(contact, m2))
    world.webhook(world.body(contact, m3))
    assert wait_until(lambda: len(world.rows(contact)) >= 3, timeout=5)
    world.takeover.add(contact)  # staff took the conversation while m1 was running
    world.gate.set()

    wait_until(lambda: all(r["status"] not in ("queued", "processing") for r in world.rows(contact)), timeout=20)
    time.sleep(1.0)
    assert world.posted_messages(contact) == [str(m1)], (
        "only the row already past its takeover check is answered"
    )
    assert_settled(world, contact)
    assert str(m2) not in [m for m in world.parse_calls], "a row under takeover runs no turn"
