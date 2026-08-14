"""Uniform request-idempotency middleware (duplicate-submit / network-slowness backstop).

Why: a mutating action can be delivered more than once for a single user intent
(double-click before the FE disables, FE re-enabling on stale data while a refetch
lags, client/proxy/Cloudflare re-send on a slow upstream, two stale tabs). For
action endpoints whose side effects are harmful to duplicate (SLA assignment,
Respond sends, status transitions) this caused real duplicates — see
docs/plans/PLAN-uniform-idempotency.md and the form-SLA duplicate incident.

Design (see plan + its internal-grill verdicts):
- Pure ASGI so the request body can be buffered + replayed correctly (BaseHTTPMiddleware
  loses the downstream body when you read it).
- Scoped to an explicit ALLOWLIST of transition/side-effect endpoints — NOT all POSTs
  (global body-hash would silently collapse two legitimate identical creates).
- Key = sha256(session_token : method : path : body). Token (not user_id) because
  middleware runs before the auth dependency; a browser session carries one token.
- Redis SET NX is the cross-process lock. First request runs + caches the 2xx response
  for `result_ttl` (the dedupe window, ~10s). A replay within the window returns the
  cached response (handler never re-runs). A replay while the first is still in flight
  waits briefly then returns 409.
- Fail-open: any Redis error → process normally (never block a write on the cache).
- Never caches 5xx (so the user can retry) and never caches Set-Cookie/auth headers.
- `observe` mode logs would-be-duplicates without blocking (for safe rollout).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

# Endpoints whose re-execution is semantically a no-op and whose duplication is the
# harm. Matched by path suffix (ids live in the path, so suffix match is id-agnostic).
# Extend here — do NOT add create/collection POSTs (body-hash would collapse two
# legitimate identical creates; those are covered by the FE primitive + DB constraints).
_ALLOWLIST_SUFFIXES = (
    "/set-pending-approval",
    "/approval-decision",
    "/reject-submitted",
    "/process",
    "/close",
    "/send-approval-link",
    "/escalate",
)
# Some action paths are better matched by regex (e.g. SLA integration endpoints).
_ALLOWLIST_REGEXES = (
    re.compile(r"/api/v1/sla/.+/escalate$"),
    re.compile(r"/api/v1/notifications/.+/(send|resend)$"),
)

# Endpoints that own a STRONGER, stateful idempotency of their own, and whose
# correct replay is NOT a byte copy of the first response. This backstop caches a
# 2xx body for `result_ttl` seconds and returns it verbatim; that is right for a
# transition whose replay is a no-op, and wrong for one whose replay must report
# what has happened SINCE. `/api/v1/external/media/process` is the second kind: it
# keys idempotency on the respond.io message id in the `contact_media_usage`
# ledger (durable, not a 10 second window), and its replay must carry
# `idempotent_replay: true` plus the job's CURRENT status - a cached `pending`
# would tell n8n the extraction is still running long after it finished.
#
# Checked before the allowlist because it collides with it by name: the suffix
# `/process` was added for the form-action endpoints, not for this one.
_SELF_IDEMPOTENT_REGEXES = (
    re.compile(r"^/api/v1/external/media/process$"),
)

_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}

_KEY_PREFIX = "idemp:"


def _is_allowlisted(method: str, path: str) -> bool:
    if method not in _MUTATING:
        return False
    if any(rx.search(path) for rx in _SELF_IDEMPOTENT_REGEXES):
        return False
    if path.endswith(_ALLOWLIST_SUFFIXES):
        return True
    return any(rx.search(path) for rx in _ALLOWLIST_REGEXES)


def _header(headers: list[tuple[bytes, bytes]], name: bytes) -> Optional[bytes]:
    name = name.lower()
    for k, v in headers:
        if k.lower() == name:
            return v
    return None


def _session_identity(headers: list[tuple[bytes, bytes]]) -> str:
    """A stable per-caller token: bearer JWT/session token, else X-API-Key, else the
    raw cookie header. Hashed into the key — never logged or stored in clear."""
    auth = _header(headers, b"authorization")
    if auth and auth.lower().startswith(b"bearer "):
        return auth[7:].decode("latin-1", "ignore")
    apikey = _header(headers, b"x-api-key")
    if apikey:
        return apikey.decode("latin-1", "ignore")
    cookie = _header(headers, b"cookie")
    if cookie:
        return cookie.decode("latin-1", "ignore")
    return "anon"


class IdempotencyMiddleware:
    def __init__(self, app):
        self.app = app
        self._redis = None
        self._redis_init = False

    def _get_redis(self):
        if self._redis_init:
            return self._redis
        self._redis_init = True
        try:
            import redis as _redis

            self._redis = _redis.from_url(settings.redis_url, decode_responses=True)
        except Exception as e:  # pragma: no cover - fail open
            logger.warning("Idempotency: Redis init failed, dedupe disabled: %s", e)
            self._redis = None
        return self._redis

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or not getattr(settings, "idempotency_enabled", True):
            return await self.app(scope, receive, send)

        method = scope.get("method", "GET")
        path = scope.get("path", "")
        if not _is_allowlisted(method, path):
            return await self.app(scope, receive, send)

        # ---- buffer the request body (so we can hash AND replay it downstream) ----
        body = b""
        messages: list[dict] = []
        more = True
        while more:
            msg = await receive()
            if msg["type"] == "http.disconnect":
                return  # client gone; nothing to do
            body += msg.get("body", b"")
            more = msg.get("more_body", False)
            messages.append(msg)

        max_body = int(getattr(settings, "idempotency_max_body", 262144))
        replay = _replay_receive(messages)
        if len(body) > max_body:
            # Too large to fingerprint safely — pass through untouched.
            return await self.app(scope, replay, send)

        r = self._get_redis()
        if r is None:
            return await self.app(scope, replay, send)  # fail open

        token = _session_identity(scope.get("headers", []))
        fp = hashlib.sha256(
            b"%s\x00%s\x00%s\x00%s"
            % (token.encode(), method.encode(), path.encode(), body)
        ).hexdigest()
        key = _KEY_PREFIX + fp

        mode = getattr(settings, "idempotency_mode", "enforce")
        lock_ttl = int(getattr(settings, "idempotency_lock_ttl", 60))
        result_ttl = int(getattr(settings, "idempotency_result_ttl", 10))
        wait_ms = int(getattr(settings, "idempotency_wait_ms", 2000))

        try:
            acquired = r.set(key, json.dumps({"state": "in_progress"}), nx=True, ex=lock_ttl)
        except Exception as e:  # pragma: no cover - fail open
            logger.warning("Idempotency: Redis SET failed, fail-open: %s", e)
            return await self.app(scope, replay, send)

        if not acquired:
            # A replay. In observe mode just log and run normally.
            if mode == "observe":
                logger.warning("Idempotency[observe]: duplicate %s %s (would dedupe)", method, path)
                return await self.app(scope, replay, send)
            cached = await self._await_result(r, key, wait_ms)
            if cached is not None:
                logger.info("Idempotency: served cached replay for %s %s", method, path)
                return await _send_cached(send, cached)
            # First still in flight past the wait bound.
            return await _send_json(send, 409, {"code": "duplicate_in_flight",
                                                "message": "An identical request is still being processed."})

        # ---- first request: run the app, capture the response ----
        captured = {"status": 500, "content_type": "application/json", "body": b""}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                captured["status"] = message["status"]
                ct = _header(message.get("headers", []), b"content-type")
                if ct:
                    captured["content_type"] = ct.decode("latin-1", "ignore")
            elif message["type"] == "http.response.body":
                captured["body"] += message.get("body", b"")
            await send(message)

        try:
            await self.app(scope, replay, send_wrapper)
        except Exception:
            # Handler blew up — drop the lock so the user can retry immediately.
            try:
                r.delete(key)
            except Exception:
                pass
            raise

        status_code = captured["status"]
        try:
            # 202 is never cacheable. It means "accepted, not yet applied", and its body
            # carries a single-use pending-action id. Replaying it hands the client an id
            # that may since have been undone or committed, so the caller sees a stale
            # countdown - or, as observed, no countdown at all because the handler never
            # ran the second time. Duplicate submits of a deferred action are already
            # blocked at the database by the one-pending-per-form unique index, so
            # skipping the cache here loses no protection.
            if status_code == 202:
                r.delete(key)
            elif 200 <= status_code < 300 and len(captured["body"]) <= max_body:
                r.set(key, json.dumps({
                    "state": "done",
                    "status": status_code,
                    "content_type": captured["content_type"],
                    "body": captured["body"].decode("latin-1"),  # latin-1 round-trips bytes
                }), ex=result_ttl)
            else:
                # Non-2xx (incl. validation 4xx) or oversized body: don't cache; let retries through.
                r.delete(key)
        except Exception as e:  # pragma: no cover
            logger.warning("Idempotency: result cache write failed: %s", e)
            try:
                r.delete(key)
            except Exception:
                pass

    async def _await_result(self, r, key: str, wait_ms: int) -> Optional[dict]:
        deadline = time.monotonic() + (wait_ms / 1000.0)
        while True:
            try:
                raw = r.get(key)
            except Exception:
                return None
            if raw:
                try:
                    rec = json.loads(raw)
                except Exception:
                    return None
                if rec.get("state") == "done":
                    return rec
            if time.monotonic() >= deadline:
                return None
            await asyncio.sleep(0.05)


def _replay_receive(messages: list[dict]):
    """An ASGI receive that yields the buffered request messages, then blocks on
    disconnect — so the downstream handler reads the same body."""
    queue = list(messages)

    async def receive():
        if queue:
            return queue.pop(0)
        return {"type": "http.request", "body": b"", "more_body": False}

    return receive


async def _send_cached(send, rec: dict):
    body = rec.get("body", "").encode("latin-1")
    headers = [
        (b"content-type", rec.get("content_type", "application/json").encode("latin-1")),
        (b"content-length", str(len(body)).encode()),
        (b"idempotent-replay", b"true"),
    ]
    await send({"type": "http.response.start", "status": int(rec.get("status", 200)), "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def _send_json(send, status_code: int, payload: dict):
    body = json.dumps(payload).encode()
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode()),
        (b"idempotent-replay", b"true"),
    ]
    await send({"type": "http.response.start", "status": status_code, "headers": headers})
    await send({"type": "http.response.body", "body": body})
