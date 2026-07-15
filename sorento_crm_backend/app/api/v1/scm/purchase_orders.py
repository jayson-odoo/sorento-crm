"""SCM M1 purchase-order endpoints — read-only list (+ lines).

Create / confirm / receive land in M4. Read gated on ``scm.dashboard.view``.
No UUIDs surfaced — PO by po_number.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.schemas.scm_orders import PurchaseOrderListResponse
from app.services.scm.purchase_order_service import PurchaseOrderService

router = APIRouter()

_READ = require_permission_with_api_key("scm.dashboard.view")


@router.get("/purchase-orders", response_model=PurchaseOrderListResponse)
def list_purchase_orders(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    sort: Optional[str] = Query(None),
    dir: str = Query("desc"),
    query: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    supplier: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _user: dict = Depends(_READ),
):
    return PurchaseOrderService(db).list(page, limit, sort, dir, query, status, supplier)
