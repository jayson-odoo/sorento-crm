"""Tests for the request-idempotency middleware (allowlisted action endpoints).

Uses the local Redis (settings.redis_url). Each test uses a unique Authorization
token so fingerprints never collide across tests / runs.
"""
import uuid

import pytest
from fastapi import FastAPI, Body
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.middleware.idempotency_middleware import IdempotencyMiddleware


@pytest.fixture()
def client():
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

    # NOT allowlisted (a create) → must run every time.
    @app.post("/api/v1/procurement/purchase-requests")
    async def create(payload: dict = Body(default={})):
        state["n"] += 1
        return {"ran": state["n"]}

    c = TestClient(app)
    c.counter = state
    return c


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
