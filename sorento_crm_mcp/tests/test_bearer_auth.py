"""SEC-MCP-AUTH (UAC AUTH-1..6): every MCP request carries `Authorization: Bearer <token>`.

MCP-TOKEN-UI: the token is no longer an env value. The backend holds it (set from Settings >
Integrations) and the MCP server learns which tokens are valid from it; `FakeBackend` stands in
for that answer here. "enforce" is the screen's Enforce switch on, "permit" is it off.

The server used to accept anyone who could reach :8765 and acted with the shared CRM key, write
tools included. `create_http_app` is the one ASGI app `__main__` serves; these tests drive it
in-process through Starlette's TestClient, which runs the lifespan so FastMCP's session manager is
live, exactly as uvicorn does. Ported from PR #1548 (MCP-LOCKDOWN) plus the permit mode.
"""
from __future__ import annotations

import json
import logging

import pytest
from starlette.testclient import TestClient

from sorento_crm_mcp.server import create_http_app
from sorento_crm_mcp.settings import Settings

from _token_source import FakeBackend

TOKEN = "x" * 40  # fake fixture, built at runtime so it never looks like a real key
LIST_TOOLS = {"jsonrpc": "2.0", "id": "1", "method": "tools/list", "params": {}}
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
AUTH = {**MCP_HEADERS, "Authorization": f"Bearer {TOKEN}"}


def _settings(**overrides) -> Settings:
    values = {"CRM_BASE_URL": "http://crm.local", "EXTERNAL_API_KEY": "k"}
    values.update(overrides)
    return Settings(**values)


def _app(tokens=(TOKEN,), *, enforce=True):
    return create_http_app(_settings(), token_fetcher=FakeBackend(list(tokens), enforce=enforce))


def _tool_names(resp) -> list[str]:
    """The JSON-RPC result, whether FastMCP answered as JSON or as one SSE frame."""
    text = resp.text
    if "text/event-stream" in resp.headers.get("content-type", ""):
        text = [ln[5:].strip() for ln in text.splitlines() if ln.startswith("data:")][-1]
    return [t["name"] for t in json.loads(text)["result"]["tools"]]


@pytest.fixture
def client():
    with TestClient(_app()) as c:
        yield c


@pytest.fixture
def permit_client():
    with TestClient(_app(enforce=False)) as c:
        yield c


def test_no_token_is_401(client):
    resp = client.post("/mcp", json=LIST_TOOLS, headers=MCP_HEADERS)
    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate", "").lower().startswith("bearer")
    assert "crm_" not in resp.text, "a refused request must not leak the tool list"


def test_wrong_token_is_401(client):
    resp = client.post("/mcp", json=LIST_TOOLS, headers={**MCP_HEADERS, "Authorization": "Bearer nope"})
    assert resp.status_code == 401


def test_token_as_another_scheme_is_401(client):
    resp = client.post("/mcp", json=LIST_TOOLS, headers={**MCP_HEADERS, "Authorization": f"Basic {TOKEN}"})
    assert resp.status_code == 401


def test_token_with_a_suffix_is_401(client):
    resp = client.post("/mcp", json=LIST_TOOLS, headers={**MCP_HEADERS, "Authorization": f"Bearer {TOKEN}x"})
    assert resp.status_code == 401


def test_right_token_lists_the_tools(client):
    resp = client.post("/mcp", json=LIST_TOOLS, headers=AUTH)
    assert resp.status_code == 200, resp.text
    names = _tool_names(resp)
    assert "crm_master_products_list" in names
    assert len(names) > 10


def test_scheme_is_case_insensitive(client):
    resp = client.post("/mcp", json=LIST_TOOLS, headers={**MCP_HEADERS, "Authorization": f"bearer {TOKEN}"})
    assert resp.status_code == 200


def test_other_paths_need_the_token_too(client):
    assert client.get("/mcp").status_code == 401
    assert client.get("/anything-else").status_code == 401


def test_healthz_needs_no_token(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.text == "ok"


def test_starts_with_no_token_env_at_all():
    """The release-safety rule: a deploy with no token anywhere must not exit (it used to)."""
    with TestClient(_app(tokens=(), enforce=False)) as c:
        assert c.get("/healthz").status_code == 200


def test_websocket_is_refused(client):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/mcp") as ws:
            ws.receive_text()


def test_the_compare_is_constant_time():
    import inspect

    from sorento_crm_mcp import auth

    assert "hmac.compare_digest" in inspect.getsource(auth)


# --- permit mode (one release, so callers move over without an outage) -------------------------


def test_permit_lets_a_call_with_no_header_through_and_warns(permit_client, caplog):
    with caplog.at_level(logging.WARNING, logger="sorento_crm_mcp.auth"):
        resp = permit_client.post("/mcp", json=LIST_TOOLS, headers=MCP_HEADERS)
    assert resp.status_code == 200, resp.text
    assert any("Enforce is off" in r.getMessage() for r in caplog.records)


def test_permit_still_refuses_a_wrong_token(permit_client):
    resp = permit_client.post("/mcp", json=LIST_TOOLS, headers={**MCP_HEADERS, "Authorization": "Bearer nope"})
    assert resp.status_code == 401


def test_permit_right_token_passes_without_a_warning(permit_client, caplog):
    with caplog.at_level(logging.WARNING, logger="sorento_crm_mcp.auth"):
        resp = permit_client.post("/mcp", json=LIST_TOOLS, headers=AUTH)
    assert resp.status_code == 200
    assert not [r for r in caplog.records if "Enforce is off" in r.getMessage()]


def test_no_log_line_carries_the_token(client, permit_client, caplog):
    with caplog.at_level(logging.DEBUG):
        client.post("/mcp", json=LIST_TOOLS, headers=AUTH)
        client.post("/mcp", json=LIST_TOOLS, headers={**MCP_HEADERS, "Authorization": f"Bearer {TOKEN}x"})
        permit_client.post("/mcp", json=LIST_TOOLS, headers=MCP_HEADERS)
        permit_client.post("/mcp", json=LIST_TOOLS, headers={**MCP_HEADERS, "Authorization": "Bearer nope"})
    assert TOKEN not in caplog.text
    assert "nope" not in caplog.text
