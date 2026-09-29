"""RED tests - MCP catalog params for the PO warehouse filter and the SPO sort.

`documentation/plans/chatbot/PLAN-po-spo-warehouse-29sep.md` section W2;
`documentation/plans/chatbot/po-spo-warehouse-29sep-acceptance-criteria.md` AC-14.

The MCP server drops any query param a spec does not declare (`server.py`, `query_params`),
so an undeclared `warehouse_ids` / `sort` / `dir` never reaches the backend route.
"""
from __future__ import annotations

from sorento_crm_mcp.catalog import CATALOG

PO_TOOL = "crm_procurement_po_placed_list"
SPO_TOOL = "crm_procurement_spo_allocations_last_receipt_list"


def _spec(name: str):
    return next(s for s in CATALOG if s.name == name)


def test_the_po_tool_declares_warehouse_ids() -> None:
    assert "warehouse_ids" in _spec(PO_TOOL).query_params


def test_the_po_tool_keeps_its_existing_params() -> None:
    params = _spec(PO_TOOL).query_params
    for name in ("product_ids", "sort", "dir"):
        assert name in params, name


def test_the_spo_tool_declares_sort_and_dir() -> None:
    params = _spec(SPO_TOOL).query_params
    assert "sort" in params
    assert "dir" in params


def test_the_spo_tool_keeps_its_existing_params() -> None:
    params = _spec(SPO_TOOL).query_params
    for name in ("product_ids", "warehouse_ids", "top_n"):
        assert name in params, name


def test_the_descriptions_name_the_new_params() -> None:
    assert "warehouse" in _spec(PO_TOOL).description.lower()
    spo = _spec(SPO_TOOL).description
    assert "sort" in spo.lower()
    assert "gr_quantity" in spo
