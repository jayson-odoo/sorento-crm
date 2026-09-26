"""Sales Targets API (plan 3.1, 3.8, 16.3; UAC S1-1 to S1-29, S6-4 to S6-7).

Slugs (S1-13): the list, a detail and the modal's options need `sales.targets.view`; create
needs `.add`; a header edit, a period's figure, Duplicate and Add figure need `.edit`; DELETE
needs `.delete`. Plain `def` handlers: nothing here awaits (LESSONS-LEARNT).
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.schemas.sales import (
    SalesTargetChildCreate,
    SalesTargetCreate,
    SalesTargetDetail,
    SalesTargetList,
    SalesTargetOptions,
    SalesTargetPeriodUpdate,
    SalesTargetUpdate,
)
from app.services.error_handler import AppException
from app.services.sales import target_service
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()
logger = logging.getLogger(__name__)

VIEW = "sales.targets.view"
ADD = "sales.targets.add"
EDIT = "sales.targets.edit"
DELETE = "sales.targets.delete"


def _reraise(db: Session, exc: Exception):
    # A refusal (AppException) is raised before or inside the write's savepoint, which has
    # already been rolled back, so the rest of the session stays as it was. Anything else is
    # logged here and answered with a generic message: the body never carries the error text,
    # which for a database error holds the statement and its parameters.
    if isinstance(exc, AppException):
        raise exc
    db.rollback()
    logger.exception("sales targets request failed")
    raise AppException(
        status_code=500, message="Something went wrong. Please try again.", code="INTERNAL_ERROR"
    ) from exc


def _user_id(user: dict) -> Optional[str]:
    return str(user["id"]) if user and user.get("id") else None


def _load(db: Session, target_id: str):
    validate_uuid_path(target_id, resource="Target")
    return target_service.get_target_or_404(db, target_id)


@router.get("", response_model=SalesTargetList)
def list_targets(
    on: Optional[date] = Query(None),
    subject: Literal["agent", "team"] = Query("team"),
    sales_team_id: Optional[str] = Query(None),
    query: Optional[str] = Query(None),
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        if sales_team_id and sales_team_id != "none":
            validate_uuid_path(sales_team_id, resource="Sales Team")
        return target_service.list_targets(
            db, on=on, subject=subject, sales_team_id=sales_team_id, query=query
        )
    except Exception as exc:
        _reraise(db, exc)


# Before `/{target_id}`, which would otherwise capture it.
@router.get("/options", response_model=SalesTargetOptions)
def target_options(
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        return target_service.options(db)
    except Exception as exc:
        _reraise(db, exc)


@router.post("", response_model=SalesTargetDetail, status_code=status.HTTP_201_CREATED)
def create_target(
    payload: SalesTargetCreate,
    user: dict = Depends(require_permission(ADD)),
    db: Session = Depends(get_db),
):
    try:
        with db.begin_nested():
            target = target_service.create_target(db, payload, user_id=_user_id(user))
        db.commit()
        db.refresh(target)
        return target_service.target_detail(db, target)
    except Exception as exc:
        _reraise(db, exc)


@router.get("/{target_id}", response_model=SalesTargetDetail)
def get_target(
    target_id: str,
    on: Optional[date] = Query(None),
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        return target_service.target_detail(db, _load(db, target_id), on=on)
    except Exception as exc:
        _reraise(db, exc)


@router.patch("/{target_id}", response_model=SalesTargetDetail)
def update_target(
    target_id: str,
    payload: SalesTargetUpdate,
    _user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        target = _load(db, target_id)
        with db.begin_nested():
            target_service.update_target(db, target, payload)
        db.commit()
        db.refresh(target)
        return target_service.target_detail(db, target)
    except Exception as exc:
        _reraise(db, exc)


@router.patch("/{target_id}/periods/{period_id}", response_model=SalesTargetDetail)
def update_period(
    target_id: str,
    period_id: str,
    payload: SalesTargetPeriodUpdate,
    _user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        target = _load(db, target_id)
        validate_uuid_path(period_id, resource="Period")
        with db.begin_nested():
            target_service.update_period(db, target, period_id, payload.target_value)
        db.commit()
        db.refresh(target)
        return target_service.target_detail(db, target)
    except Exception as exc:
        _reraise(db, exc)


@router.post(
    "/{target_id}/duplicate", response_model=SalesTargetDetail, status_code=status.HTTP_201_CREATED
)
def duplicate_target(
    target_id: str,
    user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        source = _load(db, target_id)
        with db.begin_nested():
            copy = target_service.duplicate_target(db, source, user_id=_user_id(user))
        db.commit()
        db.refresh(copy)
        return target_service.target_detail(db, copy)
    except Exception as exc:
        _reraise(db, exc)


@router.post(
    "/{target_id}/children", response_model=SalesTargetDetail, status_code=status.HTTP_201_CREATED
)
def add_child(
    target_id: str,
    payload: SalesTargetChildCreate,
    user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Add figure (S1-28): returns the team target, re-summed."""
    try:
        validate_uuid_path(payload.sales_agent_id, resource="Sales Agent")
        parent = _load(db, target_id)
        with db.begin_nested():
            target_service.add_child(
                db, parent, payload.sales_agent_id, payload.target_value, user_id=_user_id(user)
            )
        db.commit()
        db.refresh(parent)
        return target_service.target_detail(db, parent)
    except Exception as exc:
        _reraise(db, exc)


@router.delete("/{target_id}")
def delete_target(
    target_id: str,
    _user: dict = Depends(require_permission(DELETE)),
    db: Session = Depends(get_db),
):
    """Immediate hard delete. The screens park `sales_target.delete` instead (D7)."""
    try:
        target = _load(db, target_id)
        name = target.name
        with db.begin_nested():
            target_service.delete_target(db, target)
        db.commit()
        return {"message": f"{name} deleted"}
    except Exception as exc:
        _reraise(db, exc)
