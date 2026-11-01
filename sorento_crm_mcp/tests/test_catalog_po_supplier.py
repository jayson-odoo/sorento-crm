"""SUPPLIER-ASK: the PO placed tool forwards `supplier_ids`.

`documentation/plans/chatbot/PLAN-supplier-ask-01nov.md` AC-3. The MCP server drops any
query param a spec does not declare, so an undeclared `supplier_ids` never reaches the route.
"""
from __future__ import annotations

from sorento_crm_mcp.catalog import CATALOG


def test_the_po_tool_declares_supplier_ids() -> None:
    spec = next(s for s in CATALOG if s.name == "crm_procurement_po_placed_list")
    assert "supplier_ids" in spec.query_params
    assert "supplier_ids" in spec.description
