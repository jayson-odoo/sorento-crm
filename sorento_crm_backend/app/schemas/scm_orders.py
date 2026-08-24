"""SCM M1 sales-order + purchase-order schemas.

Mirror the FE contract in ``services/salesOrderService.ts`` /
``purchaseOrderService.ts`` + ``types/scm.types.ts``. No UUIDs surface - SO by
so_number, PO by po_number; customer / product / supplier / warehouse resolved to
human codes/names. PO is read-only at M1 (create/confirm/receive land in M4).
"""
from __future__ import annotations

from decimal import Decimal
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
    #: What the customer pays for this line, and what the sales book states about it.
    #: `Decimal`, never `float`: money read back through a float is how RM 985.00 becomes
    #: 984.9999999. All three are `None` when the file said nothing - a 0 discount claims a
    #: discount of nothing was given, and a 0 total claims the line was free.
    unit_price: Optional[Decimal] = None
    discount: Optional[Decimal] = None
    line_total: Optional[Decimal] = None
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
    #: What the order is WORTH, summed from its own lines: each line's stated `line_total`
    #: where it has one, otherwise `unit_price * qty_ordered - discount`. `None` when not one
    #: line carries money, which is not the same as 0 - an order nobody priced is not an
    #: order worth nothing, and 15,000 of the absorbed rows are exactly that.
    total_amount: Optional[Decimal] = None
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
    #: The planning class this order was classified into (`project` / `retail`), or `None`
    #: when nobody has ever said. See `app.services.scm.demand_class`. Distinct from
    #: `order_type_label`, which names the ERP document type and is blank on almost every
    #: row - this is what the list's "Type" column actually shows.
    demand_class: Optional[str] = None
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
    #: The existing line's id, when the caller has one (e.g. an in-place qty edit on an
    #: already-saved order). Optional - a brand-new line naturally has none yet, and the FE
    #: form used to create/replace a whole order never has one either. When present, `update`
    #: matches on it FIRST rather than falling back to SKU, so an edited line keeps its id
    #: (and therefore `qty_delivered` / `source_system` / any reconciled link) instead of
    #: being read as "delete this one, insert a new one".
    id: Optional[str] = None
    sku: str
    qty_ordered: float = Field(..., gt=0)
    #: Optional[str], read via `model_fields_set` (not `is not None`) in `_upsert_lines` -
    #: an omitted key leaves the line's stored override alone (falling back to the
    #: product's base UOM on read), while an explicit `null`/`""` clears the override.
    uom: Optional[str] = Field(None, max_length=100)
    #: Which warehouse this line ships from, by CODE - never the UUID, matching `sku` /
    #: `customer_code` elsewhere on this schema. Same `model_fields_set` semantics as
    #: `uom`: omitted leaves the line's warehouse alone, sent (including `null`/`""`)
    #: clears it, a known code resolves and sets it. An unknown code is a 404.
    warehouse_code: Optional[str] = None
    #: When this line's quantity is due - the SAME column the detail page shows and labels
    #: "Delivery date" (`sales_order_lines.required_date`). The table also carries a
    #: never-mapped `delivery_date` column that nothing reads or shows and is deliberately
    #: left that way here, so this edits the column the FE already displays under that
    #: label. ISO `yyyy-mm-dd`; same `model_fields_set` semantics as `uom` / `warehouse_code`.
    required_date: Optional[str] = None
    #: What the customer pays, and what came off it. Same `model_fields_set` semantics as
    #: `uom` above: a qty-only edit that never sends these keys must not wipe a price the
    #: book imported, while an explicit `null` clears the figure. `Decimal`, so a price the
    #: browser sent as `88.5` is stored as 88.50 rather than a float's near-miss.
    unit_price: Optional[Decimal] = None
    discount: Optional[Decimal] = None


class SalesOrderFormData(BaseModel):
    order_type: str
    customer_code: str
    priority: str = "normal"
    requested_delivery_date: Optional[str] = None
    #: Who sold it. Optional - most manual creates name no agent - applied as given.
    sales_agent_id: Optional[str] = None
    lines: List[SalesOrderLineInput] = Field(..., min_length=1)


class SalesOrderUpdate(BaseModel):
    #: The ERP document type. Kept for anything that still sends it (n8n, the older form):
    #: it is written as given AND, when it says something the vocabulary recognises, it
    #: rewrites `demand_class` from it. The detail screen no longer uses it - see below.
    order_type: Optional[str] = None
    #: The planning class, under its own name. The detail page RENDERS this column
    #: (project / retail / Unclassified) and used to EDIT `order_type`, which is NULL on
    #: 96% of this book - so the value shown and the value written were different columns
    #: and the round trip could not be honest. Blank (omitted, `null` or `""`) leaves the
    #: stored classification alone rather than clearing it: "nobody said" is not a class,
    #: and a header edit must not un-rank an order as a side effect. A word outside the
    #: closed vocabulary is a 400 naming the words the fulfilment policy can weigh.
    demand_class: Optional[str] = None
    customer_code: Optional[str] = None
    priority: Optional[str] = None
    #: When the order was raised. Correctable because the absorbed book got it from a
    #: spreadsheet and the demand trend reads 24 months of this column. ISO `yyyy-mm-dd`.
    order_date: Optional[str] = None
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
    # M4 Slice B - draft→confirm→GR flow
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
