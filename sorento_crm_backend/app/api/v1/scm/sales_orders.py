"""SCM M1 sales-order endpoints — CRUD + create-DO-from-SO.

Read gated on ``scm.dashboard.view``; write gated on ``scm.reorder.run`` (the
SCM operator capability). No UUIDs surfaced — SO by so_number.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.schemas.scm_orders import (
    CreateDoResponse,
    SalesOrder,
    SalesOrderFormData,
    SalesOrderListResponse,
    SalesOrderUpdate,
)
from app.services.scm.sales_order_service import SalesOrderService

router = APIRouter()

_READ = require_permission_with_api_key("scm.dashboard.view")
_WRITE = require_permission("scm.reorder.run")


@router.get("/sales-orders", response_model=SalesOrderListResponse)
def list_sales_orders(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    sort: Optional[str] = Query(None),
    dir: str = Query("desc"),
    query: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _user: dict = Depends(_READ),
):
    return SalesOrderService(db).list(page, limit, sort, dir, query, status, priority)


@router.get("/sales-orders/{so_id}", response_model=SalesOrder)
def get_sales_order(so_id: str, db: Session = Depends(get_db), _user: dict = Depends(_READ)):
    return SalesOrderService(db).get(so_id)


@router.post("/sales-orders", response_model=SalesOrder, status_code=status.HTTP_201_CREATED)
def create_sales_order(
    data: SalesOrderFormData,
    db: Session = Depends(get_db),
    user: dict = Depends(_WRITE),
):
    return SalesOrderService(db).create(data, user.get("id"))


@router.put("/sales-orders/{so_id}", response_model=SalesOrder)
def update_sales_order(
    so_id: str,
    data: SalesOrderUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(_WRITE),
):
    return SalesOrderService(db).update(so_id, data, user.get("id"))


@router.delete("/sales-orders/{so_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sales_order(so_id: str, db: Session = Depends(get_db), _user: dict = Depends(_WRITE)):
    SalesOrderService(db).delete(so_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sales-orders/{so_id}/create-do", response_model=CreateDoResponse)
def create_do_from_so(
    so_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(_WRITE),
):
    return SalesOrderService(db).create_do_from_so(so_id, user.get("id"))
