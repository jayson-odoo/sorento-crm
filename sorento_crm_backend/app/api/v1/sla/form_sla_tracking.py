"""Form SLA tracking + manual escalate (TCK-28).

- GET  /form-sla-tracking            -> active stage row(s) for an entity (detail page)
- POST /form-sla-tracking/{id}/escalate -> manual force-escalate to next tier

Manual escalate is gated by the `sla.form.escalate` permission (seeded + granted
to all roles in migration 235).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.models.sla import ConversationSLATracking
from app.models.user import User
from app.services.form_sla_service import (
    FormSLAOrchestrator,
    FormEscalationBlocked,
    FORM_SLA_TYPES,
)

router = APIRouter()


def _assignee_name(db: Session, user_id: Optional[str]) -> Optional[str]:
    if not user_id:
        return None
    u = db.query(User).filter(User.id == user_id).first()
    return (u.name or u.email) if u else None


def _serialize(db: Session, t: ConversationSLATracking) -> dict:
    return {
        "tracking_id": str(t.id),
        "current_tier": t.current_tier,
        "due_at": t.due_at,
        "due_at_resolution": t.due_at_resolution,
        "is_resolved": bool(t.is_resolved),
        "assigned_to_id": t.assigned_to_id,
        "assigned_to_name": _assignee_name(db, t.assigned_to_id),
        "source_entity_type": t.source_entity_type,
        "source_entity_id": t.source_entity_id,
        "escalation_reason": t.escalation_reason,
    }


@router.get("")
async def get_form_tracking(
    source_entity_type: str = Query(...),
    source_entity_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Active (unresolved) form-SLA stage rows for an entity, newest first."""
    if source_entity_type not in FORM_SLA_TYPES:
        raise HTTPException(status_code=422, detail="Not a form SLA entity type.")
    rows = (
        db.query(ConversationSLATracking)
        .filter(
            ConversationSLATracking.source_entity_type == source_entity_type,
            ConversationSLATracking.source_entity_id == str(source_entity_id),
            ConversationSLATracking.is_resolved.is_(False),
        )
        .order_by(ConversationSLATracking.initiated_at.desc())
        .all()
    )
    return {"data": [_serialize(db, t) for t in rows]}


class _EscalateRequest(BaseModel):
    reason: str


@router.post("/{tracking_id}/escalate")
async def escalate_form_tracking(
    tracking_id: str,
    payload: _EscalateRequest,
    current_user: dict = Depends(require_permission("sla.form.escalate")),
    db: Session = Depends(get_db),
):
    """Manually force-escalate a form-SLA stage to the next tier (pre-breach)."""
    reason = (payload.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=422, detail="A reason is required to escalate.")
    try:
        tracker = FormSLAOrchestrator(db).escalate_form_tracking(
            tracking_id, reason=reason, actor_user_id=current_user["id"]
        )
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SLA tracking not found.")
    except FormEscalationBlocked as exc:
        raise HTTPException(status_code=422, detail=exc.message)
    return _serialize(db, tracker)
