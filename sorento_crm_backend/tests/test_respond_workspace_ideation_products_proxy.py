"""Sorento proxy for the shared-service ideation-product catalog.

``GET /api/v1/system/respond-workspaces/ideation-products`` degrades gracefully  - 
ALWAYS returns ``{products, error}`` (never 500). Covers:

- live-preview override path (``base_url`` + ``api_key`` query args win);
- saved-workspace path (``workspace_id`` -> stored URL + decrypted intake key);
- graceful empty + error on an upstream failure / rejected key;
- disabled hint when neither the live pair nor a resolvable workspace is present.

Deterministic/offline: a blank Postgres schema + a stubbed ``httpx.Client``; no
live shared-service.
"""
from __future__ import annotations

import uuid

import httpx
import pytest

import app.api.v1.system.respond_workspaces as rw
from app.models.respond_workspace import RespondWorkspace
from app.schemas.respond_workspace import RespondWorkspaceCreate
from app.services.respond_workspace_service import RespondWorkspaceService
from tests._pg_fixture import blank_session


@pytest.fixture
def session():
    with blank_session() as s:
        yield s


class _FakeResponse:
    def __init__(self, *, status_code=200, json_body=None):
        self.status_code = status_code
        self._json_body = json_body if json_body is not None else []

    def json(self):
        return self._json_body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "err", request=httpx.Request("GET", "http://x"), response=self
            )


class _FakeClient:
    """Records the last GET (url + headers) and returns a canned response."""

    last_url: str | None = None
    last_headers: dict | None = None

    def __init__(self, response=None, exc=None, **_kw):
        self._response = response if response is not None else _FakeResponse()
        self._exc = exc

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url, headers=None):
        _FakeClient.last_url = url
        _FakeClient.last_headers = headers
        if self._exc is not None:
            raise self._exc
        return self._response


def _patch_httpx(monkeypatch, *, response=None, exc=None):
    def factory(*_a, **_kw):
        return _FakeClient(response=response, exc=exc)

    monkeypatch.setattr(rw.httpx, "Client", factory)


def _call(session, **kw):
    return rw.list_ideation_products(db=session, _user={}, **kw)


# ── override (live-preview) path ──────────────────────────────────────────────
def test_override_path_uses_typed_url_and_key(session, monkeypatch):
    _patch_httpx(
        monkeypatch,
        response=_FakeResponse(json_body=[{"id": "p1", "name": "Sorento CRM"}]),
    )
    out = _call(
        session,
        workspace_id=None,
        base_url="http://localhost:8001",
        api_key="fxw_live_typed",
    )
    assert out["error"] is None
    assert out["products"] == [{"id": "p1", "name": "Sorento CRM"}]
    assert _FakeClient.last_url == "http://localhost:8001/ideation/intake/products"
    assert _FakeClient.last_headers == {"Authorization": "Bearer fxw_live_typed"}


# ── saved-workspace path ──────────────────────────────────────────────────────
def test_workspace_path_uses_stored_url_and_decrypted_key(session, monkeypatch):
    svc = RespondWorkspaceService(session)
    row = svc.create(
        RespondWorkspaceCreate(
            space_id="space-1",
            api_key="k",
            is_default=True,
            ideation_shared_service_url="http://saved-host:8001",
            ideation_intake_api_key="stored-intake-key-99",
        )
    )
    _patch_httpx(
        monkeypatch,
        response=_FakeResponse(json_body=[{"id": "p9", "name": "Saved Product"}]),
    )
    out = _call(session, workspace_id=row.id, base_url=None, api_key=None)
    assert out["error"] is None
    assert out["products"] == [{"id": "p9", "name": "Saved Product"}]
    assert _FakeClient.last_url == "http://saved-host:8001/ideation/intake/products"
    # decrypted stored key is used as the bearer
    assert _FakeClient.last_headers == {"Authorization": "Bearer stored-intake-key-99"}


def test_override_wins_over_saved_workspace(session, monkeypatch):
    svc = RespondWorkspaceService(session)
    row = svc.create(
        RespondWorkspaceCreate(
            space_id="space-2",
            api_key="k",
            is_default=True,
            ideation_shared_service_url="http://saved-host:8001",
            ideation_intake_api_key="stored-key",
        )
    )
    _patch_httpx(monkeypatch, response=_FakeResponse(json_body=[]))
    _call(
        session,
        workspace_id=row.id,
        base_url="http://typed-host:8001",
        api_key="typed-key",
    )
    assert _FakeClient.last_url == "http://typed-host:8001/ideation/intake/products"
    assert _FakeClient.last_headers == {"Authorization": "Bearer typed-key"}


# ── graceful degradation ──────────────────────────────────────────────────────
def test_missing_config_returns_hint_not_error(session, monkeypatch):
    # No workspace, no overrides -> disabled hint, empty list, no upstream call.
    called = {"hit": False}

    def factory(*_a, **_kw):
        called["hit"] = True
        return _FakeClient()

    monkeypatch.setattr(rw.httpx, "Client", factory)
    out = _call(session, workspace_id=None, base_url=None, api_key=None)
    assert out["products"] == []
    assert "URL" in out["error"] and "key" in out["error"].lower()
    assert called["hit"] is False


def test_unknown_workspace_returns_error(session, monkeypatch):
    # A well-formed id that is simply absent. The previous literal here was
    # "does-not-exist", which is not a UUID at all: sqlite compared it as text
    # and returned no row, so the test passed for the wrong reason. Postgres
    # rejects it before the lookup, which hides the branch under test -- see the
    # separate malformed-id defect noted in the report.
    absent_id = str(uuid.uuid4())
    _patch_httpx(monkeypatch, response=_FakeResponse(json_body=[]))
    out = _call(session, workspace_id=absent_id, base_url=None, api_key=None)
    assert out["products"] == []
    assert out["error"] == "Workspace not found."


def test_upstream_connection_error_degrades(session, monkeypatch):
    _patch_httpx(monkeypatch, exc=httpx.ConnectError("refused"))
    out = _call(
        session, workspace_id=None, base_url="http://localhost:8001", api_key="k"
    )
    assert out["products"] == []
    assert out["error"] and "reach" in out["error"].lower()


def test_upstream_401_reports_rejected_key(session, monkeypatch):
    _patch_httpx(monkeypatch, response=_FakeResponse(status_code=401))
    out = _call(
        session, workspace_id=None, base_url="http://localhost:8001", api_key="bad"
    )
    assert out["products"] == []
    assert out["error"] and "key" in out["error"].lower()


def test_malformed_items_are_skipped(session, monkeypatch):
    _patch_httpx(
        monkeypatch,
        response=_FakeResponse(
            json_body=[
                {"id": "ok", "name": "Good"},
                {"name": "no id"},  # dropped
                "not a dict",  # dropped
                {"id": "noname"},  # kept, name falls back to id
            ]
        ),
    )
    out = _call(
        session, workspace_id=None, base_url="http://localhost:8001", api_key="k"
    )
    assert out["error"] is None
    assert out["products"] == [
        {"id": "ok", "name": "Good"},
        {"id": "noname", "name": "noname"},
    ]
