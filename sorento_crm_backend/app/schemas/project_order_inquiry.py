"""Order inquiry schemas (P10, AC-I1 to AC-I7).

A row is one instruction to purchasing. It carries the sales order NUMBER rather than its
id, the item CODE rather than the product id, and the warehouse CODE rather than the
warehouse id, so nothing on this screen is a UUID a person has to resolve for themselves.

``remark`` is the same field the client's own spreadsheet calls REMARK: the verb in their
spelling, or the SPO reference itself for a row already on the water. It ships beside the
raw ``verb`` so the screen can colour by verb while printing what purchasing reads.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


class OrderInquiryLinkOut(BaseModel):
    """One placement on an order inquiry row (`projects.order_inquiry_links`, AC-I5).

    A row keeps its full quantity and carries a list of these, so "where is this linked" is
    answered once, by the ONE reader
    (`ProjectOrderInquiryService.links_for_rows`), for the worklist, the per-project list
    and the SCM sales-order detail alike.

    Everything here is what a person reads. `document` is the link's own copy of the
    number, which is why it survives the line it named being re-imported under a new id;
    `line_label` is `L3` only when the book numbered the line, and absent rather than
    invented when it did not - the LOCATION is what identifies the line then, and it is a
    fact. `po_id` addresses the PO popover and is null on an SPO link, because there is no
    purchase order to open.
    """

    id: str
    #: `po` or `spo`. Only an ORDER BACK row ever carries an `spo` link (part 2 4b).
    kind: str
    document: Optional[str] = None
    line_label: Optional[str] = None
    qty: str
    location: Optional[str] = None
    issue_date: Optional[date] = None
    expected_date: Optional[date] = None
    #: Q5's location fit, 1 to 5. Never a filter, only a rank - a link outside tier 1 is
    #: the split instruction the buyer keys into AutoCount, not a mistake.
    tier: Optional[int] = None
    #: The document arrives AFTER the row's own required date (AC-P3-7). Stated, never
    #: acted on: purchasing decides whether a late document is still the answer, and
    #: unlinking it here would take away the only cover the row has. Derived from the two
    #: dates rather than stored, so it can never go stale against either of them.
    late: bool = False
    auto: bool = False
    linked_at: Optional[datetime] = None
    #: WHO linked it, by name. Null on a cascade link, which nobody did by hand.
    linked_by_name: Optional[str] = None
    po_id: Optional[str] = None


class OrderInquiryRowOut(BaseModel):
    id: str
    order_inquiry_id: str
    so_line_id: Optional[str] = None
    project_sales_order_id: Optional[str] = None
    sales_order_ref: Optional[str] = None
    # AC-D06: the Project SO reference, its line number and the decision revision the Buy
    # came from. Absent on an amendment exception row, which no revision decided.
    project_so_ref: Optional[str] = None
    line_no: Optional[int] = None
    decision_revision: Optional[int] = None
    so_date: Optional[datetime] = None
    project_customer: Optional[str] = None
    is_amendment: bool = False

    item_code: Optional[str] = None
    qty: str
    delivery_date: Optional[date] = None
    # Empty when no allocation has been confirmed yet (AC-H5). Never defaulted.
    stock_location: Optional[str] = None
    verb: str
    remark: Optional[str] = None
    spo_ref: Optional[str] = None
    covered_by: Optional[str] = None
    note: Optional[str] = None
    # The FIRST link's document and line, kept as the one-word display the older readers
    # print. The TRUTH is `links` below: a row may sit on two lines of one purchase order
    # and on an SPO allocation at the same time, and a single column cannot say that.
    po_ref: Optional[str] = None
    po_line_id: Optional[str] = None
    #: The document CS NAMED for an order back. Not a link - it is what the walk tries
    #: FIRST, and a document this system does not hold is recorded rather than refused.
    cited_document: Optional[str] = None
    #: Every document this row's quantity sits on, oldest link first (AC-I5).
    links: List[OrderInquiryLinkOut] = []
    #: The sum of `links[].qty`. `qty - linked_qty` is what still flows to reorder
    #: planning, and is exactly what `scm.committed_v` now nets (migration 422).
    linked_qty: str = "0"
    # Whether this row has anywhere to link to at all (the captain, 20 Aug: a "Link PO"
    # offer with nothing behind it reads as a bug, not an empty state). Verb AND product,
    # not product alone: an ORDER BACK row may link to an `spo_allocations` row as well as
    # to a purchase order line, so a flag that only looked at purchase orders hid the Link
    # action on the one row the feature was built for. Computed with the SAME predicate
    # `po-candidates` answers, so the flag and the dialog can never disagree.
    has_link_candidate: bool = False

    state: str
    actioned_at: Optional[datetime] = None
    actioned_by_name: Optional[str] = None
    created_at: Optional[datetime] = None

    #: The HANDSHAKE (`PLAN-scm-oi-handshake.md`), beside `state` and never merged with
    #: it: `awaiting`, `acknowledged`, `changed` or `rejected`. Every one of the columns
    #: below is declared here because `response_model` silently drops a field it has not
    #: been told about, and the whole screen reads off them.
    ack_state: str = "awaiting"
    acknowledged_by_name: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    rejected_by_name: Optional[str] = None
    rejected_at: Optional[datetime] = None
    rejected_reason: Optional[str] = None
    #: When CS last amended a row purchasing had already acknowledged.
    changed_at: Optional[datetime] = None


class OrderInquiryDetail(BaseModel):
    id: str
    #: `OI-000001` - what a person calls this inquiry. Optional only so a record written
    #: before the column existed still reads; everything created since carries one.
    inquiry_no: Optional[str] = None
    project_sales_order_id: str
    amendment_id: Optional[str] = None
    state: str
    raised_at: Optional[datetime] = None
    # The purchasing task the rows are attached to (AC-I4).
    task_id: Optional[str] = None
    task_name: Optional[str] = None
    rows: List[OrderInquiryRowOut] = []


class OrderInquirySummary(BaseModel):
    total: int = 0
    raised: int = 0
    actioned: int = 0
    cancelled: int = 0


class OrderInquiryWorklistRow(BaseModel):
    """One instruction on purchasing's own list, in the spreadsheet's columns.

    Same vocabulary as the per-project row above - the sales order NUMBER, the item CODE,
    a quantity as a string - plus the three facts the cross-project view needs and the
    per-project one does not: which document to open (a core sales order for an adopted
    record, the project document for an authored one), who it is for when there is no
    project to name, and whether anybody has placed it yet.
    """

    id: str
    #: `OI-000123` - the number of the inquiry this row belongs to, off its own header.
    #: Optional only so a record written before the column existed still reads; every
    #: inquiry raised since carries one. The S/O no beside it does not answer the same
    #: question: an amendment raises a SECOND inquiry on the same sales order.
    inquiry_no: Optional[str] = None
    so_date: Optional[date] = None
    so_number: Optional[str] = None
    item_code: Optional[str] = None
    product_name: Optional[str] = None
    qty: str
    delivery_date: Optional[date] = None
    project_customer: Optional[str] = None
    # Blank until the row traces to a placed purchase order. Never a guess at who would
    # supply it: purchasing reads a filled cell as a statement that an order exists.
    supplier: Optional[str] = None
    supplier_id: Optional[str] = None
    po_number: Optional[str] = None
    # The location the PO is placed for: the donor to order back for an order-back row,
    # the confirmed allocation's warehouse for a plan/confirmed row, otherwise the line's
    # own fulfilment location. Blank when neither is known.
    location: Optional[str] = None
    # What flows to reorder planning, for this row's own SO line (the captain, 20 Aug: "show
    # the quantity, quantity taken from PO, and the remaining quantity, cause this is what
    # flows to reorder planning"). `taken_from_po` sums every SIBLING placed ORDER row on the
    # same line - the PO no cell links to one PO, but a line may have been covered across
    # several; `remaining_open` sums every raised ORDER row on the line, which is exactly
    # `committed_v`'s confirmed leg (`verb='ORDER' AND state='raised'`) - what still counts as
    # demand to the reorder engine. On a raised row that includes itself. `0` for a row with
    # no `so_line_id` (an amendment exception row traces to none).
    #
    # Both figures are scoped to `verb='ORDER'` SIBLINGS, always - including for a row whose
    # OWN verb is not `ORDER` (the captain, 21 Aug: an ADVANCE row read "Taken from PO 432 /
    # Remaining 0", technically correct about its ORDER siblings, but read as "handled" next
    # to an unactioned date change of its own). The frontend mutes these two cells with an
    # honest per-verb label instead of a figure whenever `verb != 'ORDER'`
    # (`orderInquiryWorklist.ts`'s `flowExclusionLabel`) - this schema still always ships the
    # real ORDER-sibling numbers, so nothing here needs to change to keep that true.
    taken_from_po: str = "0"
    remaining_open: str = "0"
    # Same as `OrderInquiryRowOut.has_link_candidate` - whether this row has anywhere to
    # link to, computed the same way so the two listings that render "Link PO" can never
    # disagree with the dialog.
    has_link_candidate: bool = False
    # Who sold it (`sales_orders.sales_agent_id` -> `sales_agents`), read off the same core
    # sales order the SO DATE / S/O NO columns already join to. Null on an authored row
    # that reaches no core order and on one whose core order carries no agent.
    agent_code: Optional[str] = None
    agent_label: Optional[str] = None
    state: str
    raised_at: Optional[datetime] = None
    # WHO told purchasing to buy THIS ROW, by name: the confirmer of the supply revision
    # that raised it (`supply_decision_id` -> `so_supply_decisions.confirmed_by`), falling
    # back to the inquiry header's `raised_by` for an amendment-born row that has no
    # revision. Never the header for a row that HAS one: the header is re-stamped on every
    # reconfirm, so it would print the latest reconfirmer beside an older row's own clock.
    # Never the id either - the column is printed as it comes. Null when nobody was
    # recorded, or the user has since been removed.
    raised_by_name: Optional[str] = None
    verb: str
    note: Optional[str] = None

    # Addressing only, never rendered.
    project_id: Optional[str] = None
    project_sales_order_id: Optional[str] = None
    core_sales_order_id: Optional[str] = None
    is_adopted: bool = False
    # The placed purchase order this row traces to (same coalesce the PO NO column reads),
    # so the "PO no" cell's popup can address `GET .../order-inquiries/po/{po_id}` without
    # a second lookup. Null on a row nobody has placed yet.
    po_id: Optional[str] = None
    #: Every document this row's quantity sits on (AC-I5), the SAME reader the per-project
    #: list and the SCM sales-order detail use. Empty on a row nobody has linked.
    links: List[OrderInquiryLinkOut] = []
    linked_qty: str = "0"
    #: The document CS cited on an order back, so the screen can say the walk honoured it.
    cited_document: Optional[str] = None

    #: The HANDSHAKE (`PLAN-scm-oi-handshake.md`), beside `state` and never merged with
    #: it: `awaiting`, `acknowledged`, `changed` or `rejected`. Every one of the columns
    #: below is declared here because `response_model` silently drops a field it has not
    #: been told about, and the whole screen reads off them.
    ack_state: str = "awaiting"
    acknowledged_by_name: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    rejected_by_name: Optional[str] = None
    rejected_at: Optional[datetime] = None
    rejected_reason: Optional[str] = None
    #: When CS last amended a row purchasing had already acknowledged.
    changed_at: Optional[datetime] = None


class OrderInquiryMonthTotal(BaseModel):
    month: str
    #: `JAN 26`, spelled the way their sheet tab is.
    label: str
    rows: int = 0
    qty: str = "0"


class OrderInquiryFacet(BaseModel):
    id: str
    label: str
    rows: int = 0


class OrderInquiryStateCounts(BaseModel):
    raised: int = 0
    #: Some of the quantity is on documents and the rest is still demand (section 3.I).
    partly_linked: int = 0
    actioned: int = 0
    cancelled: int = 0
    #: Wholly covered by links. Stored as `placed`, read as "Linked" (AC-I1). Declared
    #: here because `response_model` silently drops a key it has not been told about, and
    #: the service builds this dict off the rows themselves rather than off a fixed list.
    placed: int = 0
    total: int = 0


class OrderInquiryAckCounts(BaseModel):
    """The Acknowledgement filter's own four counts (`PLAN-scm-oi-handshake.md` section
    4), computed with the `ack` filter itself DROPPED - the same rule the month, supplier,
    project, raised-by and kind controls follow, so choosing one value leaves the other
    three readable.

    Declared field by field rather than left to the dict the service builds, because
    `response_model` drops a key it has not been told about.
    """

    awaiting: int = 0
    acknowledged: int = 0
    changed: int = 0
    rejected: int = 0


class OrderInquiryKindTotals(BaseModel):
    """The three cards above the schedule and the list (section 3.I2, AC-I11).

    Quantity, not row count: what a buyer acts on is how much is still to buy, and two
    rows of one and one row of two are the same day's work. Decimal STRINGS, like every
    quantity on this screen - a float round trip loses the tail of a quantity somebody
    signed for.

    Declared here rather than left to the dict the service returns, because
    `response_model` silently drops a key it has not been told about.
    """

    #: On SPO allocations already on their way.
    spo: str = "0"
    #: On purchase order lines.
    po: str = "0"
    #: Raised and on nothing - what still flows to reorder planning.
    buy: str = "0"


class OrderInquiryWorklistSummary(BaseModel):
    """The strip above the list, and the controls beside it.

    The totals honour every filter, the month included, because they describe what is on
    screen. Each axis drops its OWN filter, because a control that empties itself the
    moment it is used cannot be used a second time.
    """

    total_rows: int = 0
    total_qty: str = "0"
    by_state: OrderInquiryStateCounts = OrderInquiryStateCounts()
    by_month: List[OrderInquiryMonthTotal] = []
    suppliers: List[OrderInquiryFacet] = []
    projects: List[OrderInquiryFacet] = []
    #: The people who raised at least one of the rows in view, by the same rule the rows
    #: themselves use (their revision's confirmer, the header only when there is no
    #: revision) - the "Raised by" filter's own list. Never every user in the company: a
    #: picker whose entries mostly return nothing is a picker nobody uses twice.
    raised_by: List[OrderInquiryFacet] = []
    #: What the rows in view still need, per kind (AC-I11) - the cards' own figures.
    #: Computed with the `kind` filter dropped, like every other control here, so
    #: pressing one card leaves the other two readable.
    kinds: OrderInquiryKindTotals = OrderInquiryKindTotals()
    #: How many rows sit at each acknowledgement state (AC-H4), computed with the `ack`
    #: filter dropped for the same reason `kinds` drops its own.
    ack: OrderInquiryAckCounts = OrderInquiryAckCounts()


class AcknowledgeRowsRequest(BaseModel):
    """Purchasing takes on one row or a batch of them (AC-H2).

    Ids only: what an acknowledgement means is fixed - the rows become purchasing's work
    and the cascade runs for exactly them - so there is nothing else to say about it.
    """

    row_ids: List[str] = Field(..., min_length=1)


class AcknowledgeResult(BaseModel):
    """What one press did, in the two numbers the toast reports: how many rows were taken
    on, and how much of them found a document at that moment."""

    acknowledged: int = 0
    #: Rows the cascade linked, and how many placements it made across them. `0` is an
    #: ordinary answer: there may be nothing open to link to yet.
    linked_rows: int = 0
    links: int = 0


class RejectRowRequest(BaseModel):
    """Purchasing refuses a row, with a reason CS will read on the board cell.

    The reason is REQUIRED (AC-H5). A refusal with no reason sends CS back to a person to
    ask, which is the whole thing the board's "Rejected by X: Y" exists to stop.
    """

    reason: str = Field(..., min_length=1, max_length=1000)

    @model_validator(mode="after")
    def _reason_is_not_blank(self) -> "RejectRowRequest":
        if not (self.reason or "").strip():
            raise ValueError("Say why this row is being rejected.")
        return self


class LinkNowRequest(BaseModel):
    """Run the cascade over acknowledged rows now (AC-H13), optionally narrowed to the
    products an upload just touched. Omitted `product_ids` means every acknowledged or
    changed row that still has something unlinked."""

    product_ids: Optional[List[str]] = None


class MarkInquiryRowsRequest(BaseModel):
    row_ids: List[str] = Field(..., min_length=1)
    state: str = Field(..., description="raised, actioned or cancelled")


class OrderInquiryPoCandidateClaim(BaseModel):
    """One EXISTING tag already on this candidate's PO line - the row's expand (section G,
    "the captain, 20 Aug"). Read straight off the placed rows themselves: the tag IS the
    evidence, so there is nothing else to derive it from.
    """

    so_number: Optional[str] = None
    item_code: Optional[str] = None
    qty: str
    placed_date: Optional[datetime] = None


class OrderInquiryPoCandidate(BaseModel):
    """One open document line this row could be linked to (section 3.I).

    In the walk's own order, outermost key first: the document CS cited; then an SPO
    allocation before a purchase order line on an ORDER BACK row; then the location tier
    (Q5); then the purchase order's OWN issue date, then the line's expected date, then the
    document number (Q7). Location NEVER filters a candidate out - it only ranks it.

    `recommended` marks the first candidate whose `remaining` balance covers what the row
    still needs. `already_tagged` is what OTHER links already claim off this same line, so
    `remaining` is never a promise this line cannot keep, and `claims` names those other
    rows one by one.
    """

    #: `po` or `spo`. An `spo` candidate is offered to an ORDER BACK row and nothing else.
    kind: str = "po"
    #: The purchase order line, or the SPO allocation. Exactly one is set.
    po_line_id: Optional[str] = None
    spo_allocation_id: Optional[str] = None
    po_number: str
    line_label: Optional[str] = None
    #: Where that line lands the goods, and how well it fits the row's own location.
    location: Optional[str] = None
    tier: int = 5
    #: CS named this document on the order back, so the walk tried it before any other.
    cited: bool = False
    supplier_name: Optional[str] = None
    #: BOTH dates, because the cascade orders on the document's date first and the line's
    #: second (Q7) and a candidate list that showed one could not be checked against it.
    issue_date: Optional[date] = None
    expected_date: Optional[date] = None
    qty_ordered: str
    qty_received: str
    already_tagged: str
    remaining: str
    covers: bool
    recommended: bool = False
    # The line's own held price, when the PO carries one. Never a guess.
    unit_cost: Optional[str] = None
    currency: Optional[str] = None
    claims: List[OrderInquiryPoCandidateClaim] = []
    # What the cascade (G2, 20 Aug: "take from the earliest PO, then subsequently from
    # subsequent PO") would take off THIS line for THIS row - `0` when the cascade never
    # reaches this line (already covered by an earlier one, or nothing is left to cover).
    # Server-computed by the SAME walk `auto_place_for_products` runs, so the dialog's
    # preview and the auto pass can never disagree; the dialog offers it as an editable
    # starting point, not the only answer.
    default_take: str = "0"


class PlaceOnPoAllocation(BaseModel):
    """One line of a link: this row takes `qty` off ONE document line.

    Exactly one of the two ids is set, the same rule the link row's own CHECK constraint
    holds and the same rule `order_link_claim` follows for its purchase side.
    """

    po_line_id: Optional[str] = None
    spo_allocation_id: Optional[str] = None
    qty: str

    @model_validator(mode="after")
    def _names_exactly_one_target(self) -> "PlaceOnPoAllocation":
        if bool(self.po_line_id) == bool(self.spo_allocation_id):
            raise ValueError(
                "Name a purchase order line or an SPO allocation, not both and not neither."
            )
        return self


class PlaceOnPoRequest(BaseModel):
    po_line_id: Optional[str] = Field(
        None, description="Single-target link: one purchase order line, whole remainder."
    )
    # Several document lines can cover one row. Mutually exclusive with `po_line_id` - a
    # caller either names one line directly or hands over the whole allocation.
    allocations: Optional[List[PlaceOnPoAllocation]] = Field(
        None,
        description=(
            "Link across one or more lines: {po_line_id | spo_allocation_id, qty}."
        ),
    )

    @model_validator(mode="after")
    def _names_something_to_place(self) -> "PlaceOnPoRequest":
        if not self.po_line_id and not self.allocations:
            raise ValueError("Name a purchase order line, or a list of allocations.")
        return self


class AutoPlaceRequest(BaseModel):
    """Run the cascade now - the worklist's own "Auto-link". Omitted `product_ids` means
    every product that currently has a raised or partly linked ORDER / RESERVE & ORDER /
    ORDER BACK row."""

    product_ids: Optional[List[str]] = None


class UnlinkRequest(BaseModel):
    """Unlink. With a `link_id` that ONE link goes and the row keeps its others; without
    one every link the row holds goes, which is what the whole-row action means."""

    link_id: Optional[str] = None


class AutoPlaceResult(BaseModel):
    placed_rows: int = 0
    allocations: int = 0
    products_touched: int = 0


class UnplaceAllRequest(BaseModel):
    """"Unplace all" for the CURRENT worklist scope (the captain, 20-21 Aug: it operates
    on whatever the list is filtered to - one product when the filters happen to narrow
    to one, every placed row when they do not). The SAME filter shape `GET
    /order-inquiries` takes, minus `state` - this is always about placed rows, whatever
    else is filtered - and no `product_ids`: the worklist paginates server-side, so a
    client-derived product list would silently miss rows behind page 1. Every field
    omitted means every placed row in the company.
    """

    query: Optional[str] = None
    delivery_month: Optional[str] = None
    raised_date: Optional[str] = None
    project_id: Optional[str] = None
    supplier_id: Optional[str] = None
    #: The user whose inquiries the list is narrowed to, so the action can never reach
    #: further than what the person pressing it can see.
    raised_by: Optional[str] = None


class UnplaceAllResult(BaseModel):
    unplaced: int = 0


class UnplaceAllPreview(BaseModel):
    """The confirm dialog's own numbers, resolved server-side against the SAME filters
    `unplace-all` itself reads - never derived from whatever page of the worklist happens
    to be loaded in the browser. `product_code`/`product_name` are set only when EVERY
    matching row resolves to the same product; otherwise both stay null and the dialog
    speaks only of the count."""

    count: int = 0
    product_code: Optional[str] = None
    product_name: Optional[str] = None


class OrderInquiryPoDetailLine(BaseModel):
    """One line of the purchase order behind a placed worklist row - the "PO no" cell's
    popup (the captain, 20 Aug). Read straight off `purchase_order_lines`, never netted
    against other rows' claims - that reading belongs to the "Place on PO" candidates,
    not to a plain look at what was ordered."""

    sku: Optional[str] = None
    product_name: Optional[str] = None
    qty_ordered: str
    qty_received: str
    remaining: str
    location: Optional[str] = None


class OrderInquiryPoDetail(BaseModel):
    """The PO popup's whole answer: the header purchasing already reads off the sheet,
    plus every line, not only the one this row happened to be tagged to."""

    id: str
    po_number: str
    supplier_code: Optional[str] = None
    supplier_name: Optional[str] = None
    expected_date: Optional[date] = None
    status: str
    lines: List[OrderInquiryPoDetailLine] = []
