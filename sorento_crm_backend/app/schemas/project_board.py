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


class BoardSource(BaseModel):
    kind: BoardSourceKind
    qty: str
    #: Warehouse code for a Reserve; null for Buy, which has no location by definition.
    location: Optional[str] = None
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
    so_number: str
    customer_name: Optional[str] = None
    project_label: Optional[str] = None
    line_no: int
    item_code: str
    qty: str
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


class BoardCellLocation(BaseModel):
    location: Optional[str] = None
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


class BoardProductRow(BaseModel):
    item_code: str
    description: Optional[str] = None


class BoardOrderStanding(BaseModel):
    sales_order_id: str
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
