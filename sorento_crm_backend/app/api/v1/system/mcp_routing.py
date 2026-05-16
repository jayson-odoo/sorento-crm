"""Read-only routing lookup: MCP tool → eligible escalation teams/agents."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.mcp_routing_service import resolve_tool_routing

router = APIRouter(prefix="/mcp-routing", tags=["mcp-routing"])


class RoutingEntryOut(BaseModel):
    team_code: str
    team_name: str
    agent_code: str
    agent_name: str
    tier: Optional[int] = None


class RoutingResultOut(BaseModel):
    tool_name: str
    entries: list[RoutingEntryOut]
    primary: Optional[RoutingEntryOut] = None


@router.get("", response_model=RoutingResultOut)
def get_tool_routing(
    tool_name: str = Query(..., description="MCP tool name to resolve routing for"),
    db: Session = Depends(get_db),
) -> RoutingResultOut:
    result = resolve_tool_routing(db, tool_name)
    return RoutingResultOut(**result.to_payload())
