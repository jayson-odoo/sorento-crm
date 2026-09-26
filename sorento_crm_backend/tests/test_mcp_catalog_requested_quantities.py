"""Dealer stock verdict - S2, backend half of AC-1759: `sync_catalog` seeds the new
`requested_quantities` param declaration into `mcp_tools`.

PLAN `documentation/plans/chatbot/PLAN-chatbot-dealer-stock-verdict.md` "Who validates
(D25)": the MCP `ToolSpec` DECLARES the contract; `sync_catalog` copies the spec's
`description` verbatim into `mcp_tools.description` (`app/services/mcp_tool_registry_service.
sync_catalog`) - there is no separate `query_params` column on `McpTool`
(`app/models/access.py::McpTool`), so the description text IS how the declaration reaches
the persisted catalog row an admin reads.

Copies the fixture/import pattern of the existing real-catalog sync test
(`tests/test_mcp_catalog_ideation.py`): Postgres only (`tests/_pg_fixture.blank_session`),
the sys.path shim for the sibling `sorento_crm_mcp` package (not a backend dependency, see
that file's own comment), `SORENTO_ENV_FILE=.env.ci-tests` -> `sorento_ai_automation_rearch`.

Red today because the ToolSpec itself has no `requested_quantities` param yet (S2, MCP
side) - the synced description will not mention it until that lands, so the membership
assertion below fails for that reason, not a fixture bug.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from tests._pg_fixture import blank_session

# The MCP server is a SIBLING package in this monorepo, not a backend dependency - see
# `tests/test_mcp_catalog_ideation.py` for the full rationale.
if importlib.util.find_spec("sorento_crm_mcp") is None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "sorento_crm_mcp"))

TOOL = "crm_inventory_stock_balance_list"


def test_sync_catalog_writes_requested_quantities_into_mcp_tools_description():
    from app.models.access import McpTool
    from app.services.mcp_tool_registry_service import sync_catalog

    with blank_session() as db:
        sync_catalog(db)
        db.commit()

        row = db.query(McpTool).filter(McpTool.tool_name == TOOL).one()
        assert row.is_active is True
        assert "requested_quantities" in (row.description or "").lower()
