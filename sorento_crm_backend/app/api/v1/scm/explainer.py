"""SCM M5 — semantic explainer endpoints (bounded prose + scoped Q&A + advisory).

Read-oriented viewing aids gated on ``scm.dashboard.view``. Explanation lazily
caches its prose on first view; Q&A is stateless. No MCP tool / agent loop and no
numeric write anywhere (AC-M5.3 / AC-M5.8). Paths mirror the FE contract in
``reorder/services/explainerService.ts``.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.schemas.scm_explainer import (
    AdvisoryResult,
    AskRequest,
    AskResult,
    ExplanationResult,
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
