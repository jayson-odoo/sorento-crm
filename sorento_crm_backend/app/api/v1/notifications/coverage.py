"""Coverage subscription API: list / subscribe / unsubscribe.

A subscriber covers a colleague (target) so the target's future SLA
assignment/escalation notifications also reach the subscriber.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.services.coverage_subscription_service import CoverageSubscriptionService
from app.services.error_handler import handle_internal_error
from app.services.user_service import UserPermissionService

router = APIRouter()

MANAGE_TEAM_PERM = "notifications.coverage.manage_team"


class _SubscribeRequest(BaseModel):
    target_user_id: str
    expires_at: Optional[datetime] = None
    # True = auto-assign the target's future SLA tasks to me (redirect; sole coverer).
    # False = notify-only (default): I'm notified and take over manually.
    redirect_assignments: bool = False


class _AssignRequest(BaseModel):
    coverer_id: str
    target_user_id: str
    expires_at: Optional[datetime] = None
    redirect_assignments: bool = False


@router.get("/")
async def list_my_coverage(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List the colleagues I am covering for (my subscriptions)."""
    try:
        data = CoverageSubscriptionService(db).list_my_subscriptions(current_user["id"])
        return {"data": data, "empty": len(data) == 0}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", status_code=201)
async def subscribe_coverage(
    payload: _SubscribeRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Subscribe to a colleague (scope-B). Reactivates an existing row if present."""
    try:
        sub = CoverageSubscriptionService(db).subscribe(
            current_user["id"],
            payload.target_user_id,
            payload.expires_at,
            redirect_assignments=payload.redirect_assignments,
        )
        return {
            "id": str(sub.id),
            "target_user_id": str(sub.target_user_id),
            "is_active": bool(sub.is_active),
            "redirect_assignments": bool(getattr(sub, "redirect_assignments", False)),
            "expires_at": (
                getattr(sub, "expires_at").isoformat()
                if getattr(sub, "expires_at", None)
                else None
            ),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/team")
async def list_team_coverage(
    current_user: dict = Depends(require_permission(MANAGE_TEAM_PERM)),
    db: Session = Depends(get_db),
):
    """HoD view: active coverage across my team scope (coverer OR covered in scope-B)."""
    try:
        data = CoverageSubscriptionService(db).list_team_subscriptions(current_user["id"])
        return {"data": data, "empty": len(data) == 0}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/assign", status_code=201)
async def assign_coverage(
    payload: _AssignRequest,
    current_user: dict = Depends(require_permission(MANAGE_TEAM_PERM)),
    db: Session = Depends(get_db),
):
    """HoD assigns one team member to cover another (both in the actor's scope-B).

    Takes effect immediately; the coverer is notified. Records ``created_by_id`` for
    audit. Permission-gated by ``notifications.coverage.manage_team``."""
    try:
        sub = CoverageSubscriptionService(db).assign_coverage(
            current_user["id"],
            payload.coverer_id,
            payload.target_user_id,
            payload.expires_at,
            redirect_assignments=payload.redirect_assignments,
        )
        return {
            "id": str(sub.id),
            "subscriber_id": str(sub.subscriber_id),
            "target_user_id": str(sub.target_user_id),
            "redirect_assignments": bool(getattr(sub, "redirect_assignments", False)),
            "expires_at": (
                getattr(sub, "expires_at").isoformat()
                if getattr(sub, "expires_at", None)
                else None
            ),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/manage/{subscription_id}", status_code=200)
async def revoke_coverage_by_id(
    subscription_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revoke a specific coverage row by id. Allowed for the coverer (owns it) or a
    HoD with ``manage_team`` when both endpoints are in their scope-B."""
    try:
        can_manage = UserPermissionService(db).check_user_has_permission(
            current_user["id"], MANAGE_TEAM_PERM
        )
        CoverageSubscriptionService(db).deactivate_by_id(
            subscription_id, current_user["id"], can_manage
        )
        return {"message": "Revoked"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{target_user_id}", status_code=200)
async def unsubscribe_coverage(
    target_user_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Stop covering a colleague (deactivate the subscription)."""
    try:
        CoverageSubscriptionService(db).unsubscribe(current_user["id"], target_user_id)
        return {"message": "Unsubscribed"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
