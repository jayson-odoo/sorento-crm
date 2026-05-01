"""MCP access guard endpoints (Phase 3)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.access import McpAccessLog
from app.schemas.user import McpAccessCheckIn, McpAccessCheckOut, McpAccessLogOut
from app.services.mcp_access_service import evaluate

router = APIRouter(prefix="/mcp-access", tags=["mcp-access"])


@router.post("/check", response_model=McpAccessCheckOut)
def check_access(
    payload: McpAccessCheckIn,
    db: Session = Depends(get_db),
) -> McpAccessCheckOut:
    decision = evaluate(
        db,
        tool_name=payload.tool_name,
        contact_id=payload.contact_id,
        space_id=payload.space_id,
    )
    db.commit()
    return McpAccessCheckOut(
        allowed=decision.allowed,
        decision=decision.decision,
        agent_name=decision.agent_name,
    )


@router.get("/log", response_model=list[McpAccessLogOut])
def list_access_log(
    limit: int = Query(100, ge=1, le=1000),
    decision: Optional[str] = Query(None),
    tool_name: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> list[McpAccessLogOut]:
    q = db.query(McpAccessLog).order_by(McpAccessLog.ts.desc())
    if decision:
        q = q.filter(McpAccessLog.decision == decision)
    if tool_name:
        q = q.filter(McpAccessLog.tool_name == tool_name)
    rows = q.limit(limit).all()
    return [McpAccessLogOut.model_validate(r) for r in rows]
