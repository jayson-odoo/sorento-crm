"""The multi-order planning board's wire shapes (PLAN section 13).

Transcribed field for field from the Phase 1 types the frontend was built against
(`sorento_crm_frontend/app/(protected)/project-sales/_shared/types/fulfilmentPlanning.types.ts`).
The conventions are the ones the supply schemas next door already keep: quantities are decimal
STRINGS, and the screen reads codes rather than identifiers - sales-order NUMBER, item CODE,
warehouse CODE. The two id fields that exist (`sales_order_id` on a contribution and on a
standing) are addressing only, the same way `SupplyComponent.source_warehouse_id` is.

Two field names are deliberately camelCase, `dateBuckets` and `productRows`, and they are the
only ones. The board names its axes for what they are ON SCREEN, because the delivery-schedule
matrix next door uses `column` to mean a PRODUCT - its API's inherited word, kept even after
that grid was transposed - and two grids using one word for opposite things is worse than one
pair of odd-looking field names.
"""
from __future__ import annotations

from datetime import date
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

BoardGranularity = Literal["day", "week", "month"]
BoardBucketKind = Literal["dated", "no_date"]
BoardSourceKind = Literal["reserve", "timely_spo", "buy", "unplannable"]


class BoardDateBucket(BaseModel):
    """One column: a period, or the one column that is not a period.

    There is no aggregate for the past. Every dated line buckets by its OWN period whether that
    period is past or future, because lumping three years of late demand into one column
    destroys the schedule the board exists to show. `is_past` is how the information survives
    the lumping being removed.
    """

    key: str
    kind: BoardBucketKind
    #: What the column header reads, already formatted. `No date` is not a bucket of time at
    #: all and carries no start.
    label: str
    start: Optional[date] = None
    #: This bucket's whole period ended before `as_of`, so the screen can tint it. The period
    #: CONTAINING `as_of` is not past: some of its dates are still to come. Always false for
    #: `no_date` - an absent date has not passed, it is simply absent.
    is_past: bool = False


class BoardRankFactor(BaseModel):
    """One weighted factor behind a row's rank.

    `present: false` means the value was unknown and the factor was dropped from BOTH sums,
    never scored as zero: an unknown is not a bad score, and treating it as one is how a
    ranking starts lying. A zero WEIGHT is still reported, so "this counted for nothing" is
    visible rather than inferred.
    """

    key: str
    weight: float
    value: Optional[float] = None
    present: bool
    #: The ABSOLUTE fact behind the normalised value, as text: this line's required date, this
    #: order's document date, this customer's terms, this order's demand class. Shown FIRST,
    #: with the normalised value secondary - on its own a 0.00 beside a 1.00 explains nothing,
    #: and under a policy that weights nothing a demand row carries every score is 0.00, which
    #: reads as a broken feature rather than as a rule saying nothing. Null when absent.
    raw: Optional[str] = None


class BoardSource(BaseModel):
    kind: BoardSourceKind
    qty: str
    #: Warehouse code for a Reserve; null for Buy, which has no location by definition.
    location: Optional[str] = None
    #: Addressing only, never rendered: `POST /sales-orders/{pso_id}/confirm` names a Reserve
    #: component's warehouse by ID (`lines[].reserve[].warehouse_id`) while the screen names it
    #: by code, so the pair has to travel together. Null for Buy and for an unplannable row.
    warehouse_id: Optional[str] = None
    #: The sentence the rule wrote, shown beside the quantity. Never a bare code.
    reason: str
    spo_number: Optional[str] = None
    arrival_date: Optional[date] = None


class BoardContribution(BaseModel):
    """One contributing sales-order line inside a cell: a row of the breakdown table."""

    #: Stable draft key, and part of the contract because the frontend rebuilds it:
    #: `${sales_order_id}|${line_no}|${item_code}|${bucket_key}`. Addressing only.
    key: str
    sales_order_id: str
    #: The MIRROR line id, which is how `confirm` names a line (`lines[].project_line_id`):
    #: the service builds its index from the planning record's own lines and refuses anything
    #: else. NULL until somebody adopts this sales order - there is no planning record yet, and
    #: a null is the honest answer rather than an absent key the screen has to interpret.
    project_line_id: Optional[str] = None
    so_number: str
    customer_name: Optional[str] = None
    #: Addressing only, and what a pivot BY CUSTOMER groups on: two different customers can
    #: carry the same name, and grouping by the label would merge them.
    customer_id: Optional[str] = None
    project_label: Optional[str] = None
    #: What a pivot BY PROJECT groups on: the project string, normalised. An order adopted from
    #: the AutoCount book has no project registration by design, so the string is the only
    #: identity a project has here.
    project_key: Optional[str] = None
    line_no: int
    item_code: str
    qty: str
    #: What the customer ordered on this line, what has gone out, and what is still owed.
    #: Three names rather than one `qty`, because they differ the moment a delivery is
    #: part-made and the board plans against the last of them.
    qty_ordered: str = "0"
    qty_delivered: str = "0"
    qty_outstanding: str = "0"
    #: What the engine proposes to meet it with, from the SAME ladder the per-order sheet runs
    #: (own location, then the shared pool under the hot-selling rules, then timely incoming,
    #: then Buy). The three add up to `qty_outstanding`.
    qty_proposed_reserve: str = "0"
    qty_proposed_incoming: str = "0"
    qty_proposed_buy: str = "0"
    # ---- why the Reserve is the size it is, in the strip's vocabulary ----
    #: What the demand ranked AHEAD of this line at its own pile still wants, and how many
    #: lines that is. The active policy decides the order; required date is the tie-break.
    so_qty_ahead: str = "0"
    lines_ahead: int = 0
    #: What was LEFT AT THIS LINE'S OWN LOCATION when it was reached: on hand, less reserved,
    #: less what confirmed decisions hold, less `so_qty_ahead`. Three numbers live near each
    #: other and none may be printed as another:
    #:   * the strip's `available_qty` is the WHOLE pile's position (on hand - all SO + all SPO);
    #:   * this is what was left for THIS line at its own location;
    #:   * `qty_proposed_reserve` is what the line actually took - which can EXCEED this one,
    #:     because the shared pool is a second source with a queue of its own.
    available_to_this_line: str = "0"
    #: What could be borrowed instead of bought, and from where. Borrow is never proposed on
    #: either surface - it needs a donor and a reason from a person - but a Buy printed with no
    #: mention of it reads as "this stock exists nowhere".
    qty_borrow_available: str = "0"
    borrow_candidates: List[BorrowCandidate] = []
    #: The line's REAL required date, never the bucket it landed in.
    required_date: Optional[date] = None
    #: This line's own date is behind `as_of`. Per LINE, which is what a "N of M lines are past
    #: their required date" summary counts: a line dated yesterday is past even when the week
    #: it sits in has not ended, so the bucket flag alone would undercount it.
    is_past: bool = False
    fulfilment_location: Optional[str] = None
    #: The sales-order line states no location, so it cannot be planned (AC-FP16).
    unplannable: bool = False
    priority: Optional[str] = None
    rank_score: float
    rank_factors: List[BoardRankFactor] = []
    sources: List[BoardSource] = []
    #: The supply this row would otherwise have had was taken by a row served before it.
    contested: bool = False


class BorrowCandidate(BaseModel):
    """Where a Buy could be borrowed from instead. Offered, never proposed (AC-B09)."""

    source: str
    warehouse_code: str
    donor_project_ref: Optional[str] = None
    free_qty: str


class StockDetailSalesOrder(BaseModel):
    """One document contributing to a location's SO Qty, as AutoCount's drill-down lists it."""

    sales_order_id: str
    so_number: str
    customer_name: Optional[str] = None
    customer_id: Optional[str] = None
    project_label: Optional[str] = None
    demand_class: Optional[str] = None
    #: The document's own date, and the date the quantity is wanted.
    doc_date: Optional[date] = None
    delivery_date: Optional[date] = None
    so_qty: str
    #: A confirmed decision already covers this line: committed demand, not merely outstanding.
    is_covered: bool = False


class StockDetailIncoming(BaseModel):
    """One undelivered supply-PO allocation: AutoCount's PO Qty, which in Sorento is the SPO."""

    spo_number: Optional[str] = None
    supplier_name: Optional[str] = None
    expected_date: Optional[date] = None
    spo_qty: str


class StockDetail(BaseModel):
    """`GET /project-sales/fulfilment-planning/stock-detail`.

    AutoCount's Stock Status with Detail for one product at one location: the four totals, and
    every document behind them. The lists ADD UP to the totals by construction - both are
    summed from the same rows - so the drill-down can never justify a number the strip did not
    print.
    """

    product_id: str
    item_code: str
    description: Optional[str] = None
    warehouse_id: str
    location: str
    qty_on_hand: str
    #: What the whole book still owes here, by the shared `is_open_demand()` rule, every demand
    #: class: a dealer order occupies the stock as completely as a project one.
    so_qty: str
    spo_qty: str
    #: `on hand - SO + SPO`, SIGNED. A negative is the point, not an error.
    available_qty: str
    qty_reserved: str
    qty_held_by_decisions: str
    qty_free: str
    sales_orders: List[StockDetailSalesOrder] = []
    incoming: List[StockDetailIncoming] = []


class BoardCellLocation(BaseModel):
    """One (product, location) of a cell: what is owed there, and what is actually there.

    The strip used to read "BRW-BB 22" with 22 being the DEMAND, which is the one reading
    nobody guessed. Every number is now named, and the stock facts sit beside the demand.

    Every stock figure is null (never zero) for the location-less row of a line whose sales
    order states no warehouse: there is no location whose stock could be counted, and a zero
    would read as "that location is empty".
    """

    location: Optional[str] = None
    #: Addressing only: what the stock drill-down is opened by. Never rendered, and never
    #: derived on the client from a warehouse code or an item code.
    product_id: Optional[str] = None
    warehouse_id: Optional[str] = None
    #: The demand, under the name the frontend's source strip already reads.
    qty: str
    #: The same number, said unambiguously.
    qty_demand: str
    qty_on_hand: Optional[str] = None
    qty_reserved: Optional[str] = None
    #: What this engine may actually use: on hand, less reserved, less what confirmed decisions
    #: already hold. The figure the proposal was computed from.
    qty_free: Optional[str] = None
    #: Of that, what was still unclaimed when THIS cell's lines were served - earlier dates
    #: draw first, so a December cell can face a smaller pile than `qty_free` suggests.
    qty_free_remaining: Optional[str] = None
    #: What confirmed decisions are holding here. On hand, less reserved, less this, IS
    #: `qty_free` - the third term of that arithmetic, printed so the sum closes on screen.
    qty_held_by_decisions: Optional[str] = None
    #: What the WHOLE BOOK still owes at this location: every open line of every open sales
    #: order, not merely the ones on this board, by the shared `is_open_demand()` rule. Without
    #: it "478 free" reads as "478 available to me" while 47,009 is owed at that location.
    qty_owed_all_orders: Optional[str] = None
    #: Of that, the part a confirmed decision already covers (per LINE, the rule
    #: `scm.committed_v` applies), so committed pressure can be told from uncommitted.
    qty_owed_confirmed: Optional[str] = None
    #: Allocated on a supply PO and not yet received, at this location.
    qty_incoming: Optional[str] = None
    # ---- AutoCount's Stock Status vocabulary, which is the strip's first line ----
    #: "SO Qty": the same number as `qty_owed_all_orders`, under the word the planner uses.
    so_qty: Optional[str] = None
    #: "PO Qty" in AutoCount is the supplier order; in Sorento that is the SPO.
    spo_qty: Optional[str] = None
    #: "Available Qty": `on hand - SO + SPO`, SIGNED and never clamped - "oversold here by 632"
    #: is the signal, and a floor of zero would report it as "nothing left" instead.
    available_qty: Optional[str] = None
    incoming: List["BoardIncoming"] = []
    qty_proposed_reserve: str = "0"
    qty_proposed_incoming: str = "0"
    qty_proposed_buy: str = "0"


class BoardIncoming(BaseModel):
    """One undelivered supply-PO allocation: how much, when, and on which document."""

    spo_number: Optional[str] = None
    arrival_date: Optional[date] = None
    qty: str


class BoardCell(BaseModel):
    item_code: str
    bucket_key: str
    #: Summed across every contributing line, including the unplannable ones.
    total_qty: str
    locations: List[BoardCellLocation] = []
    contributions: List[BoardContribution] = []
    unplannable_count: int = 0
    contested_count: int = 0
    #: Contributions whose own required date is already past.
    past_count: int = 0
    #: How many DISTINCT sales orders contribute here, and whether the ranking told any two of
    #: these rows apart. "The active policy separates none of these rows" is TRUE of a cell
    #: holding a single line, and of a cell holding several lines of one order, and in both
    #: cases it reads as a policy failure when nothing failed. These say which case it is.
    distinct_order_count: int = 0
    rank_separates: bool = False


class BoardProductRow(BaseModel):
    item_code: str
    description: Optional[str] = None


class BoardOrderStanding(BaseModel):
    sales_order_id: str
    #: The planning record this order's confirmation posts to
    #: (`POST /project-sales/sales-orders/{pso_id}/confirm`). NULL when nobody has adopted the
    #: sales order yet, which is what lets the screen state that rather than guess it.
    project_sales_order_id: Optional[str] = None
    so_number: str
    customer_name: Optional[str] = None
    line_count: int
    #: Always 0 from the server: the verdicts live in the board's client draft (13.4).
    decided_count: int = 0
    unplannable_count: int = 0


class BoardPolicy(BaseModel):
    """The `scm.priority_policy` row a board was ranked by. Named on screen, never assumed."""

    name: str
    factors: Dict[str, float] = {}
    demand_class_weights: Dict[str, float] = {}
    #: A what-if the planner asked for rather than the row that is live. A previewed ranking
    #: is labelled and may never be committed against.
    is_preview: bool = False
    #: This policy cannot separate these rows at all - every weighted factor is absent, or
    #: holds one value across the whole board. Reported rather than left to be inferred: the
    #: live seeded rule weights only `po_document_sequence`, which no sales-order line can
    #: carry, so every row scores 0.0 and a flat ranking would otherwise read as a considered
    #: one (13.5).
    discriminates_nothing: bool = False


class PlanningBoard(BaseModel):
    """`GET /project-sales/fulfilment-planning/board`. A pure read: opening it claims nothing."""

    model_config = ConfigDict(populate_by_name=True)

    granularity: BoardGranularity
    policy: BoardPolicy
    #: The date the board was built against, so which periods read as past is reproducible
    #: rather than whatever the client's clock said.
    as_of: date
    date_buckets: List[BoardDateBucket] = Field(default=[], alias="dateBuckets")
    product_rows: List[BoardProductRow] = Field(default=[], alias="productRows")
    cells: List[BoardCell] = []
    orders: List[BoardOrderStanding] = []

    # ---- selection-scoped totals -------------------------------------------------
    #
    # Counted over every contributing line of the SELECTION, before any window is applied.
    # Read these for a banner; never sum the cells on screen for one.
    #
    # The difference bites at day granularity. The 30-column window opens on work still to
    # come, so it holds no past cell at all: a banner summing `BoardCell.past_count` reads
    # "143 of 153 lines are already past their required date" at week and month and then
    # DISAPPEARS at day, losing the most important number on the board exactly when the
    # planner is looking closest.
    #: Contributing lines in the selection.
    line_count: int = 0
    #: Of those, the ones whose own required date is behind `as_of`.
    past_line_count: int = 0
    #: Of those, the ones whose sales order states no fulfilment location (AC-FP16).
    unplannable_line_count: int = 0
    #: Of those, the ones the ranking could not cover because a higher-ranked line took the
    #: supply first. Allocation runs over the whole selection, not over the window, so this is
    #: the selection's contest count on every granularity.
    contested_line_count: int = 0
