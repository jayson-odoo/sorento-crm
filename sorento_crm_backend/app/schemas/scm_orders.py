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
    # AutoCount SODTL pricing (Slice 8) — surfaced read-only; None on native rows.
    unit_price: Optional[float] = None
    discount_amt: Optional[float] = None
    tax_rate: Optional[float] = None
    tax_amt: Optional[float] = None
    sub_total: Optional[float] = None
    delivery_date: Optional[str] = None
    tax_code: Optional[str] = None


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
    lines: List[SalesOrderLine]
    created_at: str
    # AutoCount mirror (Slice 8): provenance gate + ingest-safe annotations.
    source: str = "manual"
    source_doc_no: Optional[str] = None
    internal_note: Optional[str] = None
    follow_up: bool = False


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
    # AutoCount PODTL extras (Slice 8) — surfaced read-only; None on native rows.
    unit_cost: Optional[float] = None
    description: Optional[str] = None
    sub_total: Optional[float] = None


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
    lines: List[PurchaseOrderLine]
    created_at: str
    # M4 Slice B — draft→confirm→GR flow
    is_on_order: bool = False
    source: str = "manual"           # autocount | recommendation | manual
    # AutoCount mirror (Slice 8): human DocNo + ingest-safe annotations.
    source_doc_no: Optional[str] = None
    internal_note: Optional[str] = None
    follow_up: bool = False
    gr_reference: Optional[str] = None


class PurchaseOrderPagination(BaseModel):
    total: int
    page: int


class PurchaseOrderListResponse(BaseModel):
    data: List[PurchaseOrder]
    empty: bool
    pagination: PurchaseOrderPagination
