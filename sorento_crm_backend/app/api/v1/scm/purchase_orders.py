"""SCM purchase-order endpoints - list/read, in-place correction, and the M4 Slice B
draft→confirm→GR flow.

Reads are gated on ``scm.dashboard.view``; every write mutates supply state, so all of them
(confirm, create-GR, bulk delete, and the PUT) are gated on ``scm.reorder.run`` - the planning
permission that already governs accepting recommendations into drafts. No UUIDs surfaced - PO
by po_number, supplier/product/location by code, GR by its reference.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.schemas.scm_decisions import (
    BulkConfirmRequest,
    BulkConfirmResult,
    CreateGrResult,
)
from app.schemas.scm_orders import (
    PurchaseOrder,
    PurchaseOrderListResponse,
    PurchaseOrderUpdate,
    SupplierOption,
)
from app.services.error_handler import AppException
from app.services.scm.purchase_order_service import PurchaseOrderService

router = APIRouter()

_READ = require_permission_with_api_key("scm.dashboard.view")
_WRITE = require_permission_with_api_key("scm.reorder.run")


class BulkDeleteRequest(BaseModel):
    ids: List[str] = Field(default_factory=list)


class BulkDeleteResult(BaseModel):
    deleted: int
    #: Order-inquiry rows placed on one of the deleted POs' lines that were unplaced -
    #: put back on the board rather than left pointing at supply that no longer exists.
    unplaced_rows: int


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
    outstanding: Optional[bool] = Query(
        None,
        description=(
            "true = still expecting delivery (mirrors scm.po_ordered_v: status in "
            "active/received/partial/closed AND an open line with qty_ordered > "
            "qty_received); false = the complement (drafts, cancelled, fully received). "
            "Omitted = every status."
        ),
    ),
    allocated: Optional[bool] = Query(
        None,
        description=(
            "true = at least one order-inquiry row is linked to a line of this order; "
            "false = none is; omitted = every order. The same fact the `allocated_qty` "
            "column sums, so the filter and the figure cannot disagree."
        ),
    ),
    documents: Optional[str] = Query(
        None,
        description=(
            "Comma-separated purchase order numbers - keep only these. What the Order "
            "Inquiries page hands over when the buyer asks to see the book they just "
            "uploaded (AC-H13). Omitted = every order; naming none matches none."
        ),
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

    `outstanding` is the buyer's "at a glance" question (the captain, 20 Aug: "how do i know
    the open PO / outstanding PO") - the PO book's own `is_on_order` flag as a list filter,
    so it can never disagree with what a row's own badge says.

    `allocated` is the same shape of question for section 3.G: every row carries
    `allocated_qty`, the quantity order inquiries have already occupied on it, and this
    narrows the list to the orders that are, or are not, spoken for. WHO is on an order is
    the detail page's Allocated to panel - a list of 13,000 orders answers "is this one
    taken", never "by whom".

    `documents` is the narrowest of them: the exact orders one upload wrote, so "Open
    purchase orders" after a book lands shows that book and not the other 13,000.
    """
    return PurchaseOrderService(db).list(
        page, limit, sort, dir, query, status, supplier,
        product_code=product_code, outstanding=outstanding, allocated=allocated,
        documents=documents.split(",") if documents is not None else None,
    )


@router.post("/purchase-orders/bulk-confirm", response_model=BulkConfirmResult)
def bulk_confirm_purchase_orders(
    payload: BulkConfirmRequest = Body(...),
    db: Session = Depends(get_db),
    _user: dict = Depends(_WRITE),
):
    """Confirm draft POs → active + canonical PO number (M4-D6). Idempotent."""
    return PurchaseOrderService(db).bulk_confirm(payload.ids, (_user or {}).get("id"))


@router.post("/purchase-orders/bulk-delete", response_model=BulkDeleteResult)
def bulk_delete_purchase_orders(
    payload: BulkDeleteRequest = Body(...),
    db: Session = Depends(get_db),
    _user: dict = Depends(_WRITE),
):
    """Hard delete purchase orders (captain, 20 Aug: "give me an option to bulk delete
    purchase orders ... maybe need to recreate"). Any order-inquiry row placed on a
    deleted PO's line is unplaced first, not left dangling - see the service docstring.
    """
    return PurchaseOrderService(db).bulk_delete(payload.ids, (_user or {}).get("id"))


@router.post("/purchase-orders/{po_id}/create-gr", response_model=CreateGrResult)
def create_gr_from_purchase_order(
    po_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_WRITE),
):
    """Create a goods receipt from an active PO, stamping received qty (M4-D6)."""
    return PurchaseOrderService(db).create_gr(po_id, (_user or {}).get("id"))


@router.get("/purchase-orders/suppliers", response_model=List[SupplierOption])
def list_purchase_order_suppliers(
    query: Optional[str] = Query(
        None, description="Substring match on the supplier code or name."
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _user: dict = Depends(_READ),
):
    """Active suppliers, for the detail page's Supplier select. Declared before
    `/{po_id}` so `suppliers` never parses as a PO id.

    Gated on `scm.dashboard.view` (this router's read permission) rather than reusing
    `GET /procurement/suppliers/select`, for two reasons: that route sits behind the
    procurement module guard and its own permission, which a purchasing/SCM-only role does
    not necessarily hold, and it takes no `limit`/`offset` at all, so a paged picker cannot
    page it. Same reasoning, and same shape, as `/sales-orders/agents`.
    """
    return PurchaseOrderService(db).list_supplier_options(query, limit, offset)


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


@router.put("/purchase-orders/{po_id}", response_model=PurchaseOrder)
def update_purchase_order(
    po_id: str,
    data: PurchaseOrderUpdate,
    db: Session = Depends(get_db),
    _user: dict = Depends(_WRITE),
):
    """Correct a purchase order in place - header and lines, in one write.

    The supply-side twin of `PUT /sales-orders/{so_id}`. Until now this router had no write
    route beyond confirm / delete / create-GR, so a wrong supplier, a wrong date or a
    mistyped quantity could only be fixed by deleting the order and re-uploading the book.

    An omitted key leaves the stored value alone; one sent as `null` clears it. `lines`, when
    sent, upserts the whole array - see `PurchaseOrderService._upsert_lines`, including the
    409s that stop a received or claimed line being dropped.
    """
    return PurchaseOrderService(db).update(po_id, data)
