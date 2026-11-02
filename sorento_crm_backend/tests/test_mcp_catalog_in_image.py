"""ASSISTANT-CATALOG-500: the backend reads the MCP tool catalog from inside its own image.

Production, 2 Nov 2026: `POST /api/v1/system/ai-assistant/chat` returned 500 on every panel
question that reached tool pick, with
`FileNotFoundError: '/sorento_crm_mcp/sorento_crm_mcp/catalog.py'`. The backend image is built
with `context: ./sorento_crm_backend` and copied to `/app`, so the monorepo's
`sorento_crm_mcp/` is not in it and `mcp` is not in `requirements.txt`. The old
`_load_catalog_specs` climbed `Path(__file__).parents[3]` (which is `/` in the image) to read it.
In a checkout and in CI's test job the file is there, which is why no test saw it.

The first test rebuilds the image's view: the `sorento_crm_mcp` package cannot be imported and
the service module lives at `/app/app/services/`, so any read outside the backend fails exactly
as it did in production.

The copy guard pins the backend's verbatim copy to the MCP file. The MCP package stays the
source of truth; the copy only exists so the image has it.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

import app.services.mcp_tool_capability_service as capability_service
from app.services import tool_keyword_rank

BACKEND_ROOT = Path(__file__).resolve().parents[1]
MCP_PACKAGE_DIR = BACKEND_ROOT.parent / "sorento_crm_mcp"
MCP_CATALOG = MCP_PACKAGE_DIR / "sorento_crm_mcp" / "catalog.py"
BACKEND_COPY = BACKEND_ROOT / "app" / "services" / "mcp_catalog_copy.py"

# Where the module sits inside the deployed image (Dockerfile: WORKDIR /app, COPY . .).
IMAGE_MODULE_PATH = "/app/app/services/mcp_tool_capability_service.py"


@pytest.fixture
def image_layout(monkeypatch):
    """The backend as the production container sees it: no MCP package, no monorepo above /app."""
    monkeypatch.setitem(sys.modules, "sorento_crm_mcp", None)
    monkeypatch.setitem(sys.modules, "sorento_crm_mcp.catalog", None)
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(capability_service, "__file__", IMAGE_MODULE_PATH)
    tool_keyword_rank._tool_texts.cache_clear()
    yield
    tool_keyword_rank._tool_texts.cache_clear()


def test_the_catalog_is_the_backend_copy():
    """Pins the mechanism: the image-layout tests relocate `__file__` at call time, so a path
    climb evaluated at import time (a module-level constant) would slip past them."""
    from app.services import mcp_catalog_copy

    assert capability_service._load_catalog_specs() is mcp_catalog_copy.CATALOG


def test_capability_documents_build_in_the_image_layout(image_layout):
    """The panel's tool pick, the capability summary and the embedding backfill all start here."""
    docs = capability_service.build_capability_documents(include_planned=False)

    names = {d.source_key for d in docs}
    assert "crm_master_products_list" in names
    assert "crm_inventory_stock_balance_list" in names
    assert len(names) > 50, f"only {len(names)} tools built from the catalog"


def test_live_capability_summary_builds_in_the_image_layout(image_layout):
    """`/system/tool-capabilities/summary` (MCP tool `crm_system_tool_capabilities_summary`)."""
    summary = capability_service.build_live_capability_summary(include_tools=True)

    assert summary["summary"]["total_tools"] > 50


def test_panel_keyword_ranking_works_in_the_image_layout(image_layout):
    """`_rag_select_tools` -> `rank_tools`: the exact chain that returned 500 in production."""
    picked = tool_keyword_rank.rank_tools("stock balance in the warehouse", [], 3)

    assert len(picked) == 3
    assert all(p["tool_name"] for p in picked)


def test_backend_catalog_copy_is_the_mcp_catalog_byte_for_byte():
    """The MCP package is the source of truth; the backend copy must never drift from it."""
    if not MCP_PACKAGE_DIR.is_dir():
        pytest.skip("no sorento_crm_mcp/ next to the backend (inside the image); the checkout runs this guard")
    assert BACKEND_COPY.is_file(), f"missing {BACKEND_COPY.relative_to(BACKEND_ROOT.parent)}"
    assert BACKEND_COPY.read_bytes() == MCP_CATALOG.read_bytes(), (
        "the backend's copy of the MCP catalog drifted. From the repo root run:\n"
        "  cp sorento_crm_mcp/sorento_crm_mcp/catalog.py sorento_crm_backend/app/services/mcp_catalog_copy.py"
    )


def test_tool_pick_that_raises_degrades_to_no_tools(monkeypatch, caplog):
    """A failing tool ranking must not turn the whole chat turn into a 500: no tools, logged."""
    from app.services.ai_assistant_service import AIAssistantChatService

    def _boom(*_a, **_k):
        raise FileNotFoundError("/sorento_crm_mcp/sorento_crm_mcp/catalog.py")

    monkeypatch.setattr(tool_keyword_rank, "rank_tools", _boom)
    service = AIAssistantChatService.__new__(AIAssistantChatService)

    with caplog.at_level(logging.ERROR, logger="app.services.ai_assistant_service"):
        selected, sources = service._rag_select_tools(
            standalone_query="Intent: record_action\nCancel order SO-1", enabled_tools=[], top_k=3
        )

    assert (selected, sources) == ([], [])
    assert any(r.exc_info for r in caplog.records), "the failure must be logged with its stack"
