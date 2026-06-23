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
from app.dependencies import get_current_user
from app.services.coverage_subscription_service import CoverageSubscriptionService
from app.services.error_handler import handle_internal_error

router = APIRouter()


class _SubscribeRequest(BaseModel):
    target_user_id: str
    expires_at: Optional[datetime] = None


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
            current_user["id"], payload.target_user_id, payload.expires_at
        )
        return {
            "id": str(sub.id),
            "target_user_id": str(sub.target_user_id),
            "is_active": bool(sub.is_active),
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
