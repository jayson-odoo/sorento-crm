"""Dealer stock verdict - S2, the MCP catalog declaration (AC-1759, D20).

PLAN `documentation/plans/chatbot/PLAN-chatbot-dealer-stock-verdict.md` "The presenter (S2)"
+ "Who validates (D25)": "MCP catalog ToolSpec declares contract: param
`requested_quantities` in, key `needs_quantity` out; `sync_catalog` -> `mcp_tools`; never
validates." UAC AC-1759: `crm_inventory_stock_balance_list` lists `requested_quantities` as
a query param and the description tells the caller when to pass it.

Today the tool's `query_params` tuple carries only the scalar `requested_qty`
(`sorento_crm_mcp/catalog.py`, the `crm_inventory_stock_balance_list` ToolSpec) - there is
no `requested_quantities` entry at all, so `test_catalog_declares_requested_quantities_param`
is red on a plain membership check, not a fixture bug.

Review round 3 (live pass, `dealer-stock-verdict.EVIDENCE.md`, Root cause A) adds the
coverage gap the evidence named directly: these two tests above only ever asserted the
`ToolSpec.query_params` tuple and description text, never exercised the COMPILED tool
with a live `requested_quantities` value. `server.py::_compile_tool` types every query
param off one fixed `str | int | float | bool | list[str]` union with no dict case
(`_scalar_union`), so a native-dict call fails Pydantic validation with 5 errors before
the backend is ever reached - the JSON-string form is the only one that survives.
"""
from __future__ import annotations

import json

import pytest

from sorento_crm_mcp.catalog import CATALOG
from sorento_crm_mcp.server import _compile_tool, create_mcp_app
from sorento_crm_mcp.settings import Settings

TOOL = "crm_inventory_stock_balance_list"


def spec():
    matches = [s for s in CATALOG if s.name == TOOL]
    assert len(matches) == 1, f"expected exactly one {TOOL} entry in CATALOG"
    return matches[0]


def test_catalog_declares_requested_quantities_param():
    """AC-1759. The per-product map, alongside the existing scalar (D20: the map
    wins per product, the scalar fills the rest - both must exist side by side)."""
    s = spec()
    assert "requested_quantities" in s.query_params
    assert "requested_qty" in s.query_params, "the scalar stays (D20), not replaced"


def test_catalog_description_tells_the_caller_when_to_pass_requested_quantities():
    """AC-1759. Without the instruction the planner has the slot and never fills
    it - the same rationale `test_catalog_requested_qty` already pins for the
    scalar (`tests/test_presenters_stock.py`)."""
    description = spec().description.lower()
    assert "requested_quantities" in description
    # Distinguishes it from the scalar's own doc line: the map answers "which
    # product gets which quantity" for MORE THAN ONE product in the same call.
    assert "product" in description


# --------------------------------------------------------------------------- #
# Review round 3 (live pass): the COMPILED tool, not just the ToolSpec.
# --------------------------------------------------------------------------- #


class _FakeSettings:
    crm_base_url = "http://crm.local"
    external_api_key = "test-key"


class _CapturingClient:
    """Records the query the compiled tool actually sends to the backend (same
    pattern as `test_growth_r1_opt_in_defaults.py::_CapturingClient`)."""

    def __init__(self):
        self.query = None

    async def get(self, path, path_params=None, query=None, tool_name=None):
        return await self.request("GET", path, path_params, query, None, tool_name)

    async def request(self, method, path, path_params=None, query=None, body=None, tool_name=None):
        self.query = dict(query or {})
        return json.dumps(
            {"data": [], "pagination": {"total": 0, "page": 1, "limit": 10}, "empty": True}
        )


class _FakeCtx:
    def __init__(self, client):
        self.request_context = type(
            "_RC",
            (),
            {"lifespan_context": {"client": client, "settings": _FakeSettings()}},
        )()


@pytest.mark.asyncio
async def test_requested_quantities_as_a_json_string_reaches_the_backend_unchanged():
    """The contract this fix pins: the CRM lane (`lanes/business/fetch.py`) must send
    `requested_quantities` as a compact JSON STRING, and it crosses this tool's
    normalization (`_normalize_query_value` passes a plain string through verbatim,
    `server.py`) to reach the backend query byte-identical - the backend route parses it
    itself (`parse_requested_quantities`, `Optional[str]`)."""
    fn = _compile_tool(spec())
    client = _CapturingClient()
    raw = '{"00000000-0000-0000-0000-0000000000a1":5,"00000000-0000-0000-0000-0000000000a2":60}'

    await fn(
        _FakeCtx(client),  # type: ignore[arg-type]
        contact_id="1",
        space_id="s",
        requested_quantities=raw,
    )

    assert client.query is not None
    assert client.query["requested_quantities"] == raw


@pytest.mark.asyncio
async def test_requested_quantities_as_a_native_dict_is_rejected_by_the_schema():
    """Root cause A, reproduced at the boundary that actually fails in production: a
    native dict for `requested_quantities` fails Pydantic validation before the tool
    body ever runs, because the compiled signature types every query param off ONE
    fixed `str | int | float | bool | list[str]` union with no dict case
    (`server.py::_compile_tool`, `_scalar_union`). This is why the string form is the
    contract, not a style preference - a dict-valued call from the parser/lane never
    reaches the backend at all, and the caller sees a `ToolError`, not a 400."""
    from mcp.server.fastmcp.exceptions import ToolError

    app = create_mcp_app(Settings(CRM_BASE_URL="http://crm.local", EXTERNAL_API_KEY="k"))

    with pytest.raises(ToolError) as excinfo:
        await app.call_tool(
            TOOL,
            {
                "contact_id": "1",
                "space_id": "s",
                "requested_quantities": {"00000000-0000-0000-0000-0000000000a1": 5},
            },
        )

    assert "validation error" in str(excinfo.value).lower()
