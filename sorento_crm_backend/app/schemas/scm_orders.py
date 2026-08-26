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

class SalesOrderLineInquiry(BaseModel):
    """The order inquiry covering one sales-order line, in the two words a person reads.

    The ROW's state, not the header's: "purchasing placed this line" is what the column
    answers, and a header sitting at `raised` while its row has been placed on a PO would
    say the opposite.
    """

    #: `OI-000123`. Null only on a row raised before inquiries were numbered.
    inquiry_no: Optional[str] = None
    state: str


class SalesOrderLineSupplyComponent(BaseModel):
    """One piece of a line's supply, in the vocabulary the planning board reads
    (`PLAN-scm-cs-planning-uat.md` section 2).

    The COMPONENTS, never a sentence: the words ("Use shared stock 71 from BRW") are written
    in one place, `project-sales/_shared/lib/supplyVocabulary.ts`, and a sentence composed
    here would be a second implementation of the same vocabulary drifting against the board.

    `rung` is what decides the words - never the warehouse code, which reads `BRW-BB` and
    `BRW` as the same site when they are the agent's own location and the shared pool.
    """

    kind: str
    qty: str
    #: The warehouse this piece is drawn from, by CODE. `None` for a Buy, which is held
    #: nowhere yet.
    source_location: Optional[str] = None
    #: `pool` / `group_take` / `group_borrow` / `cross_group_borrow` / `incoming` / `buy`.
    #: `None` on a component frozen before the rung was recorded.
    rung: Optional[str] = None
    #: The sales order a borrow was taken FROM, when one was named. What tells a borrow from
    #: another order apart from a borrow of free stock elsewhere.
    donor_so_number: Optional[str] = None


class SalesOrderLineLink(BaseModel):
    """One link on the order inquiry row covering a sales order line (AC-I9).

    A subset of `OrderInquiryLinkOut`: what a LINE's column needs to say where its Buy
    sits, and nothing about who linked it or when, which the order inquiry screen owns.
    Never an id on screen - the document number and the line label are what a person
    reads, and `line_label` is absent rather than invented when the book numbered nothing.
    """

    #: `po` or `spo`. Only an ORDER BACK row ever carries an `spo` link (part 2 4b).
    kind: str
    document: Optional[str] = None
    line_label: Optional[str] = None
    qty: str
    location: Optional[str] = None
    expected_date: Optional[str] = None


class SalesOrderLine(BaseModel):
    id: str
    sku: str
    product_name: str
    qty_ordered: float
    qty_delivered: float
    #: What is still to go out on this line: `ordered - delivered`, floored at 0, and **0 on a
    #: CLOSED line whatever those two say**. A book re-upload closes a line by absence without
    #: knowing what shipped, so `qty_delivered` stays 0 and the subtraction alone would report
    #: the whole quantity as still owed on an order that is done. Stated here rather than
    #: recomputed on the client so the grid, its footer and the header cannot disagree.
    outstanding_qty: float = 0
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
    #: What has already been PLANNED about this line, and how far purchasing has got with
    #: it: the inquiry row covering the line through the planning record's mirror
    #: (`projects.sales_order_lines.core_sales_order_line_id`). `None` when nobody has
    #: raised one - never an empty object, because "nobody was told about this line" and
    #: "told, about nothing" are different answers.
    #:
    #: Sent on the SINGLE order read only. The list has no column for it and would pay two
    #: more queries a page for a fact nothing there prints.
    order_inquiry: Optional[SalesOrderLineInquiry] = None
    #: Which confirmed revision decided supply for this line: the ACTIVE decision's
    #: `revision_no` when its `line_snapshots` name this core line, `None` otherwise.
    #:
    #: Per LINE and not per order, because since `PLAN-fulfilment-planning-from-autocount
    #: -so.md` 13.4 a confirmation covers the SUBSET the planner chose - an order with an
    #: active revision can still hold lines nobody has decided, and a header-level answer
    #: would report those as settled.
    decision_revision: Optional[int] = None
    #: What was DECIDED for this line and what the engine had SUGGESTED, as components
    #: (AC-D4). Both read off the active revision's snapshot for this line.
    #:
    #: `supply_decided` is `None` on a line no active revision covers - the same answer
    #: `decision_revision` gives, for the same reason. `supply_proposed` is `None` for that
    #: AND for a revision written before the proposal was frozen: "not recorded" and "the
    #: engine suggested nothing" are different answers, and an empty list would claim the
    #: second.
    #:
    #: An undecided line carries no suggestion here on purpose: the live ladder is the
    #: planning board's read, and running it per line on a detail page of 300 lines would be
    #: 300 engine walks for a column the board already answers.
    supply_decided: Optional[List[SalesOrderLineSupplyComponent]] = None
    supply_proposed: Optional[List[SalesOrderLineSupplyComponent]] = None
    #: WHERE this line's Buy sits (AC-I9): every link on the order inquiry row covering
    #: the line, PO or SPO, with the quantity each holds. Read off the SAME child table
    #: (`projects.order_inquiry_links`) the order inquiry worklist's "Linked to" column
    #: and the PO occupancy panel read, through the one reader, so the three surfaces
    #: cannot answer differently.
    #:
    #: `[]` when a row covers the line and nothing has been linked yet; `None` when no row
    #: covers it at all. The two are different answers - "nothing has been linked" against
    #: "nobody was told about this line" - and the column prints each in its own words.
    linked_to: Optional[List[SalesOrderLineLink]] = None


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
    #: Every DISTINCT date this order's LINES are due on (`sales_order_lines.required_date`),
    #: earliest first. Empty when no line names one, because an order nobody dated is not
    #: due today. This is what the list's "Delivery date" column shows - one order routinely
    #: ships on several days, so the header's own `requested_delivery_date` (a different
    #: figure, and blank on most of this book) could never answer "when is this due". That
    #: field is unchanged and still on the detail page.
    #:
    #: A LIST, not the `delivery_date_from`/`_to` span it replaced: an order due on the 12th
    #: of January and the 10th of March is due on two days, and printing it as a range
    #: claims a stretch of eight weeks nothing in the data says. The list's sort key keeps
    #: the old name (`min(required_date)` under `delivery_date_from`) because that is the
    #: column's id, and renaming it drops every saved column layout that names it.
    delivery_dates: List[str] = Field(default_factory=list)
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
    #: The order inquiries raised against this order, on BOTH the list and the single read.
    #: Empty for an order nobody has planned - the business sees sales orders and order
    #: inquiries and nothing between them, so this is where an order says what has been
    #: done about it.
    order_inquiries: List[SalesOrderInquiry] = Field(default_factory=list)
    created_at: str


class LinkedPurchaseOrder(BaseModel):
    """A pairing this sales order's lines claim, and whether both sides are present."""

    po_number: str
    item_code: Optional[str] = None
    resolved: bool = False


class SalesOrderInquiry(BaseModel):
    """One order inquiry raised against this sales order.

    By NUMBER (`OI-000001`), never by id: this is what the screen prints and links from.
    `rows_placed` against `rows_total` is how far purchasing has got with it - the one fact
    a buyer looking at the sales order actually wants, and the reason the column is not
    just a list of numbers.
    """

    inquiry_no: Optional[str] = None
    state: str
    raised_at: Optional[str] = None
    #: Who raised it, resolved to a person's name. Null when nobody was recorded.
    raised_by_name: Optional[str] = None
    rows_total: int = 0
    rows_placed: int = 0


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


# --- purchase orders --------------------------------------------------------

class PurchaseOrderLine(BaseModel):
    id: str
    sku: str
    product_name: str
    qty_ordered: float
    qty_received: float
    #: What is still to ARRIVE on this line: `ordered - received`, floored at 0, and **0 on a
    #: CLOSED line whatever those two say**. A book re-upload closes a line by absence without
    #: knowing what arrived, so `qty_received` stays 0 and the subtraction alone would report
    #: the whole quantity as still coming on an order that is done. Distinct from the header's
    #: `open_qty`, which is SUPPLY and ignores receipts.
    outstanding_qty: float = 0
    #: The line's own override when the book stated one, otherwise the product's base unit.
    uom: str
    #: What we pay for this line, and what the supplier's document states about it.
    #: `Decimal`, never `float`: money read back through a float is how RM 985.00 becomes
    #: 984.9999999. All three are `None` when the file said nothing - a 0 discount claims a
    #: discount of nothing was given, and a 0 total claims the goods were free.
    #:
    #: `unit_price` is the `unit_cost` COLUMN under the name the sales-order screen uses for
    #: the same fact. The two grids are one click apart in the same menu, and two names for
    #: one figure is how two screens start disagreeing about the same number.
    unit_price: Optional[Decimal] = None
    discount: Optional[Decimal] = None
    line_total: Optional[Decimal] = None
    #: The currency the three figures above are in. The book is mostly USD.
    currency: Optional[str] = None
    #: Where this line lands. Per line: one order routinely arrives into two locations.
    #: The serializer has emitted this since the header Warehouse field was dropped, and
    #: `response_model` silently discarded it for want of this declaration.
    warehouse_code: Optional[str] = None
    #: `open` or otherwise. A line that has left the order book is not incoming supply
    #: however much quantity it still shows. Emitted by the serializer, likewise dropped.
    line_status: str = "open"
    #: When this line's goods are due. Per line, for the same reason as the location.
    expected_date: Optional[str] = None


class PurchaseOrderPlacement(BaseModel):
    """One order-inquiry placement sitting on a purchase-order line (section 3.G, AC-G1).

    Every field is a NAME. The inquiry by its number, the sales order by its document
    number, the customer and the agent by the labels the order-inquiry worklist already
    prints for them - a UUID on this panel would tell the buyer nothing they could act on.
    """

    #: `OI-000006`. Null only on a row raised before the numbering stamp existed.
    inquiry_no: Optional[str] = None
    #: The sales order this quantity is owed to - its AutoCount number where it has one.
    so_number: Optional[str] = None
    customer: Optional[str] = None
    #: Who sold it, by person label, falling back to the agent code.
    agent: Optional[str] = None
    qty: float = 0.0
    #: Where the demand needs it: `order_inquiry_rows.stock_location`.
    needed_at: Optional[str] = None
    #: True when `needed_at` is not the PO line's own location - the PO line says DC1 and
    #: the demand is at BRW-BB. That difference IS the split instruction for AutoCount,
    #: which is why it is a mark on the row rather than a filter that hides it.
    location_differs: bool = False


class PurchaseOrderLineAllocation(BaseModel):
    """One purchase-order line's occupancy: the three figures, then who is on it (AC-G1)."""

    #: Which line this belongs to, matched against `PurchaseOrderLine.id`.
    line_id: str
    sku: str
    #: The PO LINE's own location, so the panel can say what the demand differs from.
    warehouse_code: Optional[str] = None
    #: What is still to ARRIVE on the line - the same rule `PurchaseOrderLine` prints.
    outstanding: float = 0.0
    #: The sum of every live order-inquiry link on this line.
    allocated: float = 0.0
    #: `outstanding - allocated`, floored at 0. A line promised more than it has left is
    #: over-committed, which is a finding for the buyer, not a credit to spend twice.
    free: float = 0.0
    placements: List[PurchaseOrderPlacement] = Field(default_factory=list)


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
    #: What is still to ARRIVE across the order, summed off the per-line rule above. Not the
    #: same figure as `open_qty`: that one is supply and counts a whole open line however much
    #: of it has already been received.
    outstanding_qty: float = 0.0
    #: What the order is WORTH, summed from its own lines: each line's stated `line_total`
    #: where it has one, otherwise `unit_cost * qty_ordered - discount`. `None` when not one
    #: line carries money, which is not the same as 0 - an order nobody priced is not an
    #: order worth nothing. The same rule the sales book's own `total_amount` follows.
    total_amount: Optional[Decimal] = None
    #: The currency the order is written in, from the header or, failing that, its first
    #: priced line. Blank on rows predating the book having more than one.
    currency: Optional[str] = None
    lines: List[PurchaseOrderLine]
    #: What order inquiries have OCCUPIED on this order, one entry per line carrying at
    #: least one placement (section 3.G). Empty on the LIST, which does not pay for the
    #: placement query per row; populated on the single read, which is where the panel is.
    allocations: List[PurchaseOrderLineAllocation] = Field(default_factory=list)
    #: The sum of every placement across the whole order - on the list as well as the
    #: single read (AC-G4). Declared here or `response_model` drops it, which is exactly
    #: how a carefully built figure goes out missing.
    allocated_qty: float = 0.0
    created_at: str
    # M4 Slice B - draft→confirm→GR flow
    is_on_order: bool = False
    source: str = "manual"           # recommendation | import | manual
    gr_reference: Optional[str] = None


class PurchaseOrderLineInput(BaseModel):
    #: The existing line's id, when the caller has one. Optional - a brand-new line has
    #: none yet. When present, `update` matches on it FIRST rather than falling back to SKU,
    #: so an edited line keeps its id (and therefore its `qty_received`, its `source_system`
    #: and any goods receipt pointing at it) instead of being read as "delete this one,
    #: insert a new one".
    id: Optional[str] = None
    sku: str
    qty_ordered: float = Field(..., gt=0)
    #: Optional[str], read via `model_fields_set` (not `is not None`) in `_upsert_lines` -
    #: an omitted key leaves the line's stored override alone (falling back to the product's
    #: base UOM on read), while an explicit `null`/`""` clears the override.
    uom: Optional[str] = Field(None, max_length=100)
    #: Which warehouse this line lands in, by CODE - never the UUID, matching `sku` /
    #: `supplier_code` elsewhere on this schema. Same `model_fields_set` semantics as `uom`.
    #: An unknown code is a 404.
    warehouse_code: Optional[str] = None
    #: When this line's goods are due. ISO `yyyy-mm-dd`; same semantics again.
    expected_date: Optional[str] = None
    #: What we pay, and what came off it. Same `model_fields_set` semantics as `uom` above:
    #: a qty-only edit that never sends these keys must not wipe a cost the book imported,
    #: while an explicit `null` clears the figure. `unit_price` writes the `unit_cost`
    #: column - see `PurchaseOrderLine`. `line_total` is deliberately NOT writable: it is
    #: what the supplier's document charged.
    unit_price: Optional[Decimal] = None
    discount: Optional[Decimal] = None


class PurchaseOrderUpdate(BaseModel):
    #: When the order was raised (`purchase_orders.issue_date`), under the name the screen
    #: shows. Correctable because the imported book got it from a spreadsheet and
    #: `scm.receipt_lead_v` measures the supplier's lead time from this column, so a wrong
    #: one skews every safety stock computed from it. ISO `yyyy-mm-dd`.
    order_date: Optional[str] = None
    #: When the goods are expected. Read via `model_fields_set`: sent as `null` it CLEARS.
    expected_date: Optional[str] = None
    #: The supplier, by code. An unknown code is a 404 rather than a silent unlink.
    supplier_code: Optional[str] = None
    lines: Optional[List[PurchaseOrderLineInput]] = None


class SupplierOption(BaseModel):
    """One `suppliers` row, for the detail page's Supplier select.

    Served under `scm.dashboard.view` rather than the procurement master's own permission,
    for the same reason `SalesAgentOption` is: a purchasing/SCM operator role can hold the
    former without the latter, and this route only ever reads.
    """

    supplier_code: str
    supplier_name: str


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
