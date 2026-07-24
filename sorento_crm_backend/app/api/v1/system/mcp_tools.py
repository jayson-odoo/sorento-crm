"""System-level MCP tool catalog read endpoints.

Pure catalog listing — tools carry no agent ownership (see
``app.services.mcp_access_service`` for why that model was removed).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.access import McpTool
from app.schemas.user import McpToolOut

router = APIRouter(prefix="/mcp-tools", tags=["mcp-tools"])


@router.get("", response_model=list[McpToolOut])
def list_mcp_tools(
    is_active: bool = Query(True, description="When true, exclude tools removed from the code catalog."),
    limit: int = Query(500, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> list[McpToolOut]:
    q = db.query(McpTool)
    if is_active:
        q = q.filter(McpTool.is_active.is_(True))
    rows = (
        q.order_by(McpTool.module_key.asc(), McpTool.tool_name.asc())
        .limit(limit)
        .all()
    )
    return [McpToolOut.model_validate(r) for r in rows]
