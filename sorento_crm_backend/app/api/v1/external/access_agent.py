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
from app.schemas.access_agent import (
    AgentAccessCheckIn,
    AgentAccessCheckOut,
    AttributeAccess,
)
from app.services.field_access import check_attributes
from app.services.mcp_access_service import evaluate_agent

router = APIRouter()


@router.post("/check", response_model=AgentAccessCheckOut)
def check_agent_access(
    payload: AgentAccessCheckIn,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
) -> AgentAccessCheckOut:
    """Return whether ``(contact_id, space_id)`` may use ``agent`` (= ``AccessAgent.code``).

    Optionally also answers, per field, whether this contact may be TOLD it. Two
    different denials, because they need two different fixes: the agent was never
    assigned, or it was assigned and this field is not ticked on it.

    This is a preflight, not the enforcement point. ``/incoming-stock/list`` strips
    what the caller may not see whether or not anyone asked here first - forgetting
    this call must never be the difference between safe and leaking.
    """
    decision = evaluate_agent(
        db,
        agent_code=payload.agent,
        contact_id=payload.contact_id,
        space_id=payload.space_id,
    )
    db.commit()

    attributes = None
    all_allowed = None
    if payload.attributes:
        checked = check_attributes(
            db,
            resource=payload.resource or "incoming_stock",
            attributes=payload.attributes,
            contact_id=payload.contact_id,
            space_id=payload.space_id,
        )
        attributes = [AttributeAccess(**item) for item in checked["attributes"]]
        all_allowed = checked["all_allowed"]

    return AgentAccessCheckOut(
        allowed=decision.allowed,
        decision=decision.decision,
        agent_name=decision.agent_name,
        attributes=attributes,
        all_attributes_allowed=all_allowed,
    )
