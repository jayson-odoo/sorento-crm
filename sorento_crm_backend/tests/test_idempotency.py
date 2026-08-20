"""Tests for the request-idempotency middleware (allowlisted action endpoints).

Uses the local Redis (settings.redis_url), but on its OWN logical DB (see
`_ISOLATED_REDIS_DB`) rather than the default one every other test shares.
Each test's Authorization token is a fresh uuid4, so within this file no two
tests, and no two calls, ever fingerprint to the same key - that part was
never the flaky bit.

The flaky bit (BL-034, "409 == 200") was `tests/conftest.py`'s
`_reset_global_state` autouse fixture: it flushes every `idemp:*` key after
EVERY test in the WHOLE suite, on the default DB, with no per-test scoping,
so that route tests elsewhere reusing predictable paths/bodies do not read
each other's cached replies. That flush runs on whichever xdist worker
happens to finish a test at that instant - it is not scoped to this file or
even this worker. `--dist loadfile` only serialises the tests INSIDE one
file; it does nothing to stop a DIFFERENT file on a DIFFERENT worker from
firing that flush in the gap between this file's own r1 and r2 calls. When
it lands there, it deletes r1's freshly-written "done" cache entry before r2
reads it: r2's NX-set still fails (Redis briefly still disagrees), but
`_await_result`'s poll now finds nothing to wait for and times out, so r2
comes back 409 (`duplicate_in_flight`) instead of the cached 200.

Moving this file onto its own Redis DB index takes it out of that flush's
blast radius entirely (the flush's own Redis client is cached process-wide
in `tests/conftest.py` against the DEFAULT db, so it can never reach here),
without narrowing what the conftest fixture protects for every other test.
"""
import uuid
from urllib.parse import urlsplit, urlunsplit

import pytest
from fastapi import FastAPI, Body
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.middleware.idempotency_middleware import IdempotencyMiddleware

# Unused elsewhere in the repo (checked: only app/config.py's default `.../0`
# and the local dev `.env`'s `.../6` name a db index) - picked once, fixed,
# not derived from anything random or worker-specific, because this file
# never runs concurrently with itself (`--dist loadfile`) and needs no
# further isolation than "not db 0".
_ISOLATED_REDIS_DB = "9"


def _isolated_redis_url(base_url: str) -> str:
    parts = urlsplit(base_url)
    return urlunsplit(parts._replace(path=f"/{_ISOLATED_REDIS_DB}"))


@pytest.fixture()
def client(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "redis_url", _isolated_redis_url(settings.redis_url))

    app = FastAPI()
    app.add_middleware(IdempotencyMiddleware)

    state = {"n": 0}

    # Allowlisted suffix → deduped.
    @app.post("/api/v1/procurement/purchase-requests/{rid}/set-pending-approval")
    async def set_pending(rid: str):
        state["n"] += 1
        return {"ran": state["n"], "rid": rid}

    # Allowlisted but returns 500 → must NOT be cached.
    @app.post("/api/v1/procurement/purchase-requests/{rid}/process")
    async def process(rid: str):
        state["n"] += 1
        return JSONResponse(status_code=500, content={"ran": state["n"]})

    # Allowlisted but answers 202 (a deferred form action) → must NOT be cached.
    # The regression this pins: approve → undo → approve within the dedupe window
    # returned the FIRST 202 from cache, so the second action was never parked and
    # the countdown banner never re-appeared (PLAN-form-sla-undo.md).
    @app.post("/api/v1/procurement/purchase-requests/{rid}/approval-decision")
    async def decide(rid: str):
        state["n"] += 1
        return JSONResponse(status_code=202, content={"deferred": True, "ran": state["n"]})

    # NOT allowlisted (a create) → must run every time.
    @app.post("/api/v1/procurement/purchase-requests")
    async def create(payload: dict = Body(default={})):
        state["n"] += 1
        return {"ran": state["n"]}

    c = TestClient(app)
    c.counter = state
    yield c

    # Best-effort hygiene, not a correctness dependency: each test's token is
    # already a fresh uuid4, so nothing in this file ever re-reads a leftover
    # key. Clears the isolated db anyway so it doesn't quietly accumulate
    # short-TTL keys across a long local session.
    try:
        import redis as _redis

        _redis.from_url(settings.redis_url, decode_responses=True).flushdb()
    except Exception:
        pass


def _auth():
    return {"Authorization": f"Bearer test-{uuid.uuid4()}"}


def test_duplicate_within_window_runs_once(client):
    h = _auth()
    url = "/api/v1/procurement/purchase-requests/abc/set-pending-approval"
    r1 = client.post(url, headers=h)
    r2 = client.post(url, headers=h)  # identical replay
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json() == r2.json()                 # same response served
    assert client.counter["n"] == 1                # handler ran ONCE
    assert r1.headers.get("idempotent-replay") is None
    assert r2.headers.get("idempotent-replay") == "true"


def test_different_caller_not_deduped(client):
    url = "/api/v1/procurement/purchase-requests/abc/set-pending-approval"
    client.post(url, headers=_auth())
    client.post(url, headers=_auth())            # different token → different key
    assert client.counter["n"] == 2


def test_different_path_not_deduped(client):
    h = _auth()
    client.post("/api/v1/procurement/purchase-requests/A/set-pending-approval", headers=h)
    client.post("/api/v1/procurement/purchase-requests/B/set-pending-approval", headers=h)
    assert client.counter["n"] == 2               # ids differ in path


def test_non_allowlisted_create_always_runs(client):
    h = _auth()
    client.post("/api/v1/procurement/purchase-requests", json={"x": 1}, headers=h)
    client.post("/api/v1/procurement/purchase-requests", json={"x": 1}, headers=h)
    assert client.counter["n"] == 2               # creates are NOT deduped


def test_5xx_not_cached(client):
    h = _auth()
    url = "/api/v1/procurement/purchase-requests/zz/process"
    r1 = client.post(url, headers=h)
    r2 = client.post(url, headers=h)
    assert r1.status_code == 500 and r2.status_code == 500
    assert client.counter["n"] == 2               # error not cached → retry re-ran


def test_202_deferred_not_cached(client):
    """A 202 promises future work, not a result - replaying it from cache means the
    second click parks NOTHING while telling the user it did."""
    h = _auth()
    url = "/api/v1/procurement/purchase-requests/zz/approval-decision"
    r1 = client.post(url, headers=h)
    r2 = client.post(url, headers=h)
    assert r1.status_code == 202 and r2.status_code == 202
    assert client.counter["n"] == 2               # both requests really ran
    assert r2.headers.get("idempotent-replay") is None
