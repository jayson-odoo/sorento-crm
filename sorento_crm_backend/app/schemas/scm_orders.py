"""SCM M1 sales-order + purchase-order schemas.

Mirror the FE contract in ``services/salesOrderService.ts`` /
``purchaseOrderService.ts`` + ``types/scm.types.ts``. No UUIDs surface — SO by
so_number, PO by po_number; customer / product / supplier / warehouse resolved to
human codes/names. PO is read-only at M1 (create/confirm/receive land in M4).
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


# --- sales orders -----------------------------------------------------------

class SalesOrderLine(BaseModel):
    id: str
    sku: str
    product_name: str
    qty_ordered: float
    qty_delivered: float
    uom: str
    #: Where this line ships from. Per line: one order can land in two locations.
    warehouse_code: str = ""
    #: `open` or `closed`. A closed line is not a commitment however much it still shows.
    line_status: str = "open"
    #: When this line's quantity is due. Per line, for the same reason as the location.
    required_date: Optional[str] = None


class SalesOrder(BaseModel):
    id: str
    so_number: str
    order_type: str
    order_type_label: str
    customer_code: str
    customer_name: str
    market_segment: Optional[str] = None
    priority: str
    status: str
    order_date: str
    requested_delivery_date: Optional[str] = None
    total_qty: float
    committed_qty: float
    #: What the order says, and how much of it is still open. Both, because a total that
    #: silently means "outstanding" reads as an empty order once everything has shipped.
    line_count: int = 0
    open_line_count: int = 0
    lines: List[SalesOrderLine]
    #: Where the order came from: `inquiry` (the Order Inquiry sheet created it), `upload`
    #: (CS's outstanding extract), or `manual`. It decides who may edit the figures.
    source: str = "manual"
    #: The project the sheet named when no customer of that name existed.
    internal_note: Optional[str] = None
    #: Every distinct location its lines ship from. Plural: one order can land in two.
    stock_locations: List[str] = Field(default_factory=list)
    #: The purchase orders its lines wait on, each with whether the pairing is resolved.
    #: Present on the LIST (attached in one query per page); absent on a single read.
    linked_purchase_orders: List[LinkedPurchaseOrder] = Field(default_factory=list)
    awaiting_purchase_orders: int = 0
    created_at: str


class LinkedPurchaseOrder(BaseModel):
    """A pairing this sales order's lines claim, and whether both sides are present."""

    po_number: str
    item_code: Optional[str] = None
    resolved: bool = False


class SalesOrderLineInput(BaseModel):
    sku: str
    qty_ordered: float = Field(..., gt=0)
    uom: str = ""


class SalesOrderFormData(BaseModel):
    order_type: str
    customer_code: str
    priority: str = "normal"
    requested_delivery_date: Optional[str] = None
    lines: List[SalesOrderLineInput] = Field(..., min_length=1)


class SalesOrderUpdate(BaseModel):
    order_type: Optional[str] = None
    customer_code: Optional[str] = None
    priority: Optional[str] = None
    requested_delivery_date: Optional[str] = None
    lines: Optional[List[SalesOrderLineInput]] = None


class SalesOrderPagination(BaseModel):
    total: int
    page: int


class SalesOrderListResponse(BaseModel):
    data: List[SalesOrder]
    empty: bool
    pagination: SalesOrderPagination


class CreateDoResponse(BaseModel):
    sales_order: SalesOrder
    do_number: str


# --- purchase orders (read-only at M1) --------------------------------------

class PurchaseOrderLine(BaseModel):
    id: str
    sku: str
    product_name: str
    qty_ordered: float
    qty_received: float
    uom: str


class PurchaseOrder(BaseModel):
    id: str
    po_number: str
    supplier_code: str
    supplier_name: str
    warehouse_code: Optional[str] = None
    warehouse_name: Optional[str] = None
    status: str
    order_date: str
    expected_date: Optional[str] = None
    total_qty: float
    line_count: int
    #: What the PO still contributes as incoming supply, as distinct from what the order
    #: says. Zero on a fully-received or historical order, which is the point.
    open_qty: float = 0.0
    open_line_count: int = 0
    lines: List[PurchaseOrderLine]
    created_at: str
    # M4 Slice B — draft→confirm→GR flow
    is_on_order: bool = False
    source: str = "manual"           # recommendation | import | manual
    gr_reference: Optional[str] = None


class PurchaseOrderPagination(BaseModel):
    total: int
    page: int


class PurchaseOrderListResponse(BaseModel):
    data: List[PurchaseOrder]
    empty: bool
    pagination: PurchaseOrderPagination
