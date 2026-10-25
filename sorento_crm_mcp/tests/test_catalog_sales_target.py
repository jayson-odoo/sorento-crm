"""Phase 2 RED tests - MCP catalog entry for sales target progress (lane SALES-TARGET-CHAT, slice 1).

`documentation/plans/sales/sales-target-chat-25oct-acceptance-criteria.md` T3-1. Written before the
ToolSpec exists: `next(...)` raises StopIteration for the missing tool, the module imports fine.
Run with `PYTHONPATH=$PWD` from `sorento_crm_mcp/`.
"""
from __future__ import annotations

import inspect

from sorento_crm_mcp.catalog import CATALOG
from sorento_crm_mcp.presenters import PRESENTER_TOOLS
from sorento_crm_mcp.server import _compile_tool

TOOL = "crm_sales_target_progress"

REQUIRED_QUERY_PARAMS = ("contact_id", "space_id", "date_from", "date_to", "customer_ids")


def _spec():
    return next(s for s in CATALOG if s.name == TOOL)


def test_sales_target_tool_spec() -> None:
    spec = _spec()
    assert spec.path == "/api/v1/sales/target-progress", spec.path
    assert spec.method == "GET", spec.method
    assert spec.restricted_fields == (("sales.sales_target", "Sales target"),), spec.restricted_fields
    missing = [p for p in REQUIRED_QUERY_PARAMS if p not in spec.query_params]
    assert not missing, f"missing query params {missing} (has {spec.query_params})"


def test_sales_target_is_a_presenter_tool_and_compiles() -> None:
    spec = _spec()
    assert TOOL in PRESENTER_TOOLS, sorted(PRESENTER_TOOLS)
    params = inspect.signature(_compile_tool(spec)).parameters
    assert "view" in params, sorted(params)
