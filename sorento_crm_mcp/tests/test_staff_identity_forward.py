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


def test_ac3_a_write_tool_never_carries_it(mcp, crm):
    # record_actions.py:89 (hand-written write) and a compiled catalog write
    _call(mcp, "crm_complaint_close", {"complaint_id": PROMO_ID}, STAFF)
    _call(mcp, "crm_it_support_ticket_create", {"contact_id": "", "space_id": "", "payload_json": "{}"}, STAFF)
    sent = _crm_requests(crm)
    assert sent, "fixture: the write tools must have reached the CRM"
    assert all(IDENTITY not in r.headers for r in sent), "AC-3: a write stays act-as"


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


def test_ac4_an_unscoped_tool_is_not_refused_for_want_of_an_id(mcp, crm):
    """The refusal is for company-scoped tools only (scope.is_scoped)."""
    headers = {**BASE, "X-MCP-Scope": "staff"}
    _call(mcp, "crm_forms_management_forms_list", {}, headers)
    assert _crm_requests(crm), "an unscoped read still goes ahead"
