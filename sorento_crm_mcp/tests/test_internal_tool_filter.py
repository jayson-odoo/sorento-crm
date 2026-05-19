"""Tests for the `internal=True` ToolSpec filter introduced so admin / back-office
procurement tools stay out of the n8n agent's tool catalog by default. See
`sorento_crm_mcp/server.py:create_mcp_app` and `sorento_crm_mcp/catalog.py`.
"""
from __future__ import annotations

import pytest

from sorento_crm_mcp.catalog import CATALOG


_EXPECTED_INTERNAL = {
    "crm_procurement_packing_lists_list",
    "crm_procurement_packing_lists_get",
    "crm_procurement_spo_allocations_grouped_by_shipment",
    "crm_procurement_spo_allocations_grouped_by_spo",
    "crm_procurement_spo_allocations_list",
    "crm_procurement_spo_allocations_get",
    "crm_procurement_grn_list",
    "crm_procurement_grn_get",
    "crm_procurement_picking_lines_list",
}


def test_admin_procurement_tools_marked_internal():
    marked = {s.name for s in CATALOG if getattr(s, "internal", False)}
    missing = _EXPECTED_INTERNAL - marked
    assert not missing, f"expected internal=True on: {missing}"


def test_user_facing_incoming_stock_grn_is_not_internal():
    """`crm_incoming_stock_grn` is the user-facing alternative to the admin
    `crm_procurement_grn_list`. It must remain visible to the agent."""
    spec = next((s for s in CATALOG if s.name == "crm_incoming_stock_grn"), None)
    assert spec is not None
    assert not getattr(spec, "internal", False)


@pytest.mark.parametrize("name", sorted(_EXPECTED_INTERNAL))
def test_internal_tools_advertise_procurement_escalation(name):
    spec = next((s for s in CATALOG if s.name == name), None)
    assert spec is not None
    assert getattr(spec, "escalation_team", "") == "procurement"


def test_internal_tools_filter_skips_registration(monkeypatch):
    """`create_mcp_app` must skip registration for internal tools when
    `mcp_expose_internal=False` (the default)."""
    from sorento_crm_mcp import server as server_mod
    from sorento_crm_mcp.settings import Settings

    registered: list[str] = []

    class _StubFastMCP:
        def __init__(self, *a, **kw):
            pass

        def add_tool(self, _impl, name, description=""):
            registered.append(name)

    monkeypatch.setattr(server_mod, "FastMCP", _StubFastMCP)
    monkeypatch.setattr(server_mod, "_compile_tool", lambda spec: lambda *a, **kw: None)
    monkeypatch.setattr(server_mod, "register_user_guide_tools", lambda *a, **kw: None)
    # Stub discovery registration too — covered by its own test
    from sorento_crm_mcp import discovery as discovery_mod
    monkeypatch.setattr(discovery_mod, "register_discovery_tools", lambda *a, **kw: None)

    s = Settings(
        crm_base_url="http://test",
        external_api_key="k",
        mcp_response_envelope="v1",
        mcp_expose_internal=False,
    )
    server_mod.create_mcp_app(s)

    leaked = _EXPECTED_INTERNAL & set(registered)
    assert not leaked, f"internal tools leaked to agent: {leaked}"


def test_internal_tools_visible_when_flag_enabled(monkeypatch):
    """With MCP_EXPOSE_INTERNAL=1, internal tools register normally."""
    from sorento_crm_mcp import server as server_mod
    from sorento_crm_mcp.settings import Settings

    registered: list[str] = []

    class _StubFastMCP:
        def __init__(self, *a, **kw):
            pass

        def add_tool(self, _impl, name, description=""):
            registered.append(name)

    monkeypatch.setattr(server_mod, "FastMCP", _StubFastMCP)
    monkeypatch.setattr(server_mod, "_compile_tool", lambda spec: lambda *a, **kw: None)
    monkeypatch.setattr(server_mod, "register_user_guide_tools", lambda *a, **kw: None)
    from sorento_crm_mcp import discovery as discovery_mod
    monkeypatch.setattr(discovery_mod, "register_discovery_tools", lambda *a, **kw: None)

    s = Settings(
        crm_base_url="http://test",
        external_api_key="k",
        mcp_response_envelope="v1",
        mcp_expose_internal=True,
    )
    server_mod.create_mcp_app(s)

    visible = _EXPECTED_INTERNAL & set(registered)
    assert visible == _EXPECTED_INTERNAL, f"missing when expose=True: {_EXPECTED_INTERNAL - visible}"
