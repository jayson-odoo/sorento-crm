"""MCP-TOKEN-UI: the MCP server learns its valid tokens from the backend, not from env.

The backend answers `GET /api/v1/system/mcp-auth` (over the X-API-Key channel the server
already uses) with SHA-256 digests of the tokens that are valid now (current, plus the previous
one while it is in its grace window) and the Enforce switch. These tests pin the four states
from the plan (no token, token + Enforce off, token + Enforce on, rotation), the cache, the
refresh on a miss, and what a backend outage does.
"""
from __future__ import annotations

import json

import httpx
import pytest
from starlette.testclient import TestClient

from sorento_crm_mcp import auth
from sorento_crm_mcp.server import create_http_app
from sorento_crm_mcp.settings import Settings

from _token_source import FakeBackend, digest

OLD = "o" * 40  # fake fixtures, built at runtime so they never look like a real key
NEW = "n" * 40
LIST_TOOLS = {"jsonrpc": "2.0", "id": "1", "method": "tools/list", "params": {}}
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def _bearer(token: str) -> dict:
    return {**MCP_HEADERS, "Authorization": f"Bearer {token}"}


def _settings() -> Settings:
    return Settings(CRM_BASE_URL="http://crm.local", EXTERNAL_API_KEY="k")


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(auth, "_monotonic", c)
    return c


def _post(client, headers):
    return client.post("/mcp", json=LIST_TOOLS, headers=headers)


# --- state: no token set yet (the first deploy) -----------------------------------------------


def test_no_token_set_lets_a_headerless_call_through():
    backend = FakeBackend([], enforce=False)
    with TestClient(create_http_app(_settings(), token_fetcher=backend)) as c:
        assert _post(c, MCP_HEADERS).status_code == 200


def test_no_token_set_refuses_any_bearer_so_the_deploy_probe_still_sees_401():
    """deploy.yml probes with a deliberately wrong bearer and expects 401 (deploy.yml ~2266)."""
    backend = FakeBackend([], enforce=False)
    with TestClient(create_http_app(_settings(), token_fetcher=backend)) as c:
        resp = _post(c, _bearer("deploy-check-not-the-token"))
    assert resp.status_code == 401


def test_enforce_with_no_token_refuses_everything():
    backend = FakeBackend([], enforce=True)
    with TestClient(create_http_app(_settings(), token_fetcher=backend)) as c:
        assert _post(c, MCP_HEADERS).status_code == 401


# --- state changes reach a running server without a restart ------------------------------------


def test_enforce_switched_on_applies_after_the_cache_ttl(clock):
    backend = FakeBackend([NEW], enforce=False)
    with TestClient(create_http_app(_settings(), token_fetcher=backend)) as c:
        assert _post(c, MCP_HEADERS).status_code == 200
        backend.enforce = True
        assert _post(c, MCP_HEADERS).status_code == 200, "cached inside the TTL"
        clock.now += auth.CACHE_TTL_SECONDS + 0.1
        assert _post(c, MCP_HEADERS).status_code == 401
        assert _post(c, _bearer(NEW)).status_code == 200


def test_an_unknown_bearer_inside_the_miss_interval_is_refused_without_a_fetch(clock):
    """Why the backend waits SEND_NEW_AFTER_SECONDS (10 s, `app/services/mcp_auth_token.py`)
    before sending a freshly rotated token: inside MISS_REFRESH_SECONDS of the last fetch, an
    unknown bearer is refused without asking the backend again (review S1)."""
    backend = FakeBackend([OLD], enforce=True)
    with TestClient(create_http_app(_settings(), token_fetcher=backend)) as c:
        assert _post(c, _bearer(OLD)).status_code == 200
        backend.tokens = [NEW, OLD]
        clock.now += 1.0
        assert _post(c, _bearer(NEW)).status_code == 401
        assert auth.MISS_REFRESH_SECONDS < 10.0, "the backend's send-new delay must exceed this"


def test_a_new_token_is_accepted_through_the_refresh_on_a_miss(clock):
    """Past the miss interval (the backend's send-new delay guarantees that), the MCP cache must
    not refuse a rotated token."""
    backend = FakeBackend([OLD], enforce=True)
    with TestClient(create_http_app(_settings(), token_fetcher=backend)) as c:
        assert _post(c, _bearer(OLD)).status_code == 200
        backend.tokens = [NEW, OLD]
        clock.now += auth.MISS_REFRESH_SECONDS + 0.1
        assert _post(c, _bearer(NEW)).status_code == 200


def test_rotation_grace_old_and_new_both_pass_then_old_is_refused(clock):
    backend = FakeBackend([NEW, OLD], enforce=True)
    with TestClient(create_http_app(_settings(), token_fetcher=backend)) as c:
        assert _post(c, _bearer(NEW)).status_code == 200
        assert _post(c, _bearer(OLD)).status_code == 200
        backend.tokens = [NEW]  # grace over, or "Revoke previous now"
        clock.now += auth.CACHE_TTL_SECONDS + 0.1
        assert _post(c, _bearer(OLD)).status_code == 401
        assert _post(c, _bearer(NEW)).status_code == 200


def test_wrong_bearers_do_not_hammer_the_backend(clock):
    backend = FakeBackend([NEW], enforce=True)
    with TestClient(create_http_app(_settings(), token_fetcher=backend)) as c:
        _post(c, _bearer(NEW))
        before = backend.calls
        for _ in range(20):
            assert _post(c, _bearer("nope")).status_code == 401
        assert backend.calls - before <= 1


# --- backend down -----------------------------------------------------------------------------


def test_backend_down_keeps_the_last_known_tokens(clock):
    backend = FakeBackend([NEW], enforce=True)
    with TestClient(create_http_app(_settings(), token_fetcher=backend)) as c:
        assert _post(c, _bearer(NEW)).status_code == 200
        backend.down = True
        clock.now += auth.CACHE_TTL_SECONDS * 5
        assert _post(c, _bearer(NEW)).status_code == 200
        assert _post(c, MCP_HEADERS).status_code == 401, "an outage must not switch the gate off"


def test_cold_start_with_the_backend_down_is_503_not_an_exit(clock):
    backend = FakeBackend([NEW], enforce=True)
    backend.down = True
    with TestClient(create_http_app(_settings(), token_fetcher=backend)) as c:
        assert c.get("/healthz").status_code == 200
        resp = _post(c, MCP_HEADERS)
        assert resp.status_code == 503
        assert "crm_" not in resp.text
        backend.down = False
        clock.now += auth.MISS_REFRESH_SECONDS + 0.1
        assert _post(c, _bearer(NEW)).status_code == 200


@pytest.mark.parametrize(
    "answer",
    [
        {},
        {"enforce": "yes", "token_sha256": []},
        {"enforce": True, "token_sha256": "abc"},
        {"enforce": True, "token_sha256": [1]},
        ["not", "an", "object"],
    ],
)
def test_a_malformed_answer_is_treated_as_backend_down(answer, clock):
    async def fetch():
        return answer

    with TestClient(create_http_app(_settings(), token_fetcher=fetch)) as c:
        assert _post(c, MCP_HEADERS).status_code == 503


# --- the default fetcher ----------------------------------------------------------------------


async def test_default_fetcher_calls_the_backend_with_the_api_key():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"enforce": True, "token_sha256": [digest(NEW)]})

    fetch = auth.backend_fetcher(_settings(), transport=httpx.MockTransport(handler))
    answer = await fetch()
    assert answer == {"enforce": True, "token_sha256": [digest(NEW)]}
    assert str(seen[0].url) == "http://crm.local/api/v1/system/mcp-auth"
    assert seen[0].headers["X-API-Key"] == "k"
    assert seen[0].method == "GET"


async def test_default_fetcher_raises_on_an_error_status():
    fetch = auth.backend_fetcher(
        _settings(), transport=httpx.MockTransport(lambda r: httpx.Response(401, text="no"))
    )
    with pytest.raises(httpx.HTTPStatusError):
        await fetch()


def test_no_log_line_carries_a_token_or_a_digest(clock, caplog):
    backend = FakeBackend([NEW], enforce=True)
    with caplog.at_level("DEBUG"):
        with TestClient(create_http_app(_settings(), token_fetcher=backend)) as c:
            _post(c, _bearer(NEW))
            _post(c, _bearer("nope-wrong-token"))
            backend.down = True
            clock.now += auth.CACHE_TTL_SECONDS + 1
            _post(c, _bearer(NEW))
    assert NEW not in caplog.text
    assert digest(NEW) not in caplog.text
    assert "nope-wrong-token" not in caplog.text


def test_settings_no_longer_read_a_token_from_env(monkeypatch):
    monkeypatch.setenv("MCP_AUTH_TOKEN", "e" * 40)
    s = Settings(CRM_BASE_URL="http://crm.local", EXTERNAL_API_KEY="k")
    assert not hasattr(s, "mcp_auth_token")
    assert "e" * 40 not in json.dumps(s.model_dump(), default=str)
