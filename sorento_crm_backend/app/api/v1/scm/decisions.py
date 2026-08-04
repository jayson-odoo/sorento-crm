"""SCM M4 Slice B — decision endpoints (Accept / Adjust / Reject + bulk) and the
per-run decision-state read.

Deciding on a recommendation mutates planning state (draft POs, override rows,
rec.status) so writes are gated on ``scm.reorder.run``. Reading the decision state
for the results grid is a dashboard view (``scm.dashboard.view``). Paths mirror the
FE contract in ``reorder/services/decisionService.ts``. No UUIDs surface.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.schemas.scm_decisions import (
    AcceptResult,
    AdjustRequest,
    BulkAcceptRequest,
    BulkAcceptResult,
    BulkRejectRequest,
    BulkRejectResult,
    ConfirmDecisionsRequest,
    ConfirmDecisionsResult,
    RecDecisionListResponse,
    RejectRequest,
)
from app.services.scm import reorder_run_service
from app.services.scm import decision_service as svc

router = APIRouter()

_VIEW = require_permission_with_api_key("scm.dashboard.view")
_RUN = require_permission_with_api_key("scm.reorder.run")


@router.post("/recommendations/bulk-accept", response_model=BulkAcceptResult)
def bulk_accept(
    payload: BulkAcceptRequest = Body(...),
    db: Session = Depends(get_db),
    _user: dict = Depends(_RUN),
):
    result = svc.bulk_accept(db, payload.run_id, payload.ids, (_user or {}).get("id"))
    db.commit()
    return result


@router.post("/recommendations/bulk-reject", response_model=BulkRejectResult)
def bulk_reject(
    payload: BulkRejectRequest = Body(...),
    db: Session = Depends(get_db),
    _user: dict = Depends(_RUN),
):
    result = svc.bulk_reject(
        db, payload.run_id, payload.ids, payload.reason_text, (_user or {}).get("id")
    )
    db.commit()
    return result


@router.post("/recommendations/{rec_id}/accept", response_model=AcceptResult)
def accept(
    rec_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_RUN),
):
    result = svc.accept_recommendation(db, rec_id, (_user or {}).get("id"))
    db.commit()
    return result


@router.post("/recommendations/{rec_id}/adjust", response_model=AcceptResult)
def adjust(
    rec_id: str,
    payload: AdjustRequest = Body(...),
    db: Session = Depends(get_db),
    _user: dict = Depends(_RUN),
):
    result = svc.adjust_recommendation(
        db,
        rec_id,
        payload.override_qty,
        payload.override_supplier_id,
        payload.reason_text,
        (_user or {}).get("id"),
    )
    db.commit()
    return result


@router.post("/recommendations/{rec_id}/reject")
def reject(
    rec_id: str,
    payload: RejectRequest = Body(...),
    db: Session = Depends(get_db),
    _user: dict = Depends(_RUN),
):
    result = svc.reject_recommendation(db, rec_id, payload.reason_text, (_user or {}).get("id"))
    db.commit()
    return result


@router.post(
    "/reorder-runs/{run_id}/confirm-decisions", response_model=ConfirmDecisionsResult
)
def confirm_decisions(
    run_id: str,
    payload: ConfirmDecisionsRequest = Body(default=ConfirmDecisionsRequest()),
    db: Session = Depends(get_db),
    _user: dict = Depends(_RUN),
):
    reorder_run_service.assert_run_visible(db, run_id)
    result = svc.confirm_decisions(db, run_id, payload.ids, (_user or {}).get("id"))
    db.commit()
    return result


@router.get("/reorder-runs/{run_id}/decisions", response_model=RecDecisionListResponse)
def list_decisions(
    run_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    reorder_run_service.assert_run_visible(db, run_id)
    return {"data": svc.list_decisions(db, run_id)}


@router.post("/reorder-runs/{run_id}/reset-decisions")
def reset_decisions(
    run_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_RUN),
):
    """DEMO / ADMIN — roll a run's decisions back to its as-generated state (clears
    every accept/reject/adjust + drops the draft POs they staged) so the flow can be
    demonstrated again. Only draft POs are removed; confirmed (active) orders are left
    untouched. Guarded by ``scm.reorder.run`` (the same permission that makes the
    decisions)."""
    reorder_run_service.assert_run_visible(db, run_id)
    result = svc.reset_run_decisions(db, run_id, (_user or {}).get("id"))
    db.commit()
    return result
