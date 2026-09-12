"""Planning changes wire shapes (`documentation/plans/scm/PLAN-so-book-diff-replanning.md`
section 3, re-shaped by `PLAN-scm-change-management-one-engine.md` Slice C contract A),
transcribed field for field from
`sorento_crm_frontend/app/(protected)/project-sales/_shared/types/planningChange.types.ts`,
the Phase 1 contract this Phase 2 build matches exactly.

Slice C replaced the rule table's reaction verb (`suggested`) and its sentence (`why`) with
`suggestion`: the re-run at the line's new state diffed against what it holds, one component
per thing that happens, each carrying the sentence the server composed for it.

Quantities are decimal STRINGS, the same convention `project_supply.py` and
`project_board.py` use throughout: a float round trip loses the tail of a quantity the
customer signed for.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.project_board import BoardContribution
from app.schemas.project_supply import ConfirmLine

PlanningChangeKind = Literal[
    "delayed", "advanced", "qty_up", "qty_down", "cancelled", "added", "product_changed",
]
#: The one decision per row (AC-C7): Confirm the composed suggestion, or Amend it.
#: `accept` / `keep` / `board` are retired with the rule table that produced them (Slice C,
#: migration 515) - a verb the row agreed with executed nothing, which is why "accept" had
#: to exist at all. The route 422s on any other value.
PlanningChangeDecision = Optional[Literal["confirm", "amend"]]

#: What the diff did to ONE component of the plan (Slice C rule 3). The first four act on
#: something the line already HELD; the last four source quantity the re-run left uncovered.
PlanningChangeSuggestionAction = Literal[
    "keep", "reduce", "release", "reallocate", "use_own", "borrow", "spo", "buy",
]
#: Where the quantity in a component comes from, or went to.
PlanningChangeSuggestionSource = Optional[
    Literal["reserve", "borrow", "spo", "buy", "po", "pool_share"]
]
PlanningChangeAppliedState = Literal["pending", "applied", "failed", "superseded"]
# Every value the batches table can carry. The model keeps this a plain string column so a
# new trigger is a new constant, not a migration - but THIS literal must grow with it, or
# the new source 500s the whole listing on response validation (hit live 20 Aug: the first
# so_manual_edit batch made /planning-changes read as empty to the captain).
PlanningChangeSourceKind = Literal["so_book_upload", "so_manual_edit"]


class PlanningChangeFromTo(BaseModel):
    required_date: Optional[str] = None
    qty: Optional[str] = None
    status: Optional[str] = None
    #: The old/new product on a `product_changed` row (Slice A, rule 5's "carrying the old
    #: and the new product") - `None` on every other kind, same as the fields above.
    item_code: Optional[str] = None


class PlanningChangeHeldReserve(BaseModel):
    location: str
    warehouse_id: Optional[str] = None
    qty: str


class PlanningChangeHeldBorrow(BaseModel):
    location: str
    warehouse_id: Optional[str] = None
    qty: str
    source: Optional[str] = None


class PlanningChangeHeld(BaseModel):
    reserve: List[PlanningChangeHeldReserve] = Field(default_factory=list)
    borrow: List[PlanningChangeHeldBorrow] = Field(default_factory=list)
    buy_qty: str = "0"
    timely_spo_qty: str = "0"
    revision_no: int


class PlanningChangeEvidencedFact(BaseModel):
    value: bool
    where: List[str] = Field(default_factory=list)


class PlanningChangeBuyActionedFact(BaseModel):
    value: bool
    po_number: Optional[str] = None
    #: The SUM of every currently placed-or-actioned Buy on the line.
    qty: Optional[str] = None
    #: When that placed supply is expected: the PO line's own date, else the PO's, else the
    #: date the inquiry row was raised against. What "late by N days" is measured from.
    arrival_date: Optional[str] = None


class PlanningChangeFacts(BaseModel):
    """The facts the suggestion was composed against.

    `within_reserve_window` is RETIRED (Slice C rule 2): the ladder's own step 0 decides
    whether a line that far out may hold stock, and a second window constant in the change
    service could only disagree with it. What the row says now is what the re-run PROPOSED,
    which already has that decision inside it.
    """

    dealer_hot_selling: PlanningChangeEvidencedFact
    project_hot_selling: PlanningChangeEvidencedFact
    discontinued: bool
    days_moved: int
    buy_actioned: PlanningChangeBuyActionedFact


class PlanningChangeInquiryRow(BaseModel):
    id: str
    verb: str
    qty: str
    state: str


class PlanningChangeSuggestionComponent(BaseModel):
    """One line of the suggestion, with the sentence the board prints for it.

    `label` is composed SERVER-side and printed verbatim: only the engine knows which rung
    covered what, against which document, for whose order, so a second composition in the
    frontend could only drift from it. Everything beside it is there so the line can be read
    as data, never so the client can re-write the sentence.
    """

    action: PlanningChangeSuggestionAction
    source: PlanningChangeSuggestionSource = None
    #: What the component held before, when the action changed an existing figure.
    qty_was: Optional[str] = None
    qty_now: str
    #: The warehouse the quantity sits in or is freed at, e.g. `BRW-IB`.
    location: Optional[str] = None
    #: The document the quantity is on: `PO-A`, `SPO-77`. Never a UUID.
    document: Optional[str] = None
    #: Where a reallocation went, in words: `dealer pool`, `SO420103 ORDER 50`, `pool`.
    target: Optional[str] = None
    #: On a `product_changed` row: which product this component is about.
    item_code: Optional[str] = None
    label: str


class PlanningChangeSuggestion(BaseModel):
    """The whole suggestion for one changed line: the re-run diffed against the hold.

    Held components come first, in held order, then the new sourcing - the reader sees what
    happens to what they already decided before they read what is being added.
    """

    components: List[PlanningChangeSuggestionComponent] = Field(default_factory=list)
    #: The unit is kept but lands N days after the line's new date (S12). `None` when on time.
    late_days: Optional[int] = None
    #: Quantity nothing can cover in time (S11). `None` when the unit is covered.
    shortfall_qty: Optional[str] = None


class PlanningChangeRow(BaseModel):
    id: str
    #: The planning mirror line this row is about, so a board cell can be matched exactly
    #: rather than by product and sales order (AC-P3-2). `None` on an `added` row.
    project_line_id: Optional[str] = None
    line_no: int
    item_code: str
    product_name: Optional[str] = None
    kind: PlanningChangeKind
    from_: PlanningChangeFromTo = Field(alias="from")
    to: PlanningChangeFromTo
    days_moved: Optional[int] = None
    held: Optional[PlanningChangeHeld] = None
    facts: PlanningChangeFacts
    #: The re-run at the line's new state DIFFED against what it holds - the whole
    #: suggestion (AC-C1). `None` only on a row raised before Slice C.
    suggestion: Optional[PlanningChangeSuggestion] = None
    #: Stock that has ALREADY physically moved for this line, in one phrase - "10 moved
    #: BRW -> BRW-IB, line cancelled" (AC-P3-9). Stated, never reversed: a movement is a
    #: person's decision and the plan does not get to undo one. `None` on nearly every row.
    moved_transfer: Optional[str] = None
    proposal: Optional[BoardContribution] = None
    inquiry_rows: List[PlanningChangeInquiryRow] = Field(default_factory=list)
    decision: PlanningChangeDecision = None
    #: What Apply posts for this line, PRE-FILLED at build from the re-run so Confirm posts
    #: it unchanged and Amend edits it. Read back so the batch page can show "Amended:
    #: Reserve 40 at BRW-BB ..." without recomputing it.
    composition: Optional[ConfirmLine] = None
    applied_state: PlanningChangeAppliedState = "pending"
    applied_reason: Optional[str] = None
    board_link: str

    model_config = {"populate_by_name": True}


class PlanningChangeOrder(BaseModel):
    project_sales_order_id: str
    so_number: str
    customer_name: Optional[str] = None
    project_label: Optional[str] = None
    revision_no: int
    rows: List[PlanningChangeRow] = Field(default_factory=list)
    is_adopted: bool
    core_sales_order_id: Optional[str] = None
    project_id: Optional[str] = None


class PlanningChangeBatchSource(BaseModel):
    upload_id: str
    file_name: str
    kind: PlanningChangeSourceKind
    import_job_id: Optional[str] = None


class ApplyPlanningChangesReturnedToReview(BaseModel):
    """B1 (code review, 20 Aug 2026): an order Apply revised whose new revision, or lack of
    one, dropped lines this batch never named back to undecided - a challenged/superseded
    revision carries nothing forward (module docstring in `planning_change_service.py`), and
    the caller was previously told only `applied_orders`, with no sign those lines moved."""

    so_number: str
    line_count: int
    line_nos: List[int] = Field(default_factory=list)
    reason: str


class PlanningChangeResult(BaseModel):
    orders_revised: List[Dict[str, Any]] = Field(default_factory=list)
    orders_failed: List[Dict[str, Any]] = Field(default_factory=list)
    inquiry_rows_changed: List[Dict[str, Any]] = Field(default_factory=list)
    lines_replanned: int = 0
    #: Rows decided `confirm`/`amend` that Apply actually wrote (accepted alone never did -
    #: the captain's own complaint this counter answers).
    lines_confirmed: int = 0
    purchasing_notified: bool = False
    #: B1 (code review, 20 Aug 2026): lines a revised order's PREVIOUS revision covered that
    #: this batch never named, dropped back to undecided as a side effect (a challenged or
    #: materially-superseded revision carries nothing forward) rather than as anything this
    #: batch decided. See `ApplyPlanningChangesReturnedToReview`.
    returned_to_review: List[ApplyPlanningChangesReturnedToReview] = Field(
        default_factory=list
    )


class PlanningChangeBatch(BaseModel):
    id: str
    created_at: datetime
    created_by_name: Optional[str] = None
    source: PlanningChangeBatchSource
    applied_at: Optional[datetime] = None
    applied_by_name: Optional[str] = None
    result: Optional[PlanningChangeResult] = None
    orders: List[PlanningChangeOrder] = Field(default_factory=list)


class PlanningChangeBatchSummary(BaseModel):
    id: str
    created_at: datetime
    created_by_name: Optional[str] = None
    source: PlanningChangeBatchSource
    order_count: int
    line_count: int
    pending_count: int
    failed_count: int
    applied_at: Optional[datetime] = None
    applied_by_name: Optional[str] = None
    #: The sales orders this batch touched, by NUMBER (AC-P3-1) - what the list row's Plan
    #: action addresses the board with, so the list needs no second call to open one.
    so_numbers: List[str] = Field(default_factory=list)


class PlanningChangeListEnvelope(BaseModel):
    """Flat `{ data, total, page, limit }`, exactly as the FE contract states it (section 3)
  - deliberately NOT the shared `ListResponse[T]` envelope (nested `pagination`), because
    the Phase 1 mock service (`planningChangeService.ts`) was built against this flat shape
    and the contract says Phase 2 must match it, not the other way round.
    """

    data: List[PlanningChangeBatchSummary] = Field(default_factory=list)
    total: int
    page: int
    limit: int


class UpdatePlanningChangeRowBody(BaseModel):
    decision: PlanningChangeDecision = None
    #: Required when `decision == 'amend'` (422 otherwise); ignored for every other
    #: decision - `confirm` derives its own composition from the row's `proposal` server-side.
    composition: Optional[ConfirmLine] = None


class ApplyPlanningChangesResult(BaseModel):
    applied_orders: List[str] = Field(default_factory=list)
    failed_orders: List[Dict[str, Any]] = Field(default_factory=list)
    already_applied: bool = False
    returned_to_review: List[ApplyPlanningChangesReturnedToReview] = Field(
        default_factory=list
    )
