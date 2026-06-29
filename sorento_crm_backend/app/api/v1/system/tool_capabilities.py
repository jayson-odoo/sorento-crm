"""Dynamic MCP capability summary endpoint.

Builds a live summary from MCP catalog + tool intents so callers can answer:
"What can you do?" with up-to-date capabilities.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_external_api_user
from app.services.mcp_tool_capability_service import (
    build_live_capability_summary,
    build_novice_capability_overview,
)

router = APIRouter(prefix="/tool-capabilities")


@router.get("/summary")
def get_tool_capabilities_summary(
    include_tools: bool = Query(
        True,
        description="Whether to include full tool list under each group; false returns counts/categories only.",
    ),
    current_user: dict[str, Any] = Depends(get_external_api_user),
):
    """Return dynamic capability summary grouped into general enquiries vs form submissions."""
    _ = current_user  # auth dependency for external API key / user scope
    return build_live_capability_summary(include_tools=include_tools)


@router.get("/overview")
def get_tool_capabilities_overview(
    current_user: dict[str, Any] = Depends(get_external_api_user),
):
    """Return a novice-friendly capability overview.

    Enrichment over `/summary`: drops admin/internal + skip-tools, maps machine
    category codes to friendly module names, attaches example questions, and
    exposes NO tool slugs / UUIDs / raw category codes / API paths. This is the
    deterministic source the AI assistant answers "what can you do?" from.
    """
    _ = current_user  # auth dependency for external API key / user scope
    return build_novice_capability_overview()

