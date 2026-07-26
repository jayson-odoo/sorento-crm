"""Stock balance snapshots — read-only AutoCount report mirror (Slice 4).

Run-history: list runs (the run selector), open a run to see its balance grid,
annotate the run. Ingest (via /external/stock-balance/ingest) appends runs.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.models.stock_balance_snapshot import StockBalanceSnapshotRun
from app.schemas.autocount_mirror import (
    MirrorAnnotationUpdate,
    StockBalanceSnapshotRunDetailResponse,
    StockBalanceSnapshotRunResponse,
)
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT, PaginationResponse
from app.services.error_handler import AppException, handle_internal_error
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()
_RESOURCE = "Stock Balance Run"


@router.get("/runs", response_model=ListResponse[StockBalanceSnapshotRunResponse])
async def list_runs(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    current_user: dict = Depends(require_permission_with_api_key("inventory.stock_balance_snapshots.view")),
    db: Session = Depends(get_db),
):
    """Runs, newest first -- the run selector."""
    try:
        q = db.query(StockBalanceSnapshotRun).order_by(desc(StockBalanceSnapshotRun.captured_at))
        total = q.count()
        rows = q.offset((page - 1) * limit).limit(limit).all()
        return ListResponse(
            data=rows,
            pagination=PaginationResponse(total=total, page=page, limit=limit),
            empty=total == 0,
        )
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/runs/{run_id}", response_model=StockBalanceSnapshotRunDetailResponse)
async def get_run(
    run_id: str,
    current_user: dict = Depends(require_permission_with_api_key("inventory.stock_balance_snapshots.view")),
    db: Session = Depends(get_db),
):
    """One run header + its balance rows (the grid)."""
    try:
        validate_uuid_path(run_id, resource=_RESOURCE)
        run = db.query(StockBalanceSnapshotRun).filter(StockBalanceSnapshotRun.id == run_id).first()
        if run is None:
            raise AppException(status_code=404, message=f"{_RESOURCE} not found", code="NOT_FOUND")
        return run
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.patch("/runs/{run_id}/annotation", response_model=StockBalanceSnapshotRunResponse)
async def annotate_run(
    run_id: str,
    payload: MirrorAnnotationUpdate,
    current_user: dict = Depends(require_permission("inventory.stock_balance_snapshots.edit")),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(run_id, resource=_RESOURCE)
        run = db.query(StockBalanceSnapshotRun).filter(StockBalanceSnapshotRun.id == run_id).first()
        if run is None:
            raise AppException(status_code=404, message=f"{_RESOURCE} not found", code="NOT_FOUND")
        fields = payload.model_fields_set
        if "internal_note" in fields:
            run.internal_note = payload.internal_note
        if "follow_up" in fields:
            run.follow_up = bool(payload.follow_up)
        db.commit()
        db.refresh(run)
        return run
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
