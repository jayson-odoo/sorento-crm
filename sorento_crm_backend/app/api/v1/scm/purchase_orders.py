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
from app.schemas.autocount_mirror import MirrorAnnotationUpdate
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
    db: Session = Depends(get_db),
    _user: dict = Depends(_READ),
):
    return PurchaseOrderService(db).list(page, limit, sort, dir, query, status, supplier)


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


@router.patch("/purchase-orders/{po_id}/annotation", response_model=PurchaseOrder)
def annotate_purchase_order(
    po_id: str,
    body: MirrorAnnotationUpdate,
    db: Session = Depends(get_db),
    _user: dict = Depends(_WRITE),
):
    """Update the two ingest-safe annotation columns. Allowed on AutoCount-synced
    POs (the one thing editable on a read-only mirror row)."""
    fields = body.model_dump(exclude_unset=True)
    return PurchaseOrderService(db).annotate(
        po_id,
        internal_note=fields.get("internal_note", ...) if "internal_note" in fields else ...,
        follow_up=fields.get("follow_up", ...) if "follow_up" in fields else ...,
    )


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
