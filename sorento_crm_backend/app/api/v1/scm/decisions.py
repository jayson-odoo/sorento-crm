"""SCM M4 Slice B - decision endpoints (Accept / Adjust / Reject + bulk) and the
per-run decision-state read. Also S16 (captain 21 Aug): the row decision - buy /
use stock / use PO / skip, or a mixture - recorded directly on a recommendation via
``POST/DELETE .../recommendations/{rec_id}/decision``, read back (with the results-
grid header's decided/total counts) via ``GET .../reorder-runs/{run_id}/plan-row-
decisions``.

Deciding on a recommendation mutates planning state (draft POs, override rows,
rec.status) so writes are gated on ``scm.reorder.run``. Reading the decision state
for the results grid is a dashboard view (``scm.dashboard.view``). Paths mirror the
FE contract in ``reorder/services/decisionService.ts``. No UUIDs surface.
"""
from __future__ import annotations

from pydantic import BaseModel
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
    PlanRowDecisionListResponse,
    RecDecisionListResponse,
    RecordPlanRowDecisionRequest,
    RejectRequest,
)
from app.schemas.scm_decisions import PlanRowDecision as PlanRowDecisionSchema
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


class CoveredDecisionRequest(BaseModel):
    """`use_stock` keeps the stock already there; `buy` turns the row into a purchase."""
    choice: str


@router.post("/recommendations/{rec_id}/covered-decision")
def covered_decision(
    rec_id: str,
    payload: CoveredDecisionRequest = Body(...),
    db: Session = Depends(get_db),
    _user: dict = Depends(_RUN),
):
    """Resolve a covered-by-stock row. The engine deliberately does not decide this."""
    result = svc.decide_covered(db, rec_id, payload.choice, (_user or {}).get("id"))
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


@router.post("/recommendations/{rec_id}/decision", response_model=PlanRowDecisionSchema)
def record_decision(
    rec_id: str,
    payload: RecordPlanRowDecisionRequest = Body(...),
    db: Session = Depends(get_db),
    _user: dict = Depends(_RUN),
):
    """S16 (captain 21 Aug) - the row decision: buy / use stock / use PO / skip, or a
    mixture, recorded directly on the recommendation. Works on any decidable rec_type,
    not just buy (see `decision_service._get_decidable_rec`), and on a product-grain
    run's grouped product exactly the way `set_moq_override` does - the caller sends
    one recommendation id per member, this route never needs to know the grouping."""
    result = svc.record_plan_row_decision(
        db,
        rec_id,
        payload.kind,
        payload.buy_qty,
        [s.model_dump() for s in payload.stock_takes],
        payload.po_qty,
        payload.po_refs,
        payload.reason_text,
        (_user or {}).get("id"),
    )
    db.commit()
    return result


@router.delete("/recommendations/{rec_id}/decision")
def clear_decision(
    rec_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_RUN),
):
    """Withdraw a row decision back to undecided."""
    result = svc.clear_plan_row_decision(db, rec_id, (_user or {}).get("id"))
    db.commit()
    return result


@router.get(
    "/reorder-runs/{run_id}/plan-row-decisions", response_model=PlanRowDecisionListResponse
)
def list_plan_row_decisions(
    run_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """Every persisted row decision on a run + the decided/total counts the results-
    grid header ("N of Total made") counts against."""
    reorder_run_service.assert_run_visible(db, run_id)
    return svc.list_plan_row_decisions(db, run_id)


@router.post("/reorder-runs/{run_id}/reset-decisions")
def reset_decisions(
    run_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_RUN),
):
    """DEMO / ADMIN - roll a run's decisions back to its as-generated state (clears
    every accept/reject/adjust + drops the draft POs they staged) so the flow can be
    demonstrated again. Only draft POs are removed; confirmed (active) orders are left
    untouched. Guarded by ``scm.reorder.run`` (the same permission that makes the
    decisions)."""
    reorder_run_service.assert_run_visible(db, run_id)
    result = svc.reset_run_decisions(db, run_id, (_user or {}).get("id"))
    db.commit()
    return result
