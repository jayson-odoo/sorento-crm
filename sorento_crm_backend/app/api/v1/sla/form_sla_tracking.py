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
from app.services.handling_lock_service import (
    HandlingLockService,
    is_handling_lock_enabled,
    _is_eligible,
    _actor_is_admin,
)

router = APIRouter()


def _assignee_name(db: Session, user_id: Optional[str]) -> Optional[str]:
    if not user_id:
        return None
    u = db.query(User).filter(User.id == user_id).first()
    return (u.name or u.email) if u else None


def _serialize(
    db: Session,
    t: ConversationSLATracking,
    viewer_user_id: Optional[str] = None,
    *,
    flag_enabled: Optional[bool] = None,
    viewer_is_admin: Optional[bool] = None,
) -> dict:
    """Serialize a form tracker for the FE resolver.

    ``flag_enabled`` (per-type) and ``viewer_is_admin`` (per-viewer) are
    request-constant; the list endpoint computes them ONCE and passes them in to
    avoid a per-row singleton read + role query. When omitted (single-row mutation
    responses) they're computed here.
    """
    out = {
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
        # Handling lock (PLAN-form-handling-lock). NULL handled_by_id = unclaimed.
        "handled_by_id": t.handled_by_id,
        "handled_by_name": _assignee_name(db, t.handled_by_id),
        "handled_at": t.handled_at,
        # Per-form feature flag; FE hides the whole lock UI when off.
        "flag_enabled": (
            flag_enabled
            if flag_enabled is not None
            else is_handling_lock_enabled(db, t.source_entity_type)
        ),
    }
    # Viewer-scoped inputs the FE state resolver needs but can't compute itself.
    if viewer_user_id:
        out["viewer_eligible"] = _is_eligible(db, t, viewer_user_id)
        out["viewer_is_admin"] = (
            viewer_is_admin
            if viewer_is_admin is not None
            else _actor_is_admin(db, viewer_user_id)
        )
    return out


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
    viewer_id = current_user.get("id")
    # Request-constant: all rows share source_entity_type; admin-ness is per-viewer.
    flag_enabled = is_handling_lock_enabled(db, source_entity_type)
    viewer_is_admin = _actor_is_admin(db, viewer_id) if viewer_id else False
    return {
        "data": [
            _serialize(
                db,
                t,
                viewer_user_id=viewer_id,
                flag_enabled=flag_enabled,
                viewer_is_admin=viewer_is_admin,
            )
            for t in rows
        ]
    }


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


class _TakeOverRequest(BaseModel):
    # Optimistic-concurrency guard: the holder the client believes is current.
    expected_handler_id: Optional[str] = None


@router.post("/{tracking_id}/claim")
async def claim_form_handling(
    tracking_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Claim the handling lock ("I'm handling this") on an escalated form tracker.

    Eligibility is team-chain membership (no RBAC slug); the service enforces flag-on +
    escalated + unresolved + eligible, then atomically claims (409 if already held).
    """
    tracker = HandlingLockService(db).claim_handling(tracking_id, current_user)
    return _serialize(db, tracker, viewer_user_id=current_user.get("id"))


@router.post("/{tracking_id}/take-over")
async def take_over_form_handling(
    tracking_id: str,
    payload: _TakeOverRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Take over the handling lock from the current holder (optimistic; 409 on mismatch)."""
    tracker = HandlingLockService(db).take_over_handling(
        tracking_id, current_user, payload.expected_handler_id
    )
    out = _serialize(db, tracker, viewer_user_id=current_user.get("id"))
    out["previous_handler_id"] = getattr(tracker, "_previous_handler_id", None)
    return out


@router.post("/{tracking_id}/release")
async def release_form_handling(
    tracking_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Release the handling lock (holder only). Opens the form for anyone eligible."""
    tracker = HandlingLockService(db).release_handling(tracking_id, current_user)
    return _serialize(db, tracker, viewer_user_id=current_user.get("id"))
