"""External agent-access preflight endpoint.

Auth: X-API-Key (``get_external_api_user``). n8n calls this BEFORE invoking an
agent's MCP tools; per-tool ``contact_id`` / ``space_id`` guards were removed,
so verification now happens once here, at the top of the workflow.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.schemas.access_agent import AgentAccessCheckIn, AgentAccessCheckOut
from app.services.mcp_access_service import evaluate_agent

router = APIRouter()


@router.post("/check", response_model=AgentAccessCheckOut)
def check_agent_access(
    payload: AgentAccessCheckIn,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
) -> AgentAccessCheckOut:
    """Return whether ``(contact_id, space_id)`` may use ``agent`` (= ``AccessAgent.code``)."""
    decision = evaluate_agent(
        db,
        agent_code=payload.agent,
        contact_id=payload.contact_id,
        space_id=payload.space_id,
    )
    db.commit()
    return AgentAccessCheckOut(
        allowed=decision.allowed,
        decision=decision.decision,
        agent_name=decision.agent_name,
    )
