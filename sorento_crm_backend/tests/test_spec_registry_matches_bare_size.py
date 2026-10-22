"""R6-5 S1: the registry API can set `matches_bare_size` (the flag a bare size reads, R6-1).

A new key is created with the flag, an existing key is PATCHed to carry it, and both the create
response and the read serializer return it. Before the fix the field was dropped on the way in
and absent on the way out.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app  # noqa: E402  MUST be first app import
from tests.test_spec_registry_pr2_routes import _BASE, _MERCHANDISER, _REGISTRY_ADMIN, _key, api  # noqa: F401


def _read(client: TestClient, as_user, spec_key: str) -> dict:
    as_user(_MERCHANDISER)  # the list read runs on products.view
    got = client.get(_BASE)
    assert got.status_code == 200, got.text[:300]
    return next(r for r in got.json()["keys"] if r["spec_key"] == spec_key)


def test_a_patch_sets_and_clears_matches_bare_size(api):
    db, _as = api
    _as(_REGISTRY_ADMIN)
    client = TestClient(app)
    _key(db, "zzt_span_width", data_type="numeric", unit="mm")

    on = client.patch(f"{_BASE}/zzt_span_width", json={"matches_bare_size": True})
    assert on.status_code == 200, on.text
    assert _read(client, _as, "zzt_span_width").get("matches_bare_size") is True
    _as(_REGISTRY_ADMIN)

    off = client.patch(f"{_BASE}/zzt_span_width", json={"matches_bare_size": False})
    assert off.status_code == 200, off.text
    assert _read(client, _as, "zzt_span_width").get("matches_bare_size") is False


def test_a_new_key_is_created_with_matches_bare_size(api):
    db, _as = api
    _as(_REGISTRY_ADMIN)
    client = TestClient(app)

    response = client.post(
        _BASE,
        json={"spec_key": "zzt_span_length", "label": "Span length", "data_type": "numeric", "unit": "mm",
              "matches_bare_size": True},
    )
    assert response.status_code == 201, response.text
    assert _read(client, _as, "zzt_span_length").get("matches_bare_size") is True
