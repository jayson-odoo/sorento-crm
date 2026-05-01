"""System-level MCP tool catalog read endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.user import McpToolOut
from app.services.access_agent_mcp_tool_service import list_picker_tools

router = APIRouter(prefix="/mcp-tools", tags=["mcp-tools"])


@router.get("", response_model=list[McpToolOut])
def list_mcp_tools(
    is_active: bool = Query(True, description="When true, exclude tools removed from the code catalog."),
    limit: int = Query(500, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> list[McpToolOut]:
    rows = list_picker_tools(db, only_active=is_active, limit=limit)
    return [McpToolOut(**r) for r in rows]
