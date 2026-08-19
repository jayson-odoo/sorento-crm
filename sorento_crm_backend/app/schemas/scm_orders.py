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
    #: Who sold it, resolved from `sales_orders.sales_agent_id` (`sales_agents` master).
    #: The id is carried only so the detail page's edit select can pre-select the current
    #: agent - the code + label are what a person reads; never a bare UUID in the UI.
    sales_agent_id: Optional[str] = None
    sales_agent_code: Optional[str] = None
    #: `sales_agents.person_label` - the human this agent code belongs to. Absent when
    #: the agent has not been given one, which is most of the master today.
    sales_agent_label: Optional[str] = None
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
    #: Who sold it. Optional - most manual creates name no agent - applied as given.
    sales_agent_id: Optional[str] = None
    lines: List[SalesOrderLineInput] = Field(..., min_length=1)


class SalesOrderUpdate(BaseModel):
    order_type: Optional[str] = None
    customer_code: Optional[str] = None
    priority: Optional[str] = None
    requested_delivery_date: Optional[str] = None
    #: Optional[str], but read via `model_fields_set` in the service rather than a plain
    #: `is not None` check: a field the caller never sent must leave the stored agent alone,
    #: while one sent as an explicit `null` (or `""`) must CLEAR it. A plain `is not None`
    #: check cannot tell those two apart - both arrive as `None`.
    sales_agent_id: Optional[str] = None
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


class SalesAgentOption(BaseModel):
    """One `sales_agents` row, for the Agent filter and the detail page's Agent select.

    Served under `scm.dashboard.view` rather than `master_data.sales_agents.view` - the
    master's own CRUD permission - because a purchasing/SCM operator role can hold the
    former without the latter, and this route only ever reads.
    """

    id: str
    sales_agent: str
    person_label: Optional[str] = None
    location_group: Optional[str] = None


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


class ProductLastCost(BaseModel):
    """What we last paid for a SKU, and where to check it.

    `unit_cost` of 0 is a price OF zero; the ABSENCE of this whole block is what "we have
    never bought it" looks like. Keeping those apart is the point of the block existing.
    """

    unit_cost: float
    currency: Optional[str] = None
    po_number: str
    issue_date: Optional[str] = None
    supplier_name: Optional[str] = None


class PurchaseOrderListResponse(BaseModel):
    data: List[PurchaseOrder]
    empty: bool
    pagination: PurchaseOrderPagination
    # Present only when the caller narrowed the list to one product. A field missing from
    # this model is DROPPED from the response however carefully the service builds it -
    # which is exactly how this one went out silently the first time.
    product_cost: Optional[ProductLastCost] = None
