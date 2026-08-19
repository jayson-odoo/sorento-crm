"""Supply composition and atomic confirmation (front planning section 6, Stage 1C).

The wire shapes here are the ones the Phase 1 frontend was built against
(`sorento_crm_frontend/app/(protected)/project-sales/_shared/types/fulfilmentPlanning.types.ts`),
transcribed field for field. Two conventions carry over from the reconciliation schemas
next door and are the reason a screen full of these renders no identifiers a person has to
resolve:

* **quantities are decimal STRINGS.** A float round trip loses the tail of a quantity a
  customer signed for, and these numbers are compared for exact equality at confirmation.
* **codes, not ids, everywhere the screen reads.** Warehouse CODE, item CODE, project
  REFERENCE. The id fields that do exist (`source_warehouse_id`, `donor_project_id`,
  `warehouse_id` on a candidate, `project_id` on the proposal, `product_id` on a line) are
  addressing only: the confirm payload names a warehouse and a donor project by id while the
  sheet names them by code, and the read had no other way to carry the pair -
  `SupplyLine.product_id` is what the Proof button asks the classification-evidence endpoint
  with. They are never rendered, the same way `ReconciliationLine.id` is never rendered.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

SupplyComponentKind = Literal["timely_spo", "reserve", "borrow", "buy"]
BorrowSource = Literal["other_location", "other_project"]
SupplyDecisionState = Literal["active", "superseded", "challenged"]


class SupplyComponent(BaseModel):
    kind: SupplyComponentKind
    qty: str
    #: The sentence the rule that produced the quantity wrote (AC-B14). Deterministic,
    #: never LLM-written, frozen with the snapshot at confirmation.
    reason: str
    source_location: Optional[str] = None
    source_warehouse_id: Optional[str] = None
    donor_project_ref: Optional[str] = None
    donor_project_id: Optional[str] = None
    #: What CS typed: the Borrow reason, or the reason a discontinued product is bought.
    cs_reason: Optional[str] = None


class SupplySpoRef(BaseModel):
    spo_number: str
    arrival_date: Optional[date] = None
    qty: str


class BorrowDonorImpact(BaseModel):
    free_before: str
    free_after_full_borrow: str
    committed_qty: str


class BorrowCandidate(BaseModel):
    """A donor, with the whole of its own position beside what it could give.

    The captain, on a list that stated free stock alone: "before I decide to borrow, I need
    to know I am not hurting them". Free nets reserved and confirmed holds only, so on this
    book it reads as raw on-hand; the AutoCount triple is what says whether the donor can
    actually spare it (PLAN 13.11).
    """

    source: BorrowSource
    warehouse_code: str
    warehouse_id: str
    donor_project_ref: Optional[str] = None
    donor_project_id: Optional[str] = None
    #: What this donor can give: the location's free stock, or the donor project's own hold.
    free_qty: str
    #: AutoCount's Stock Status columns for the DONOR's (product, location) pile.
    qty_on_hand: Optional[str] = None
    so_qty: Optional[str] = None
    spo_qty: Optional[str] = None
    #: on hand - SO + SPO. SIGNED: a donor the book has oversold says so.
    available_qty: Optional[str] = None
    #: The engine's own pair, so the two arithmetics can be reconciled on screen.
    qty_free: Optional[str] = None
    qty_committed: Optional[str] = None
    #: What this line still has to cover at the borrow rung, and what the donor is left with
    #: once it is met. `available_after_need` is what the list is RANKED on, and is signed.
    need_qty: Optional[str] = None
    available_after_need: Optional[str] = None
    #: First in the ranking - the donor this borrow hurts least. Exactly one row carries it.
    recommended: bool = False
    donor_impact: BorrowDonorImpact


class SupplyFrozenLine(BaseModel):
    """What the active revision was balanced against, as it was frozen."""

    open_qty: str
    components: List[SupplyComponent] = []
    #: The reason given for overriding the engine's proposal, when one was. Absent on a line
    #: confirmed as proposed, and on any line frozen before the field existed.
    amend_reason: Optional[str] = None
    #: The reason a discontinued product was still bought (AC-B11), when one was given.
    buy_reason: Optional[str] = None


class SupplyLine(BaseModel):
    project_line_id: str
    line_no: int
    item_code: Optional[str] = None
    #: Addressing only, never rendered (see module docstring) - what the Proof button asks
    #: `GET .../fulfilment-planning/classification` with.
    product_id: Optional[str] = None
    description: Optional[str] = None
    uom: Optional[str] = None
    open_qty: str
    required_date: Optional[date] = None
    fulfilment_location: Optional[str] = None
    is_dealer_hot_selling: bool = False
    is_project_hot_selling: bool = False
    #: Classified (a non-null letter exists on that class, at an active location) but not
    #: hot - "Cold at retail" / "Cold at project" in the UI's own words. `False` while the
    #: class is hot too - the hot flag already covers it.
    dealer_classified: bool = False
    project_classified: bool = False
    classification_unavailable: bool = False
    is_discontinued: bool = False
    pool_location: Optional[str] = None
    #: The old reorder-level cap for a hot-selling line. Always null now (19 August 2026):
    #: dealer hot-selling offers the pool nothing and project hot-selling caps it by the
    #: pool's own availability instead. Kept for wire compatibility, never a number again.
    pool_cap: Optional[str] = None
    pool_reorder_level: Optional[str] = None
    components: List[SupplyComponent] = []
    timely_spo: List[SupplySpoRef] = []
    advisory_spo: List[SupplySpoRef] = []
    borrow_candidates: List[BorrowCandidate] = []
    frozen: Optional[SupplyFrozenLine] = None
    #: Covered by the order's active revision (13.4). A confirmation covers the lines the
    #: planner chose, so `false` here means EXPLICITLY undecided - the line's whole open
    #: quantity is still demand and still reaches reorder planning. Stated as its own
    #: field rather than left to be inferred from `frozen`, because "nobody decided this"
    #: and "decided, and it needed nothing" are different answers.
    decided: bool = False
    #: Why nothing can be proposed for this line, when nothing can: a mirror line with no
    #: reconciled AutoCount line has no open quantity to promise against. Such a line still
    #: reads on the sheet, with no components and no donors, rather than refusing the whole
    #: read; a plannable line carries `null` here.
    unplannable_reason: Optional[str] = None


class SupplyDecisionOut(BaseModel):
    revision_no: int
    state: SupplyDecisionState
    confirmed_by_name: Optional[str] = None
    confirmed_at: Optional[datetime] = None
    #: Why the active revision no longer matches the order. Present when challenged.
    challenged_reason: Optional[str] = None


class SupplyFailingLine(BaseModel):
    """A line the server will not confirm, named the only way it may be (AC-C02)."""

    line_no: Optional[int] = None
    item_code: Optional[str] = None
    reason: str


class SupplyProposal(BaseModel):
    project_sales_order_id: str
    provisional_ref: str
    autocount_doc_no: Optional[str] = None
    #: NULLABLE since adoption (`PLAN-fulfilment-planning-from-autocount-so.md` section 4):
    #: an order adopted from the AutoCount book has no project registration and must not
    #: invent one, so all three project fields are absent on that path. Optional here so
    #: the value is a null rather than the string "None" - which is what a required field
    #: turned it into, and which the screen would have rendered and linked to.
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    project_name: Optional[str] = None
    status: str
    review_state: Optional[str] = None
    decision: Optional[SupplyDecisionOut] = None
    #: "4 of 12 lines decided", per order. Information, never a gate (13.4).
    lines_total: int = 0
    lines_decided: int = 0
    lines: List[SupplyLine] = []
    failing_lines: Optional[List[SupplyFailingLine]] = None


# ------------------------------------------------------------------- the confirmation


class ConfirmReserveComponent(BaseModel):
    warehouse_id: str
    qty: Decimal = Decimal("0")


class ConfirmBorrowComponent(BaseModel):
    source: BorrowSource
    warehouse_id: str
    donor_project_id: Optional[str] = None
    qty: Decimal = Decimal("0")
    #: Required, but NOT by the schema: an empty reason is a failing LINE, named by line
    #: number and item code like every other refusal, rather than a field-level 422 the
    #: sheet cannot attach to a row (AC-B09, AC-C02).
    reason: str = ""


class ConfirmLine(BaseModel):
    project_line_id: str
    timely_spo_qty: Decimal = Decimal("0")
    reserve: List[ConfirmReserveComponent] = Field(default_factory=list)
    borrow: List[ConfirmBorrowComponent] = Field(default_factory=list)
    buy_qty: Decimal = Decimal("0")
    buy_reason: Optional[str] = None
    #: Why this composition is not the one the engine proposed, in the planner's own words.
    #: Absent when they took the proposal as it stood: demanding a reason for agreeing is how
    #: a mandatory field becomes a rubber stamp. It is FROZEN with the line, beside the
    #: engine's own sentences, because those explain a decision nobody took once it is amended.
    amend_reason: Optional[str] = None


class ConfirmSupplyBody(BaseModel):
    lines: List[ConfirmLine] = Field(default_factory=list)


class ConfirmException(BaseModel):
    """An outcome purchasing has to answer, not a refusal of the confirmation."""

    line_no: Optional[int] = None
    item_code: Optional[str] = None
    message: str


class ConfirmResult(BaseModel):
    revision_no: int
    confirmed_at: Optional[datetime] = None
    review_state: str = "confirmed"
    inquiry_rows_created: int = 0
    exceptions: List[ConfirmException] = []
    #: What this revision covers, and what is still open on the order after it (13.4).
    #: `lines_undecided > 0` is a normal, deliberate outcome, not a warning.
    lines_decided: int = 0
    lines_undecided: int = 0


# ------------------------------------------------------------------- the Plans page (D1)


class PlanRow(BaseModel):
    """One row of `GET /project-sales/plans`: one supply decision revision, cross-order.

    Addressing is by `project_sales_order_id` (the SO sheet) and `sales_order_id` (the SCM
    sales order), never rendered - the same "codes, not ids" rule the rest of this file
    follows, with `so_number` and the agent CODE as what actually prints.
    """

    project_sales_order_id: str
    sales_order_id: Optional[str] = None
    project_id: Optional[str] = None
    so_number: Optional[str] = None
    customer_name: Optional[str] = None
    agent_code: Optional[str] = None
    agent_label: Optional[str] = None
    revision_no: int
    state: SupplyDecisionState
    decided_by_name: Optional[str] = None
    decided_at: Optional[datetime] = None
    #: How many lines this revision covers. Never the sales order's whole line count - a
    #: revision may cover a chosen subset (13.4) and this is that subset's size.
    line_count: int = 0
    #: "Reserve 213 · Buy 145", summed across every line the revision covers. `None` on a
    #: revision that covers nothing (should not happen, but a summary is never invented).
    components_summary: Optional[str] = None
    #: Why the active revision no longer matches the order. Present only when `state` is
    #: `challenged`.
    challenged_reason: Optional[str] = None


# --------------------------------------------------------- confirm all approved (D3)


class ConfirmManyOrderBody(BaseModel):
    """One order's half of `POST .../fulfilment-planning/confirm-all`. Same shape as
    `ConfirmSupplyBody.lines`, named so a batch of them addresses each order by id."""

    pso_id: str
    lines: List[ConfirmLine] = Field(default_factory=list)


class ConfirmManyBody(BaseModel):
    orders: List[ConfirmManyOrderBody] = Field(default_factory=list)


class ConfirmManyOrderResult(BaseModel):
    """One order's outcome. `ok` decides which of the two halves is populated - never both,
    and never neither: a result the caller cannot read as success-or-failure is worse than
    a slower reply."""

    pso_id: str
    ok: bool
    decision_revision: Optional[int] = None
    inquiry_rows_created: Optional[int] = None
    lines_decided: Optional[int] = None
    lines_undecided: Optional[int] = None
    error: Optional[str] = None
    #: The lines the server refused, named the way `SupplyFailingLine` always is (AC-C02),
    #: when the refusal named any.
    failing_lines: Optional[List[SupplyFailingLine]] = None


class ConfirmManyResult(BaseModel):
    """`POST .../fulfilment-planning/confirm-all`. One result per order named in the body,
    in the SAME order - a caller matching by index never has to search."""

    results: List[ConfirmManyOrderResult] = []


class ClassificationEvidenceLocation(BaseModel):
    """One location's contribution to a demand class's ranking - the "proof" line."""

    warehouse_code: str
    qty_delivered: str
    rank: int
    of: int
    #: This row's OWN share of the class's total quantity - qty / sum(qty) over the whole
    #: window. "Its share" in the popover; kept separate from `cumulative_share_pct` so a
    #: thin ranking's high cumulative figure is never read as this row's own weight (captain,
    #: 19 Aug 2026: "Share: top 93.6%" read as good on a row that held almost nothing).
    share_pct: Optional[float] = None
    #: The running share INCLUDING this row - "Ranked above it" in the popover is this minus
    #: `share_pct`.
    cumulative_share_pct: Optional[float] = None
    #: A/B/C, or absent when the class ranking never reached this row (should not happen -
    #: every ranked row carries a letter).
    letter: Optional[str] = None
    hot: bool = False


class ClassificationEvidenceClass(BaseModel):
    demand_class: Literal["retail", "project"]
    #: The word the captain asked for instead of the demand-class code: "Dealer" (retail
    #: customers) or "Project".
    label: str
    verdict: Literal["hot", "cold", "unclassified"]
    locations: List[ClassificationEvidenceLocation] = []


class ClassificationEvidence(BaseModel):
    """`GET .../fulfilment-planning/classification` - the proof behind a hot/cold chip."""

    product_id: str
    item_code: Optional[str] = None
    computed_at: Optional[datetime] = None
    window_days: int = 365
    hot_cut_pct: float
    classes: List[ClassificationEvidenceClass] = []
