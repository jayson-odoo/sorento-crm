"""SCM M5 — semantic explainer endpoints (bounded prose + scoped Q&A + advisory).

Read-oriented viewing aids gated on ``scm.dashboard.view``. Explanation lazily
caches its prose on first view; Q&A is stateless. No MCP tool / agent loop and no
numeric write anywhere (AC-M5.3 / AC-M5.8). Paths mirror the FE contract in
``reorder/services/explainerService.ts``.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.schemas.scm_explainer import (
    AdvisoryResult,
    AskRequest,
    AskResult,
    ExplanationResult,
    PastPlansResult,
    RunChatRequest,
    RunChatResult,
    RunOverviewResult,
)
from app.services.scm import explainer_service as svc

router = APIRouter()

_VIEW = require_permission_with_api_key("scm.dashboard.view")


@router.get("/recommendations/{rec_id}/explanation", response_model=ExplanationResult)
def get_explanation(
    rec_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    text = svc.explain_recommendation(db, rec_id)
    db.commit()  # persist the lazily-cached explanation
    return {"explanation": text}


@router.get("/reorder-runs/{run_id}/overview", response_model=RunOverviewResult)
def get_run_overview(
    run_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    text = svc.explain_run(db, run_id)
    db.commit()  # persist the lazily-cached overview
    return {"overview": text}


@router.post("/reorder-runs/{run_id}/chat", response_model=RunChatResult)
def run_chat(
    run_id: str,
    payload: RunChatRequest = Body(...),
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """Unified plan assistant (M8-F6): one Ask input. The service auto-decides whether
    a live market web search is needed, folds any reading into the grounded answer, and
    attaches a confirm-gated ``proposal`` when a signal maps onto plan lines. No numeric
    write anywhere; a live scan only caches its own signal row (persisted on commit)."""
    history = [t.model_dump() for t in payload.history]
    result = svc.answer_run_chat(
        db, run_id, payload.question, history, actor=(_user or {}).get("id")
    )
    db.commit()  # persist any signal row cached by an auto-run market scan
    return result


@router.get("/reorder-runs/{run_id}/past-plans", response_model=PastPlansResult)
def get_past_plans(
    run_id: str,
    product_code: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """Cross-run history (M8-E3): prior COMPLETED-run lines for a SKU (+ its category
    siblings / variant neighbours) or a category. Read-only; the current run is
    excluded so only PRIOR plans surface."""
    lines = svc.query_past_plans(
        db,
        product_code=product_code,
        category_ref=category,
        exclude_run_id=run_id,
    )
    return {"data": lines}


@router.post("/recommendations/{rec_id}/ask", response_model=AskResult)
def ask(
    rec_id: str,
    payload: AskRequest = Body(...),
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    return {"answer": svc.answer_question(db, rec_id, payload.question)}


@router.get("/recommendations/{rec_id}/advisory", response_model=AdvisoryResult)
def get_advisory(
    rec_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    advisory = svc.market_advisory(db, rec_id)
    db.commit()  # persist the lazily-cached advisory (get_db closes without commit)
    return {"advisory": advisory}
