"""Set-apart customers (SALES-UNIFIED 2.4): read with `sales.reports.view` (the reports they
shape), written with `sales.set_apart.edit`. Plain `def` handlers: nothing here awaits."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.services.sales import set_apart_service as svc
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()

VIEW = "sales.reports.view"
EDIT = "sales.set_apart.edit"


class SetApartCreate(BaseModel):
    customer_id: str
    from_month: str
    to_month: Optional[str] = None


class SetApartUpdate(BaseModel):
    customer_id: Optional[str] = None
    from_month: Optional[str] = None
    to_month: Optional[str] = None


@router.get("")
def list_set_apart(
    query: Optional[str] = Query(None),
    sort: str = Query("debtor_code"),
    dir: Literal["asc", "desc"] = Query("asc"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    return svc.list_rows(db, query=query, sort=sort, direction=dir, page=page, limit=limit)


# Before `/{row_id}`, which would otherwise capture it.
@router.get("/customer-options")
def customer_options(
    query: Optional[str] = Query(None),
    _user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    return {"data": svc.customer_options(db, query=query)}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_set_apart(
    payload: SetApartCreate,
    _user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    return svc.create(db, customer_id=payload.customer_id, from_month=payload.from_month,
                      to_month=payload.to_month)


@router.patch("/{row_id}")
def update_set_apart(
    row_id: str,
    payload: SetApartUpdate,
    _user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    row_id = validate_uuid_path(row_id, resource="Set-apart customer")
    return svc.update(db, row_id, payload.model_dump(exclude_unset=True))


@router.delete("/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_set_apart(
    row_id: str,
    _user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    svc.delete(db, validate_uuid_path(row_id, resource="Set-apart customer"))
