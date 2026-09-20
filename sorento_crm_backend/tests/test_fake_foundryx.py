"""Keeps `tests/support/fake_foundryx.py` honest against the guards it exists to
rehearse (PLAN-autocount-pull-review.md "Local stack for the browser pass", SR4 fix
round). Not part of the SR1-4 red/green slices - the fake itself is test infrastructure,
never referenced by `app/`.

The last test drives the REAL `FoundryxAutocountClient` (never a second, parallel
fake client) against this app through an `httpx.MockTransport` that forwards to a
`fastapi.testclient.TestClient` - no `httpx.ASGITransport` involved, so this stays
provable without pinning an httpx version's ASGI-transport support.
"""
from __future__ import annotations

import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

import tests.support.fake_foundryx as fake_foundryx

API_KEY = "fake-key-for-the-browser-pass"


@pytest.fixture
def fake(monkeypatch):
    """A fresh in-memory fake per test - the module holds its snapshot store at
    module scope, so tests would otherwise see each other's builds."""
    monkeypatch.setattr(fake_foundryx, "_snapshots", {})
    monkeypatch.setattr(fake_foundryx, "_in_flight", {})
    monkeypatch.setattr(fake_foundryx, "BUILD_SECONDS", 0.0)
    return TestClient(fake_foundryx.app)


def test_missing_api_key_is_401_top_level_body(fake):
    resp = fake.post(
        "/api/v1/autocount/snapshots", json={"companyCode": "SRT", "entity": "products"}
    )
    assert resp.status_code == 401
    # Top-level, never nested under FastAPI's default `{"detail": ...}` - that is
    # exactly what `FoundryxAutocountClient._parse` reads off a real error body.
    assert resp.json() == {
        "code": "INVALID_API_KEY",
        "message": "Missing, malformed, unknown or revoked key.",
    }


def test_an_in_flight_build_returns_the_same_snapshot_id(monkeypatch, fake):
    monkeypatch.setattr(fake_foundryx, "BUILD_SECONDS", 100.0)
    headers = {"X-API-Key": API_KEY}
    body = {"companyCode": "SRT", "entity": "stock_balances"}

    first = fake.post("/api/v1/autocount/snapshots", json=body, headers=headers)
    second = fake.post("/api/v1/autocount/snapshots", json=body, headers=headers)

    assert first.status_code == 202
    assert first.json()["status"] == "building"
    assert first.json()["snapshotId"] == second.json()["snapshotId"]


def test_ready_header_recordcount_and_contenthash_match_the_a5_rule(fake):
    from app.tasks.autocount_pull_tasks import _content_hash

    headers = {"X-API-Key": API_KEY}
    build = fake.post(
        "/api/v1/autocount/snapshots",
        json={"companyCode": "SRT", "entity": "products"},
        headers=headers,
    )
    snapshot_id = build.json()["snapshotId"]

    status = fake.get(f"/api/v1/autocount/snapshots/{snapshot_id}", headers=headers)
    header = status.json()
    assert header["status"] == "ready"
    assert header["companyCode"] == "SRT"
    assert header["complete"] is True

    rows_resp = fake.get(
        f"/api/v1/autocount/snapshots/{snapshot_id}/rows",
        params={"page": 1},
        headers=headers,
    )
    rows = rows_resp.json()["rows"]
    assert header["recordCount"] == len(rows)
    assert header["contentHash"] == _content_hash(rows)


def test_unknown_snapshot_is_404_unknown_snapshot(fake):
    resp = fake.get(
        f"/api/v1/autocount/snapshots/{uuid.uuid4()}", headers={"X-API-Key": API_KEY}
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "UNKNOWN_SNAPSHOT"


def test_fetch_verified_snapshot_accepts_what_the_fake_serves(monkeypatch, fake):
    """Drives the REAL client + the REAL guard function against this app - if the fake
    ever drifts from what `fetch_verified_snapshot` requires (AC-PP-1, the A5 hash),
    this is what catches it, not a hand-rolled assertion on the fake's own JSON."""
    import app.services.foundryx_autocount_client as client_mod
    from app.config import settings
    from app.tasks.autocount_pull_tasks import fetch_verified_snapshot

    def _handler(request: httpx.Request) -> httpx.Response:
        response = fake.request(
            request.method,
            request.url.path,
            params=dict(request.url.params),
            content=request.content,
            headers=dict(request.headers),
        )
        return httpx.Response(response.status_code, content=response.content)

    monkeypatch.setattr(client_mod, "TRANSPORT", httpx.MockTransport(_handler))
    monkeypatch.setattr(settings, "foundryx_base_url", "http://fake-foundryx.test", raising=False)
    monkeypatch.setattr(settings, "foundryx_api_key", API_KEY, raising=False)

    client = client_mod.FoundryxAutocountClient()
    build = client.build("SRT", "products")
    snapshot_id = build["snapshotId"]

    header, rows, warnings = fetch_verified_snapshot(
        client, snapshot_id=snapshot_id, company_code="SRT"
    )

    assert header["status"] == "ready"
    assert len(rows) == header["recordCount"]
    assert warnings == []
