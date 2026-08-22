"""SCM S5 - Plan Exception endpoints (UAC Group D).

Two routes: read the batch, and decide one exception. Neither computes anything - the batch
is FROZEN when a re-uploaded order book is confirmed (AC-D2a), and a GET that recomputed
would give two people different answers to the same question minutes apart while the
reviewer's decision is against the figures the engine actually saw.

Reading is `scm.dashboard.view`, matching the report and the worklist. Deciding is
`scm.reorder.run`, matching every other route that writes a planning decision.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.services.error_handler import AppException
from app.services.scm import plan_exception_service as svc

router = APIRouter()

_VIEW = require_permission_with_api_key("scm.dashboard.view")
_RUN = require_permission_with_api_key("scm.reorder.run")

_STATUSES = ("open", "approved", "rejected")


@router.get("/plan-exceptions")
def get_plan_exceptions(
    run_id: Optional[str] = Query(
        None,
        description=(
            "Which run's batch to read. Omitted means the newest batch. Opaque: it is never "
            "rendered."
        ),
    ),
    status: Optional[str] = Query(None, description="open | approved | rejected"),
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """Where the restated plan disagrees with supply already placed (AC-D2).

    `counts.delta_count` is the UPLOAD's own figure carried through unchanged, so the screen
    can show the reduction from changed lines to exceptions and the two reconcile (AC-D2b).

    An install where nothing has been re-uploaded has no batch, and that reads as an empty
    report rather than a 404: there is nothing wrong, there is simply nothing to disagree
    with yet.
    """
    if status is not None and status not in _STATUSES:
        raise AppException(422, "status must be open, approved or rejected.")
    return svc.report(db, run_id=run_id, status=status)


@router.post("/plan-exceptions/{exception_id}/decision")
def decide_plan_exception(
    exception_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    _user: dict = Depends(_RUN),
):
    """Approve or reject one exception (AC-D6).

    Validation lives in the service, not here, so the rules hold for every caller rather than
    for whoever went through this route: approving names one of THIS exception's proposed
    actions, rejecting carries a reason, a split moves a part strictly inside the quantity,
    and an already-decided exception is a 409.

    Approving a reallocation writes an allocation decision. No placed purchase order is
    amended by this endpoint (AC-D7).
    """
    row = svc.decide(
        db,
        exception_id,
        status=payload.get("status"),
        action_code=payload.get("action_code"),
        reason=payload.get("reason"),
        split_qty=payload.get("split_qty"),
        actor=(_user or {}).get("id"),
    )
    db.commit()

    # The actor's NAME, resolved for the row the screen updates in place. Never a user id.
    names = svc._actor_names(db, [row.decided_by]) if row.decided_by else {}
    out: dict[str, Any] = {
        "exception_id": str(row.id),
        "status": row.status,
        "decided_by": names.get(str(row.decided_by)) if row.decided_by else None,
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        "decided_action": row.decided_action,
        "decision_reason": row.decision_reason,
    }
    return out
