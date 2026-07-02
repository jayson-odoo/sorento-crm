"""SLA KPI dashboard endpoints (TCK-32). Management-only (sla.kpi.view)."""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.services import sla_kpi_service as kpi

router = APIRouter()

_SCOPE = Query("all", pattern="^(all|conversation|form)$")


@router.get("/summary")
async def kpi_summary(
    scope: str = _SCOPE,
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    assignee_id: Optional[str] = Query(None),
    _user: dict = Depends(require_permission("sla.kpi.view")),
    db: Session = Depends(get_db),
):
    return kpi.kpi_summary(
        db, scope=scope, date_from=date_from, date_to=date_to,
        entity_type=entity_type, assignee_id=assignee_id,
    )


@router.get("/leaderboard")
async def kpi_leaderboard(
    scope: str = _SCOPE,
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    _user: dict = Depends(require_permission("sla.kpi.view")),
    db: Session = Depends(get_db),
):
    return {"data": kpi.kpi_leaderboard(
        db, scope=scope, date_from=date_from, date_to=date_to,
        entity_type=entity_type, limit=limit,
    )}


@router.get("/trend")
async def kpi_trend(
    scope: str = _SCOPE,
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    bucket: str = Query("day", pattern="^(day|week)$"),
    _user: dict = Depends(require_permission("sla.kpi.view")),
    db: Session = Depends(get_db),
):
    return {"data": kpi.kpi_trend(
        db, scope=scope, date_from=date_from, date_to=date_to,
        entity_type=entity_type, bucket=bucket,
    )}


@router.get("/tasks")
async def kpi_tasks(
    scope: str = _SCOPE,
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    assignee_id: Optional[str] = Query(None),
    view: str = Query("all", pattern="^(all|responded|resolved|pending|responded_open)$"),
    state: str = Query("all", pattern="^(all|within|overdue)$"),
    esc_window: str = Query("all", pattern="^(all|overdue|1h|4h|24h)$"),
    sort: Optional[str] = Query(None),
    dir: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=200),
    _user: dict = Depends(require_permission("sla.kpi.view")),
    db: Session = Depends(get_db),
):
    return kpi.kpi_tasks(
        db, scope=scope, date_from=date_from, date_to=date_to,
        entity_type=entity_type, assignee_id=assignee_id, view=view, state=state,
        esc_window=esc_window, sort=sort, dir=dir,
        page=page, limit=limit,
    )
