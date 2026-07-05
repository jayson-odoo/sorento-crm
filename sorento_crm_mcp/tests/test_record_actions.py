"""Tests for the record-action write tools (crm_complaint_close /
crm_order_cancel / crm_purchase_request_approve / crm_purchase_request_reject).

Each handler wraps an existing CRM endpoint. We register the tools onto a fake
FastMCP, capture the handler callables, and drive them with a fake Context whose
lifespan client records the exact (method, path, path_params, body) it was asked
to send — proving the correct request is built from the tool args, that fixed
decision fields are injected, that a non-UUID id short-circuits without any HTTP
call, and that backend errors propagate verbatim.
"""
from __future__ import annotations

import json

import pytest

from sorento_crm_mcp.catalog import CATALOG
from sorento_crm_mcp.record_actions import (
    RECORD_ACTION_TOOLS,
    register_record_action_tools,
)

_UUID = "2654ab89-2449-4910-84bf-f718ccc661d2"


class _FakeSettings:
    crm_base_url = "http://crm.local"
    external_api_key = "test-key"


class _RecordingClient:
    """Captures the request the handler builds and returns a canned response."""

    def __init__(self, response: str = '{"ok": true}') -> None:
        self.calls: list[dict] = []
        self._response = response

    async def request(self, method, path, path_params=None, query=None, body=None, tool_name=None):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "path_params": path_params,
                "body": body,
                "tool_name": tool_name,
            }
        )
        return self._response


class _FakeRC:
    def __init__(self, client):
        self.lifespan_context = {"client": client, "settings": _FakeSettings()}


class _FakeCtx:
    def __init__(self, client):
        self.request_context = _FakeRC(client)


class _FakeMCP:
    def __init__(self) -> None:
        self.tools: dict = {}
        self.descriptions: dict = {}

    def add_tool(self, fn, name=None, description=None):
        self.tools[name] = fn
        self.descriptions[name] = description


def _register(response: str = '{"ok": true}'):
    mcp = _FakeMCP()
    register_record_action_tools(mcp, _FakeSettings())
    client = _RecordingClient(response)
    ctx = _FakeCtx(client)
    return mcp, ctx, client


def test_registers_all_four_tools_with_descriptions():
    mcp, _, _ = _register()
    for name in RECORD_ACTION_TOOLS:
        assert name in mcp.tools
        # Description mirrors the shared catalog ToolSpec (single source of truth).
        spec = next(s for s in CATALOG if s.name == name)
        assert mcp.descriptions[name] == spec.description


async def test_complaint_close_builds_post_with_note():
    mcp, ctx, client = _register()
    out = await mcp.tools["crm_complaint_close"](ctx, complaint_id=_UUID, note="resolved")
    assert out == '{"ok": true}'
    (call,) = client.calls
    assert call["method"] == "POST"
    assert call["path"] == "/api/v1/complaints-management/complaints/{complaint_id}/close"
    assert call["path_params"] == {"complaint_id": _UUID}
    assert call["body"] == {"note": "resolved"}
    assert call["tool_name"] == "crm_complaint_close"


async def test_complaint_close_omits_note_when_absent():
    mcp, ctx, client = _register()
    await mcp.tools["crm_complaint_close"](ctx, complaint_id=_UUID)
    (call,) = client.calls
    assert call["body"] == {}


async def test_order_cancel_posts_to_dedicated_cancel_endpoint():
    mcp, ctx, client = _register()
    await mcp.tools["crm_order_cancel"](ctx, order_id=_UUID, reason="changed mind")
    (call,) = client.calls
    assert call["method"] == "POST"
    assert call["path"] == "/api/v1/order-management/orders/{order_id}/cancel"
    assert call["path_params"] == {"order_id": _UUID}
    # is_cancelled is set server-side; the tool only forwards the optional reason.
    assert call["body"] == {"reason": "changed mind"}


async def test_order_cancel_without_reason_sends_empty_body():
    mcp, ctx, client = _register()
    await mcp.tools["crm_order_cancel"](ctx, order_id=_UUID)
    (call,) = client.calls
    assert call["body"] == {}


async def test_pr_approve_injects_approved_action():
    mcp, ctx, client = _register()
    await mcp.tools["crm_purchase_request_approve"](
        ctx, purchase_request_id=_UUID, comments="ok"
    )
    (call,) = client.calls
    assert call["method"] == "POST"
    assert call["path"] == (
        "/api/v1/procurement/purchase-requests/{purchase_request_id}/approval-decision"
    )
    assert call["path_params"] == {"purchase_request_id": _UUID}
    assert call["body"] == {"action": "approved", "comments": "ok"}


async def test_pr_reject_injects_rejected_action_and_maps_reason():
    mcp, ctx, client = _register()
    await mcp.tools["crm_purchase_request_reject"](
        ctx, purchase_request_id=_UUID, reason="over budget"
    )
    (call,) = client.calls
    assert call["method"] == "POST"
    assert call["body"] == {"action": "rejected", "comments": "over budget"}


@pytest.mark.parametrize(
    "tool_name,kwargs",
    [
        ("crm_complaint_close", {"complaint_id": "C-1042"}),
        ("crm_order_cancel", {"order_id": "not-a-uuid"}),
        ("crm_purchase_request_approve", {"purchase_request_id": ""}),
        ("crm_purchase_request_reject", {"purchase_request_id": "PR-88"}),
    ],
)
async def test_non_uuid_id_short_circuits_without_http_call(tool_name, kwargs):
    mcp, ctx, client = _register()
    out = await mcp.tools[tool_name](ctx, **kwargs)
    payload = json.loads(out)
    assert payload["code"] == "INVALID_IDENTIFIER_FORMAT"
    assert client.calls == []  # never hit the backend with a bad id


async def test_backend_error_propagates_verbatim():
    err = '{"detail": "not pending approval", "status_code": 400}'
    mcp, ctx, client = _register(response=err)
    out = await mcp.tools["crm_purchase_request_approve"](ctx, purchase_request_id=_UUID)
    assert out == err
    assert len(client.calls) == 1
