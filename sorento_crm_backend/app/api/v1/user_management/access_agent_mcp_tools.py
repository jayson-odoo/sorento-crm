"""Per-agent MCP tool ownership routes (Phase 2).

Mounted separately from the main access_agents router so this sub-router can
use the API-key-friendly guard (`require_module_enabled_with_api_key`) while
the rest of user-management keeps its JWT-only guard.

Auth accepts either JWT (admin UI) or X-API-Key (n8n / admin scripts).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_or_api_key
from app.schemas.user import (
    AccessAgentMcpToolBindingsUpdate,
    AccessAgentMcpToolsUpdate,
    McpToolBindingOut,
    McpToolForAgentOut,
)
from app.services.access_agent_mcp_tool_service import (
    list_tool_bindings_for_agent,
    list_tools_for_agent,
    set_tool_bindings_for_agent,
    set_tools_for_agent,
)
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()


@router.get("/{agent_id}/mcp-tools", response_model=list[McpToolForAgentOut])
def get_access_agent_mcp_tools(
    agent_id: str,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_or_api_key),
) -> list[McpToolForAgentOut]:
    """Return active MCP tools owned by this access agent (Phase 2)."""
    validate_uuid_path(agent_id, resource="Access Agent")
    rows = list_tools_for_agent(db, agent_id)
    return [McpToolForAgentOut.model_validate(r) for r in rows]


@router.put("/{agent_id}/mcp-tools", response_model=list[McpToolForAgentOut])
def set_access_agent_mcp_tools(
    agent_id: str,
    payload: AccessAgentMcpToolsUpdate,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_or_api_key),
) -> list[McpToolForAgentOut]:
    """Replace this agent's legacy (team_id NULL) MCP tool ownership set."""
    validate_uuid_path(agent_id, resource="Access Agent")
    set_tools_for_agent(db, agent_id, list(payload.tool_ids))
    db.commit()
    rows = list_tools_for_agent(db, agent_id)
    return [McpToolForAgentOut.model_validate(r) for r in rows]


@router.get(
    "/{agent_id}/mcp-tool-bindings", response_model=list[McpToolBindingOut]
)
def get_access_agent_mcp_tool_bindings(
    agent_id: str,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_or_api_key),
) -> list[McpToolBindingOut]:
    validate_uuid_path(agent_id, resource="Access Agent")
    rows = list_tool_bindings_for_agent(db, agent_id)
    return [McpToolBindingOut.model_validate(r) for r in rows]


@router.put(
    "/{agent_id}/mcp-tool-bindings", response_model=list[McpToolBindingOut]
)
def set_access_agent_mcp_tool_bindings(
    agent_id: str,
    payload: AccessAgentMcpToolBindingsUpdate,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user_or_api_key),
) -> list[McpToolBindingOut]:
    """Replace this agent's full tool/team binding set in one transaction."""
    validate_uuid_path(agent_id, resource="Access Agent")
    set_tool_bindings_for_agent(
        db,
        agent_id,
        [b.model_dump() for b in payload.bindings],
    )
    db.commit()
    rows = list_tool_bindings_for_agent(db, agent_id)
    return [McpToolBindingOut.model_validate(r) for r in rows]
