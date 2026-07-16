"""SCM M5 Part B — market advisory endpoints (signals viz + research run + topic CRUD).

Advisory-only (M5-D4): nothing here writes a quantity/ROP/SS/rank — signals are
cached web-search output. Reads are dashboard views (``scm.dashboard.view``);
firing a research run is a planning action (``scm.reorder.run``); topic config is
an admin surface (``scm.policy.manage``). Topic list is a plain view. Paths mirror
the FE contract in ``scm/market/services/marketService.ts``. No UUID surfaces.

Static ``/market-research/run`` (POST) and ``/market-research/runs/{id}`` (GET) are
distinct paths; ``/market-topics`` list/create precede the parametric
``/market-topics/{id}`` routes (route-shadowing discipline).
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.schemas.scm_market import (
    MarketResearchRunResult,
    MarketResearchTopicWrite,
    MarketSignalListResponse,
    MarketTopicListResponse,
    MarketTopicResult,
)
from app.services.scm import market_research_service as svc

router = APIRouter()

_VIEW = require_permission_with_api_key("scm.dashboard.view")
_RUN = require_permission_with_api_key("scm.reorder.run")
_MANAGE = require_permission_with_api_key("scm.policy.manage")


# --- signals (read-only viz) ------------------------------------------------

@router.get("/market-signals", response_model=MarketSignalListResponse)
def list_market_signals(
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    return {"data": svc.list_signals(db)}


# --- research run -----------------------------------------------------------

@router.post("/market-research/run", response_model=MarketResearchRunResult)
def run_market_research(
    db: Session = Depends(get_db),
    _user: dict = Depends(_RUN),
):
    return {"run": svc.run_research(db, (_user or {}).get("id"))}


@router.get("/market-research/runs/{run_id}", response_model=MarketResearchRunResult)
def get_market_research_run(
    run_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    return {"run": svc.get_run(db, run_id)}


# --- topic CRUD -------------------------------------------------------------

@router.get("/market-topics", response_model=MarketTopicListResponse)
def list_market_topics(
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    return {"data": svc.list_topics(db)}


@router.post("/market-topics", response_model=MarketTopicResult, status_code=201)
def create_market_topic(
    body: MarketResearchTopicWrite = Body(...),
    db: Session = Depends(get_db),
    _user: dict = Depends(_MANAGE),
):
    return {"topic": svc.create_topic(db, body)}


@router.put("/market-topics/{topic_id}", response_model=MarketTopicResult)
def update_market_topic(
    topic_id: str,
    body: MarketResearchTopicWrite = Body(...),
    db: Session = Depends(get_db),
    _user: dict = Depends(_MANAGE),
):
    return {"topic": svc.update_topic(db, topic_id, body)}


@router.delete("/market-topics/{topic_id}", status_code=204)
def delete_market_topic(
    topic_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_MANAGE),
):
    svc.delete_topic(db, topic_id)
    return Response(status_code=204)
