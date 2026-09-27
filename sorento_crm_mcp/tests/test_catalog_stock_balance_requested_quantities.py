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

Review round 3 (live pass, `dealer-stock-verdict.EVIDENCE.md`, Root cause A) added the
coverage gap the evidence named directly: the two tests above only ever asserted the
`ToolSpec.query_params` tuple and description text, never exercised the COMPILED tool
with a live `requested_quantities` value.

Review round 4 (Run 2 of the same evidence file) found round 3's reading of that gap was
half right. The backend does send a compact JSON STRING now, yet the live tool still failed
with `requested_quantities.str Input should be a valid string ... input_type=dict`, because
FastMCP's `pre_parse_json` (`mcp/server/fastmcp/utilities/func_metadata.py`) `json.loads`
ANY string argument whose declared annotation is not exactly `str` - the string is a dict
again by the time Pydantic sees it. So the caller cannot pick a shape that works while the
param is typed off `_scalar_union`: the string is pre-parsed into a dict and a dict has no
case in that union. `TOOL_OBJECT_QUERY_PARAMS` (`server.py`) now types this one param
`dict[str, int] | str`, and `_normalize_query_value` re-serializes a dict to the same
compact, key-sorted JSON string for the outbound query. Both shapes are therefore accepted
and both reach the backend as one identical string - which is what the tests below pin,
through `FastMCP.call_tool`, the entry that actually runs `pre_parse_json`.
"""
from __future__ import annotations

import contextlib
import json

import pytest
from mcp.server.lowlevel.server import request_ctx
from mcp.shared.context import RequestContext

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


# --------------------------------------------------------------------------- #
# Review round 4: through `FastMCP.call_tool`, the entry that runs pre_parse_json.
# --------------------------------------------------------------------------- #


@contextlib.contextmanager
def _request_context(client):
    """Make `FastMCP.call_tool` usable without a live server: the compiled tool
    reads its CRMClient off `ctx.request_context.lifespan_context`, which the
    lowlevel server normally sets from the lifespan. Setting the same contextvar
    by hand is what lets the test exercise the REAL validation path (argument
    pre-parsing + Pydantic) instead of calling the compiled function directly."""
    token = request_ctx.set(
        RequestContext(
            request_id=1,
            meta=None,
            session=None,  # type: ignore[arg-type]
            lifespan_context={"client": client, "settings": _FakeSettings()},
        )
    )
    try:
        yield
    finally:
        request_ctx.reset(token)


async def _call_through_fastmcp(value):
    app = create_mcp_app(Settings(CRM_BASE_URL="http://crm.local", EXTERNAL_API_KEY="k"))
    client = _CapturingClient()
    with _request_context(client):
        await app.call_tool(
            TOOL,
            {"contact_id": "1", "space_id": "s", "requested_quantities": value},
        )
    assert client.query is not None
    return client.query


_EXPECTED_QUERY = (
    '{"00000000-0000-0000-0000-0000000000a1":5,'
    '"00000000-0000-0000-0000-0000000000a2":60}'
)


@pytest.mark.asyncio
async def test_json_string_survives_fastmcp_preparse_and_reaches_the_backend():
    """Root cause A, at the boundary that actually failed in production. The lane
    (`lanes/business/fetch.py`) sends the compact JSON string; FastMCP pre-parses
    it into a dict before validation, so the param has to accept an object - and
    the value has to arrive at the backend as the string its route parses
    (`parse_requested_quantities`, `Optional[str]`)."""
    query = await _call_through_fastmcp(_EXPECTED_QUERY)

    assert query["requested_quantities"] == _EXPECTED_QUERY


@pytest.mark.asyncio
async def test_native_object_reaches_the_backend_as_the_same_json_string():
    """The other shape a caller can send (an n8n/LLM planner emitting a real JSON
    object, and the shape FastMCP hands over after pre-parsing a string) must be
    accepted too, and must normalize to the IDENTICAL query value - key order in
    the object is not allowed to change the string the backend receives."""
    query = await _call_through_fastmcp(
        {
            "00000000-0000-0000-0000-0000000000a2": 60,
            "00000000-0000-0000-0000-0000000000a1": 5,
        }
    )

    assert query["requested_quantities"] == _EXPECTED_QUERY
