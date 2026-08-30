"""Planning changes wire shapes (`documentation/plans/scm/PLAN-so-book-diff-replanning.md`
section 3), transcribed field for field from
`sorento_crm_frontend/app/(protected)/project-sales/_shared/types/planningChange.types.ts`,
the Phase 1 contract this Phase 2 build matches exactly.

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

PlanningChangeKind = Literal["delayed", "advanced", "qty_up", "qty_down", "closed", "added"]
PlanningChangeReaction = Literal["keep", "release", "replan", "reduce", "retire"]
#: `confirm`/`amend` apply only to a row carrying a `proposal` (`replan`/`qty_up`), the
#: captain's "I can't really amend also right to set the borrow, clicking accept here has
#: no effect" - `accept` alone recorded a decision Apply never executed for such a row.
PlanningChangeDecision = Optional[Literal["accept", "keep", "board", "confirm", "amend"]]
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


class PlanningChangeReserveWindowFact(BaseModel):
    value: bool
    window_days: int
    new_date: str
    window_end: str


class PlanningChangeBuyActionedFact(BaseModel):
    value: bool
    po_number: Optional[str] = None


class PlanningChangeFacts(BaseModel):
    dealer_hot_selling: PlanningChangeEvidencedFact
    project_hot_selling: PlanningChangeEvidencedFact
    discontinued: bool
    days_moved: int
    within_reserve_window: PlanningChangeReserveWindowFact
    buy_actioned: PlanningChangeBuyActionedFact


class PlanningChangeInquiryRow(BaseModel):
    id: str
    verb: str
    qty: str
    state: str


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
    suggested: PlanningChangeReaction
    why: str
    #: Stock that has ALREADY physically moved for this line, in one phrase - "10 moved
    #: BRW -> BRW-IB, line cancelled" (AC-P3-9). Stated, never reversed: a movement is a
    #: person's decision and the plan does not get to undo one. `None` on nearly every row.
    moved_transfer: Optional[str] = None
    proposal: Optional[BoardContribution] = None
    inquiry_rows: List[PlanningChangeInquiryRow] = Field(default_factory=list)
    decision: PlanningChangeDecision = None
    #: What Apply will post for this line, set only by `confirm`/`amend`. Read back so the
    #: batch page can show "Amended: Reserve 40 at BRW-BB ..." without recomputing it.
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
