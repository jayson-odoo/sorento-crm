"""AC-307 (D6): ideation is an MCP tool, not a special-cased chatbot lane.

`crm_ideation_turn` wraps `POST /api/v1/external/ideation/turn` and is synced into
`mcp_tools` the same way every other tool is - `sync_catalog` never gets a chatbot-
specific branch. Postgres only (`tests/_pg_fixture.blank_session`), never sqlite.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from tests._pg_fixture import blank_session

# The MCP server is a SIBLING package in this monorepo, not a backend dependency:
# `requirements.txt` does not carry it and CI installs nothing else, so without this the
# three tests below fail with `ModuleNotFoundError` on the runner while passing on a dev
# machine where `pip install -e ../sorento_crm_mcp` has been run. `catalog` and
# `module_loader` are stdlib-only, so the path is all they need. An already-installed
# copy wins, so a machine that HAS it reads exactly what it runs.
if importlib.util.find_spec("sorento_crm_mcp") is None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "sorento_crm_mcp"))


def _ideation_spec():
    from sorento_crm_mcp.catalog import CATALOG

    matches = [spec for spec in CATALOG if spec.name == "crm_ideation_turn"]
    assert len(matches) == 1, "expected exactly one crm_ideation_turn entry in CATALOG"
    return matches[0]


def test_catalog_has_ideation_tool():
    spec = _ideation_spec()
    assert spec.method == "POST"
    assert spec.path == "/api/v1/external/ideation/turn"
    assert spec.external is True


def test_sync_catalog_inserts_an_active_row_on_the_blank_schema():
    from app.models.access import McpTool
    from app.services.mcp_tool_registry_service import sync_catalog

    with blank_session() as db:
        sync_catalog(db)
        db.commit()

        row = db.query(McpTool).filter(McpTool.tool_name == "crm_ideation_turn").one()
        assert row.is_active is True
        assert row.http_method == "POST"
        assert row.http_path == "/api/v1/external/ideation/turn"


def test_sync_catalog_is_idempotent_for_the_ideation_tool():
    from app.models.access import McpTool
    from app.services.mcp_tool_registry_service import sync_catalog

    with blank_session() as db:
        sync_catalog(db)
        db.commit()
        sync_catalog(db)
        db.commit()

        rows = db.query(McpTool).filter(McpTool.tool_name == "crm_ideation_turn").all()
        assert len(rows) == 1
        assert rows[0].is_active is True
