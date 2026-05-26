"""Verify the 6 access-gated promotion/attachment tools wire contact_id+space_id
through to the backend as query parameters, and that the catalog descriptions
advertise the new server-side contact resolution behaviour.

These tools rely on the backend resolving the contact's M2M access types from
``(respond_io_id, space_id)`` and applying a JSONB ``?|`` overlap filter against
the resource's ``access_levels``. The MCP layer's only job is to refuse calls
that omit either parameter and forward both to the CRM.
"""
from __future__ import annotations

import pytest

from sorento_crm_mcp import server as server_mod
from sorento_crm_mcp.access_guard import AccessDecision
from sorento_crm_mcp.catalog import CATALOG
from sorento_crm_mcp.server import (
    TOOL_REQUIRED_QUERY_HINTS,
    _compile_tool,
)

_ACCESS_GATED_TOOLS = {
    "crm_marketing_promotions_list",
    "crm_marketing_promotion_attachments_list",
    "crm_master_product_attachments_list",
}


class _CapturingClient:
    """Captures every backend call so the test can assert query params."""

    def __init__(self):
        self.calls: list[dict] = []

    async def get(self, path, path_params=None, query=None, tool_name=None):
        self.calls.append({
            "method": "GET",
            "path": path,
            "path_params": dict(path_params or {}),
            "query": dict(query or {}),
            "tool_name": tool_name,
        })
        # is_active=true keeps the promotion-activity precheck happy for tools
        # that fan out an extra GET before the main request.
        return '{"path":"%s","ok":true,"is_active":true}' % path

    async def post(self, *args, **kwargs):
        raise AssertionError("read-only tools must not POST")

    async def request(self, method, path, path_params=None, query=None, body=None, tool_name=None):
        self.calls.append({
            "method": method,
            "path": path,
            "path_params": dict(path_params or {}),
            "query": dict(query or {}),
            "tool_name": tool_name,
        })
        return '{"path":"%s","ok":true,"is_active":true}' % path


class _Settings:
    crm_base_url = "http://crm.local"
    external_api_key = "k"


class _RC:
    def __init__(self, client):
        self.lifespan_context = {"client": client, "settings": _Settings()}


class _Ctx:
    def __init__(self, client):
        self.request_context = _RC(client)


@pytest.fixture(autouse=True)
def _allow_access(monkeypatch):
    async def _allow(*_args, **_kwargs):
        return AccessDecision(allowed=True, decision="allow", agent_name="stub")

    monkeypatch.setattr(server_mod, "check_access", _allow)


def _spec(name: str):
    for s in CATALOG:
        if s.name == name:
            return s
    raise KeyError(name)


@pytest.mark.parametrize("tool_name", sorted(_ACCESS_GATED_TOOLS))
def test_tool_marks_contact_and_space_required(tool_name):
    """Server refuses to execute the tool unless both guard params are supplied."""
    hints = TOOL_REQUIRED_QUERY_HINTS.get(tool_name)
    assert hints is not None, f"{tool_name} must be in TOOL_REQUIRED_QUERY_HINTS"
    assert set(hints) == {"contact_id", "space_id"}, hints


@pytest.mark.parametrize("tool_name", sorted(_ACCESS_GATED_TOOLS))
def test_tool_accepts_contact_and_space_query_params(tool_name):
    """Catalog ToolSpec exposes contact_id and space_id as query params (so they
    are forwarded to the backend rather than swallowed as guard-only)."""
    spec = _spec(tool_name)
    assert "contact_id" in spec.query_params, spec
    assert "space_id" in spec.query_params, spec


@pytest.mark.parametrize("tool_name", sorted(_ACCESS_GATED_TOOLS))
def test_tool_description_mentions_access_resolution(tool_name):
    """Description must tell the agent that visibility is gated by the contact's
    access types (so the LLM picks the right inputs)."""
    spec = _spec(tool_name)
    blob = spec.description.lower()
    assert "access" in blob
    assert "contact_id" in blob and "space_id" in blob


_UUID = "11111111-1111-4111-8111-111111111111"


def _build_kwargs(spec):
    kwargs: dict[str, str] = {p: _UUID for p in spec.path_params}
    kwargs["contact_id"] = "respond-abc"
    kwargs["space_id"] = "space-123"
    return kwargs


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", sorted(_ACCESS_GATED_TOOLS))
async def test_tool_forwards_contact_and_space_to_backend(tool_name, monkeypatch):
    """contact_id / space_id supplied as guard params must end up in the forwarded
    query string so the backend can resolve the contact's access codes."""

    async def _allow(*_args, **_kwargs):
        return AccessDecision(allowed=True, decision="allow", agent_name="stub")

    monkeypatch.setattr("sorento_crm_mcp.server.check_access", _allow)
    spec = _spec(tool_name)
    fn = _compile_tool(spec)
    client = _CapturingClient()
    await fn(_Ctx(client), **_build_kwargs(spec))
    assert client.calls, "tool produced no backend call"
    # Some tools fan out a precheck call without guard params (e.g. the
    # promotion-activity check). The main call is the unique one that carries
    # contact_id/space_id in the forwarded query.
    forwarded = [c for c in client.calls if "contact_id" in c["query"]]
    assert forwarded, f"contact_id never forwarded; calls={client.calls!r}"
    primary = forwarded[-1]
    assert primary["query"].get("contact_id") == "respond-abc"
    assert primary["query"].get("space_id") == "space-123"


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", sorted(_ACCESS_GATED_TOOLS))
async def test_tool_errors_when_contact_or_space_blank(tool_name, monkeypatch):
    """Missing-required-query check rejects calls that omit either guard param."""

    async def _allow(*_args, **_kwargs):
        return AccessDecision(allowed=True, decision="allow", agent_name="stub")

    monkeypatch.setattr("sorento_crm_mcp.server.check_access", _allow)
    spec = _spec(tool_name)
    fn = _compile_tool(spec)
    client = _CapturingClient()

    kw_no_contact = _build_kwargs(spec)
    kw_no_contact["contact_id"] = ""
    with pytest.raises(ValueError) as exc_info:
        await fn(_Ctx(client), **kw_no_contact)
    assert "contact_id" in str(exc_info.value)

    kw_no_space = _build_kwargs(spec)
    kw_no_space["space_id"] = ""
    with pytest.raises(ValueError) as exc_info:
        await fn(_Ctx(client), **kw_no_space)
    assert "space_id" in str(exc_info.value)
