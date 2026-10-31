"""AGENTIC-UNIFY PR 1, MCP half: AC-2, AC-3, AC-4.

The staff identity (`X-MCP-Staff-User`, sent by the CRM backend's panel client) must reach the
CRM as `X-Staff-User` on every request the MCP server makes while serving a staff-marked READ.

These tests go through the REAL MCP request path: `create_http_app` served by Starlette's
TestClient (lifespan live), a JSON-RPC `tools/call` over HTTP with real headers, the real
FastMCP request context, the real compiled tool and the real `CRMClient`. Only the network is
mocked, at the httpx transport, so the header asserted is the one that would hit the CRM.
"""
from __future__ import annotations

import json

import httpx
import pytest
from starlette.testclient import TestClient

from sorento_crm_mcp import http_client
from sorento_crm_mcp.server import create_http_app
from sorento_crm_mcp.settings import Settings

from _token_source import FakeBackend

TOKEN = "x" * 40
STAFF_ID = "11111111-1111-4111-8111-111111111111"
PROMO_ID = "22222222-2222-4222-8222-222222222222"
PRODUCT_ID = "33333333-3333-4333-8333-333333333333"
ATTACHMENT_TYPE = "44444444-4444-4444-8444-444444444444"
IDENTITY = "x-staff-user"

BASE = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json",
        "Authorization": f"Bearer {TOKEN}"}
STAFF = {**BASE, "X-MCP-Scope": "staff", "X-MCP-Staff-User": STAFF_ID}


def _crm_answer(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/master-data/products"):
        return httpx.Response(200, json={"data": [{"id": PRODUCT_ID, "product_code": "ZZT-1"}], "total": 1})
    if "/marketing/promotions/" in path:
        return httpx.Response(200, json={"id": PROMO_ID, "is_active": True, "name": "ZZT promo"})
    return httpx.Response(200, json={"data": [], "total": 0})


@pytest.fixture
def crm(monkeypatch):
    """Every request the MCP server sends to the CRM, captured at the httpx transport."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _crm_answer(request)

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


def _call(mcp, name, arguments, headers) -> str:
    body = {"jsonrpc": "2.0", "id": "1", "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    resp = mcp.post("/mcp", json=body, headers=headers)
    assert resp.status_code == 200, resp.text
    text = resp.text
    if "text/event-stream" in resp.headers.get("content-type", ""):
        text = [ln[5:].strip() for ln in text.splitlines() if ln.startswith("data:")][-1]
    return text


def _crm_requests(seen):
    # Routing hint: separate client (escalation_hint.py:46-53), no CRM data, no such backend route.
    return [r for r in seen if r.url.path.startswith("/api/") and r.url.path != "/api/v1/system/mcp-routing"]


# --- AC-2: staff-marked read tools forward the identity ----------------------------------------
def test_ac2_a_compiled_catalog_read_forwards_the_identity(mcp, crm):
    _call(mcp, "crm_inventory_stock_balance_list", {}, STAFF)
    sent = _crm_requests(crm)
    assert sent, "the tool must have reached the CRM"
    assert all(r.headers.get(IDENTITY) == STAFF_ID for r in sent), [dict(r.headers) for r in sent]


def test_ac2_a_nested_client_call_deep_in_the_tool_forwards_it_too(mcp, crm):
    """crm_master_products_list with attachment_type_ids fans out to /product-attachments from a
    helper that has no ctx argument (server.py `_fetch_all_child_rows`)."""
    _call(mcp, "crm_master_products_list", {"attachment_type_ids": ATTACHMENT_TYPE}, STAFF)
    sent = _crm_requests(crm)
    paths = [r.url.path for r in sent]
    assert any(p.endswith("/master-data/products") for p in paths)
    assert any(p.endswith("/master-data/product-attachments") for p in paths), (
        f"fixture: the child fan-out must have happened, saw {paths}"
    )
    assert all(r.headers.get(IDENTITY) == STAFF_ID for r in sent), "AC-2: every request, however deep"


def test_ac2_a_read_only_post_tool_forwards_it(mcp, crm):
    _call(mcp, "crm_lookup_resolve", {"set_key": "zzt", "raw": "x", "locale": "en", "contact_id": "", "space_id": ""}, STAFF)
    sent = _crm_requests(crm)
    assert sent and all(r.headers.get(IDENTITY) == STAFF_ID for r in sent)


# --- AC-3: never otherwise ----------------------------------------------------------------------
def test_ac3_a_call_that_is_not_staff_marked_never_carries_it(mcp, crm):
    headers = {**BASE, "X-MCP-Staff-User": STAFF_ID, "X-Staff-User": STAFF_ID}
    _call(mcp, "crm_inventory_stock_balance_list", {"contact_id": "900000008", "space_id": "364817"}, headers)
    sent = _crm_requests(crm)
    assert sent
    assert all(IDENTITY not in r.headers for r in sent), "AC-3: no staff marker, no identity header"


def test_ac3_a_caller_cannot_inject_the_header_through_its_own_request(mcp, crm):
    headers = {**BASE, "X-Staff-User": STAFF_ID}
    _call(mcp, "crm_inventory_stock_balance_list", {"contact_id": "900000008", "space_id": "364817"}, headers)
    assert all(IDENTITY not in r.headers for r in _crm_requests(crm))


def test_ac3_a_staff_marked_call_with_a_hostile_inbound_header_sends_only_the_real_id(mcp, crm):
    other = "99999999-9999-4999-8999-999999999999"
    headers = {**STAFF, "X-Staff-User": other}
    _call(mcp, "crm_inventory_stock_balance_list", {}, headers)
    sent = _crm_requests(crm)
    assert sent and all(r.headers.get(IDENTITY) == STAFF_ID for r in sent)


@pytest.mark.parametrize(
    "tool,args",
    [
        ("crm_complaint_close", {"complaint_id": PROMO_ID}),
        # a COMPILED catalog write: `message_id` is required, so the call reaches the CRM
        ("crm_it_support_ticket_create", {"payload_json": "{}", "message_id": "zzt-msg-1"}),
    ],
)
def test_ac3_a_write_tool_never_carries_it(mcp, crm, tool, args):
    """record_actions.py:89 (hand-written write) and a compiled catalog write, one each."""
    _call(mcp, tool, args, STAFF)
    sent = _crm_requests(crm)
    assert sent, f"fixture: {tool} must have reached the CRM"
    assert all(IDENTITY not in r.headers for r in sent), f"AC-3: {tool} is a write and stays act-as"


# --- AC-4: staff-marked read of a scoped tool with no staff id is refused ----------------------
def test_ac4_staff_marker_without_a_staff_id_is_refused_with_no_backend_request(mcp, crm):
    headers = {**BASE, "X-MCP-Scope": "staff"}
    out = _call(mcp, "crm_inventory_stock_balance_list", {}, headers)
    assert _crm_requests(crm) == [], "AC-4: no backend request"
    assert "scope_required" in out or "staff" in out.lower(), out


def test_ac4_a_blank_staff_id_is_refused_too(mcp, crm):
    headers = {**BASE, "X-MCP-Scope": "staff", "X-MCP-Staff-User": "   "}
    _call(mcp, "crm_inventory_stock_balance_list", {}, headers)
    assert _crm_requests(crm) == []


@pytest.mark.parametrize(
    "tool,args",
    [
        ("crm_forms_management_forms_list", {}),
        ("crm_system_tool_capabilities_summary", {}),
        ("crm_inventory_warehouses_list", {}),
    ],
)
def test_ac4_an_unscoped_read_with_no_staff_id_is_refused_too(mcp, crm, tool, args):
    """AC-4 (changed): any staff-marked read, scoped or not, with no id is refused."""
    headers = {**BASE, "X-MCP-Scope": "staff"}
    _call(mcp, tool, args, headers)
    assert _crm_requests(crm) == [], f"AC-4: {tool} reached the CRM without a staff id"


# --- AC-26: the bearer decides whether the staff markers survive --------------------------------
def _app_with(tokens, enforce):
    settings = Settings(CRM_BASE_URL="http://crm.local", EXTERNAL_API_KEY="k")
    return TestClient(create_http_app(settings, token_fetcher=FakeBackend(list(tokens), enforce=enforce)))


def test_ac26_enforce_off_with_the_bearer_keeps_the_markers_and_forwards_identity(crm):
    with _app_with([TOKEN], enforce=False) as client:
        _call(client, "crm_inventory_stock_balance_list", {}, STAFF)
    sent = _crm_requests(crm)
    assert sent and all(r.headers.get(IDENTITY) == STAFF_ID for r in sent)


def test_ac26_enforce_off_with_no_bearer_strips_the_markers_and_forwards_none(crm):
    """Today's rule, pinned: the call runs unauthenticated and as act-as (the backend client
    refuses to make it, AC-26 backend half)."""
    no_bearer = {k: v for k, v in STAFF.items() if k != "Authorization"}
    with _app_with([], enforce=False) as client:
        _call(client, "crm_inventory_warehouses_list", {}, no_bearer)
    sent = _crm_requests(crm)
    assert all(IDENTITY not in r.headers for r in sent)


def test_ac26_enforce_on_with_no_bearer_is_401(crm):
    no_bearer = {k: v for k, v in STAFF.items() if k != "Authorization"}
    body = {"jsonrpc": "2.0", "id": "1", "method": "tools/call",
            "params": {"name": "crm_inventory_stock_balance_list", "arguments": {}}}
    with _app_with([TOKEN], enforce=True) as client:
        resp = client.post("/mcp", json=body, headers=no_bearer)
    assert resp.status_code == 401
    assert _crm_requests(crm) == []


# --- a staff read with a blank contact pair on a hinted tool still forwards the identity ---------
def test_a_hinted_report_tool_with_a_blank_pair_forwards_the_identity(mcp, crm):
    args = {"contact_id": "", "space_id": "", "basis": "invoiced", "top_n": 5, "date_from": "2026-10-01",
            "date_to": "2026-10-31", "measure": "amount", "group_by": "customer"}
    _call(mcp, "crm_report_ask", args, STAFF)
    sent = [r for r in _crm_requests(crm) if r.url.path.endswith("/order-management/report-ask")]
    assert len(sent) == 1, "the blank pair must not stop the call before the CRM"
    assert sent[0].headers.get(IDENTITY) == STAFF_ID
