"""SCM purchase-order endpoints — list/read + the M4 Slice B draft→confirm→GR flow.

Reads are gated on ``scm.dashboard.view``; the confirm + create-GR writes mutate
supply state so they are gated on ``scm.reorder.run`` (the planning permission that
already governs accepting recommendations into drafts). No UUIDs surfaced — PO by
po_number, GR by its reference.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.schemas.scm_decisions import (
    BulkConfirmRequest,
    BulkConfirmResult,
    CreateGrResult,
)
from app.schemas.scm_orders import PurchaseOrder, PurchaseOrderListResponse
from app.services.error_handler import AppException
from app.services.scm.purchase_order_service import PurchaseOrderService

router = APIRouter()

_READ = require_permission_with_api_key("scm.dashboard.view")
_WRITE = require_permission_with_api_key("scm.reorder.run")


@router.get("/purchase-orders", response_model=PurchaseOrderListResponse)
def list_purchase_orders(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    sort: Optional[str] = Query(None),
    dir: str = Query("desc"),
    query: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    supplier: Optional[str] = Query(None),
    product_code: Optional[str] = Query(
        None,
        description="Keep only orders carrying this SKU, and report what we last paid for it.",
    ),
    db: Session = Depends(get_db),
    _user: dict = Depends(_READ),
):
    """The purchase-order list.

    `product_code` answers the question this screen could not be asked before - "have we ever
    bought this item, and for how much" - which matters because the plan now takes its cost
    from this book. The response carries a `product_cost` block beside the rows: the most
    recent priced line, or null when we have never bought it. A recorded 0 comes back as 0,
    because free and never-bought are different answers.
    """
    return PurchaseOrderService(db).list(
        page, limit, sort, dir, query, status, supplier, product_code=product_code,
    )


@router.post("/purchase-orders/bulk-confirm", response_model=BulkConfirmResult)
def bulk_confirm_purchase_orders(
    payload: BulkConfirmRequest = Body(...),
    db: Session = Depends(get_db),
    _user: dict = Depends(_WRITE),
):
    """Confirm draft POs → active + canonical PO number (M4-D6). Idempotent."""
    return PurchaseOrderService(db).bulk_confirm(payload.ids, (_user or {}).get("id"))


@router.post("/purchase-orders/{po_id}/create-gr", response_model=CreateGrResult)
def create_gr_from_purchase_order(
    po_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_WRITE),
):
    """Create a goods receipt from an active PO, stamping received qty (M4-D6)."""
    return PurchaseOrderService(db).create_gr(po_id, (_user or {}).get("id"))


@router.get("/purchase-orders/{po_id}", response_model=PurchaseOrder)
def get_purchase_order(
    po_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_READ),
):
    po = PurchaseOrderService(db).get_one(po_id)
    if po is None:
        raise AppException(status_code=404, message="Purchase order not found.")
    return po
