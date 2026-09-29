"""Sales Teams API (plan 3.8; UAC S6-1 to S6-3, S6-8, S6-14, S6-15).

Plain `def` handlers: nothing here awaits, and an `async def` that never awaits blocks the
worker's event loop (LESSONS-LEARNT).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.schemas.common import ListResponse
from app.schemas.sales import (
    SalesTeamAgentOption,
    SalesTeamCreate,
    SalesTeamDetail,
    SalesTeamListItem,
    SalesTeamMembersUpdate,
    SalesTeamUpdate,
)
from app.services.error_handler import handle_internal_error
from app.services.sales import team_service
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()

VIEW = "sales.teams.view"
ADD = "sales.teams.add"
EDIT = "sales.teams.edit"
DELETE = "sales.teams.delete"


def _reraise(db: Session, exc: Exception):
    db.rollback()
    raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


def _list(data: list) -> dict:
    return {
        "data": data,
        "pagination": {"total": len(data), "page": 1, "limit": max(len(data), 1)},
        "empty": not data,
    }


@router.get("", response_model=ListResponse[SalesTeamListItem])
def list_teams(
    query: Optional[str] = Query(None),
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        return _list(team_service.list_teams(db, query=query))
    except Exception as exc:
        _reraise(db, exc)


# Before `/{team_id}`, which would otherwise capture it.
@router.get("/agent-options", response_model=ListResponse[SalesTeamAgentOption])
def agent_options(
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        company_id = team_service.acting_company_id(db)
        return _list(team_service.agent_options(db, company_id=company_id))
    except Exception as exc:
        _reraise(db, exc)


@router.post("", response_model=SalesTeamDetail, status_code=status.HTTP_201_CREATED)
def create_team(
    payload: SalesTeamCreate,
    _user: dict = Depends(require_permission(ADD)),
    db: Session = Depends(get_db),
):
    try:
        team, moved = team_service.create_team_with_members(
            db,
            company_id=team_service.acting_company_id(db),
            name=payload.name,
            sales_agent_ids=payload.sales_agent_ids,
            is_active=payload.is_active,
            moves_on=payload.moves_on,
            leader_sales_agent_id=payload.leader_sales_agent_id,
        )
        db.commit()
        db.refresh(team)
        return team_service.team_detail(db, team, moved=moved)
    except Exception as exc:
        _reraise(db, exc)


@router.get("/{team_id}", response_model=SalesTeamDetail)
def get_team(
    team_id: str,
    on: Optional[date] = Query(None),
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(team_id, resource="Sales Team")
        team = team_service.get_team_or_404(db, team_id)
        return team_service.team_detail(db, team, on=on)
    except Exception as exc:
        _reraise(db, exc)


@router.patch("/{team_id}", response_model=SalesTeamDetail)
def update_team(
    team_id: str,
    payload: SalesTeamUpdate,
    _user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(team_id, resource="Sales Team")
        team = team_service.get_team_or_404(db, team_id)
        team_service.update_team(db, team, name=payload.name, is_active=payload.is_active)
        moved = team_service.save_members_and_leader(
            db,
            team,
            payload.sales_agent_ids,
            moves_on=payload.moves_on,
            leader_sales_agent_id=payload.leader_sales_agent_id,
            set_leader="leader_sales_agent_id" in payload.model_fields_set,
        )
        db.commit()
        db.refresh(team)
        return team_service.team_detail(db, team, moved=moved)
    except Exception as exc:
        _reraise(db, exc)


@router.put("/{team_id}/members", response_model=SalesTeamDetail)
def set_members(
    team_id: str,
    payload: SalesTeamMembersUpdate,
    _user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(team_id, resource="Sales Team")
        team = team_service.get_team_or_404(db, team_id)
        moved = team_service.set_members(
            db, team, payload.sales_agent_ids, moves_on=payload.moves_on
        )
        db.commit()
        db.refresh(team)
        return team_service.team_detail(db, team, moved=moved)
    except Exception as exc:
        _reraise(db, exc)


@router.delete("/{team_id}")
def delete_team(
    team_id: str,
    _user: dict = Depends(require_permission(DELETE)),
    db: Session = Depends(get_db),
):
    """Immediate hard delete. The screens park `sales_team.delete` instead (D7)."""
    try:
        validate_uuid_path(team_id, resource="Sales Team")
        team = team_service.get_team_or_404(db, team_id)
        name = team.name
        team_service.delete_team(db, team)
        db.commit()
        return {"message": f"{name} deleted"}
    except Exception as exc:
        _reraise(db, exc)
