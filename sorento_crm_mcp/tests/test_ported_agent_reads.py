"""AGENTIC-UNIFY PR 4, slice 1 (red): AC-4 and the AC-5 guard, the twelve ported reads through the REAL compiled MCP tool.

Panel tests stub MCP, so only this file proves the tools can be reached as the agent calls them:
- staff shape: blank `contact_id` and `space_id`, `X-MCP-Scope: staff` + `X-MCP-Staff-User`
  (what `_mcp_call` sends for a staff principal);
- linked-contact shape: a real-looking `contact_id` and `space_id`, no staff headers.

Only the network is faked, at the httpx transport, so the request asserted is the one that would
reach the CRM. The agent's dispatch always sends the pair, even to tools whose catalog entry does not
declare it, so the pair is passed to every tool in both shapes.

The backend venv's `sorento_crm_mcp` is an editable install of the PRIMARY checkout: the worktree
copy is put first on sys.path and checked below.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest
from starlette.testclient import TestClient

_WORKTREE_MCP = str(Path(__file__).resolve().parents[1])
if _WORKTREE_MCP not in sys.path or sys.path[0] != _WORKTREE_MCP:
    sys.path.insert(0, _WORKTREE_MCP)

import sorento_crm_mcp  # noqa: E402
from sorento_crm_mcp import http_client  # noqa: E402
from sorento_crm_mcp.catalog import CATALOG  # noqa: E402
from sorento_crm_mcp.server import create_http_app  # noqa: E402
from sorento_crm_mcp.settings import Settings  # noqa: E402

from _token_source import FakeBackend  # noqa: E402

TOKEN = "x" * 40
STAFF_ID = "11111111-1111-4111-8111-111111111111"
PROJECT_ID = "55555555-5555-4555-8555-555555555555"
IDENTITY = "x-staff-user"
CONTACT = "900000008"
SPACE = "364817"

BASE = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json",
        "Authorization": f"Bearer {TOKEN}"}
STAFF = {**BASE, "X-MCP-Scope": "staff", "X-MCP-Staff-User": STAFF_ID}

# tool -> (route path fragment the call must reach, extra arguments the tool itself requires)
TOOLS: dict[str, tuple[str, dict]] = {
    "crm_complaints_list": ("/complaints-management/complaints", {}),
    "crm_complaint_analytics": ("/complaints-management/complaints/analytics", {}),
    "crm_sla_conversation_tracking_dashboard": ("/conversation-sla-tracking/dashboard", {}),
    "crm_sla_conversation_tracking_list": ("/sla-management/conversation-sla-tracking", {}),
    "crm_sla_conversation_event_logs_list": ("/conversation-sla-tracking/event-logs", {}),
    "crm_projects_list": ("/project-sales/projects", {}),
    "crm_project_detail": (f"/project-sales/projects/{PROJECT_ID}", {"project_id": PROJECT_ID}),
    "crm_project_quotations_list": (
        f"/project-sales/projects/{PROJECT_ID}/quotations",
        {"project_id": PROJECT_ID},
    ),
    "crm_project_forecast": ("/project-sales/reports/forecast", {}),
    "crm_order_analytics": ("/order-management/orders/analytics", {}),
    "crm_find": ("/master-data/products/find", {"filters": "[]"}),
    "crm_system_tool_capabilities_summary": ("/system/tool-capabilities/summary", {}),
}

PAIRS = {"staff": {"contact_id": "", "space_id": ""}, "contact": {"contact_id": CONTACT, "space_id": SPACE}}


def test_the_worktree_copy_of_the_mcp_package_is_the_one_under_test():
    assert Path(sorento_crm_mcp.__file__).resolve().is_relative_to(Path(_WORKTREE_MCP).resolve()), (
        sorento_crm_mcp.__file__
    )


@pytest.fixture
def crm(monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": [{"ref": "ZZT-1"}], "total": 1})

    real = httpx.AsyncClient

    def client_with_transport(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(http_client.httpx, "AsyncClient", client_with_transport)
    return seen


@pytest.fixture
def mcp():
    settings = Settings(CRM_BASE_URL="http://crm.local", EXTERNAL_API_KEY="k")
    with TestClient(create_http_app(settings, token_fetcher=FakeBackend([TOKEN]))) as client:
        yield client


def _call(mcp, name, arguments, headers) -> dict:
    body = {"jsonrpc": "2.0", "id": "1", "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    resp = mcp.post("/mcp", json=body, headers=headers)
    assert resp.status_code == 200, resp.text
    text = resp.text
    if "text/event-stream" in resp.headers.get("content-type", ""):
        text = [ln[5:].strip() for ln in text.splitlines() if ln.startswith("data:")][-1]
    return json.loads(text)


def _crm(seen):
    return [r for r in seen if r.url.path.startswith("/api/") and r.url.path != "/api/v1/system/mcp-routing"]


def _refusal_text(reply: dict) -> str:
    """Everything the reply says, flattened, so a refusal is found wherever the server put it."""
    return json.dumps(reply)


@pytest.mark.parametrize("shape", ["staff", "contact"])
@pytest.mark.parametrize("name", list(TOOLS))
def test_AC4_each_read_reaches_its_route_in_both_shapes(mcp, crm, name, shape):
    fragment, extra = TOOLS[name]
    headers = STAFF if shape == "staff" else BASE
    reply = _call(mcp, name, {**extra, **PAIRS[shape]}, headers)
    flat = _refusal_text(reply)
    assert "scope_required" not in flat, flat
    assert "validation error" not in flat.lower() and "missing" not in flat.lower(), flat
    assert reply.get("result", {}).get("isError") is not True, flat
    sent = _crm(crm)
    assert sent, f"{name} ({shape}) never reached the CRM: {flat}"
    assert any(fragment in r.url.path for r in sent), [r.url.path for r in sent]
    if shape == "staff":
        assert all(r.headers.get(IDENTITY) == STAFF_ID for r in sent), [dict(r.headers) for r in sent]
    else:
        assert all(IDENTITY not in r.headers for r in sent)


@pytest.mark.parametrize("name", list(TOOLS))
def test_AC4_a_staff_read_that_omits_the_pair_entirely_also_reaches_its_route(mcp, crm, name):
    # What an agent that never mentions the pair would send (dispatch always adds it, so this is the floor).
    fragment, extra = TOOLS[name]
    reply = _call(mcp, name, dict(extra), STAFF)
    flat = _refusal_text(reply)
    assert "scope_required" not in flat, flat
    assert any(fragment in r.url.path for r in _crm(crm)), flat


# ------------------------------------------------------------------ AC-5: the catalog stays UUID-first


@pytest.mark.parametrize("name", ["crm_complaints_list", "crm_projects_list"])
def test_AC5_query_stays_off_the_catalog_and_the_compiled_schema(mcp, name):
    """A complaint number or project code is found by the in-process `crm_complaints_find` /
    `crm_projects_find`; the MCP list tools keep the UUID-first contract (`test_no_freetext_query_on_data_list_tools`)."""
    spec = next(s for s in CATALOG if s.name == name)
    assert "query" not in spec.query_params
    body = {"jsonrpc": "2.0", "id": "1", "method": "tools/list", "params": {}}
    resp = mcp.post("/mcp", json=body, headers=BASE)
    assert resp.status_code == 200, resp.text
    text = resp.text
    if "text/event-stream" in resp.headers.get("content-type", ""):
        text = [ln[5:].strip() for ln in text.splitlines() if ln.startswith("data:")][-1]
    tools = {t["name"]: t for t in json.loads(text)["result"]["tools"]}
    assert "query" not in tools[name]["inputSchema"]["properties"]
