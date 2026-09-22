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
"""
from __future__ import annotations

from sorento_crm_mcp.catalog import CATALOG

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
