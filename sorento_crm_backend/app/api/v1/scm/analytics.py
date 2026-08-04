"""SCM M2 analytics endpoints — trigger a demand/classification/supplier run and
read the run log.

Running the engine is a planning action (``scm.reorder.run``); reading the run log /
explain working is a dashboard view (``scm.dashboard.view``). The scheduled trigger is
a later slice — this is the manual on-demand entry point plus the observability read.
"""
from __future__ import annotations

from typing import Any, List, Optional

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.services.company_scope_sql import company_sql_predicate
from app.services.error_handler import AppException
from app.services.scm import analytics_service

router = APIRouter()

_VIEW = require_permission_with_api_key("scm.dashboard.view")
_RUN = require_permission_with_api_key("scm.reorder.run")


@router.post("/analytics/run")
def trigger_run(
    payload: Optional[dict] = Body(default=None),
    db: Session = Depends(get_db),
    _user: dict = Depends(_RUN),
):
    """Run the analytics engine now. Optional body: ``scope`` (product_ids /
    warehouse_ids / supplier_ids) and ``config`` (as_of)."""
    payload = payload or {}
    scope = payload.get("scope") or None
    config = payload.get("config") or None
    return analytics_service.run_analytics(db, scope=scope, config=config)


@router.get("/analytics/runs")
def list_runs(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """Recent analytics run logs (newest first) — status / counts / window / coverage."""
    # Raw SQL, so the ORM scope filter does not reach it: this company's run log only.
    co, co_params = company_sql_predicate(db, "company_id", param_prefix="car")
    rows = db.execute(text(
        "SELECT id, started_at, finished_at, status, scope, counts, window_days, "
        "config_ref, error_text FROM scm.scm_analytics_run "
        f"WHERE {co or 'true'} "
        "ORDER BY started_at DESC NULLS LAST LIMIT :lim"
    ), {"lim": limit, **co_params}).fetchall()
    data: List[dict[str, Any]] = []
    for r in rows:
        data.append({
            "id": r.id,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "status": r.status,
            "scope": r.scope,
            "counts": r.counts,
            "window_days": r.window_days,
            "as_of": r.config_ref,
            "error_text": r.error_text,
        })
    return {"data": data}


@router.get("/analytics/explain/demand")
def explain_demand(
    product_id: str = Query(...),
    warehouse_id: Optional[str] = Query(None),
    as_of: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """Deterministically re-derive a SKU's demand working (window, buckets, channel
    split, method, CV) for debugging."""
    if not product_id:
        raise AppException(status_code=422, message="product_id is required.")
    config = {"as_of": as_of} if as_of else None
    return analytics_service.explain_demand(db, product_id, warehouse_id, config=config)
