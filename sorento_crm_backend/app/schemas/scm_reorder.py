"""SCM M3 reorder-run + recommendation response schemas.

Mirror the Phase-1 FE contract documented at the top of
``app/(protected)/scm/reorder/services/reorderRunService.ts`` +
``types/reorder.types.ts``. No UUIDs surface in display fields - SKU/warehouse/
supplier resolve to human codes/names (ids stay on the request path only).
"""
from __future__ import annotations

from datetime import date
from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

#: One sales order number, capped like `canonical_documents.py`'s own `_SoNumber` - a
#: bound on the STRING, not the list (that is `so_numbers`'s own `Field(max_length=...)`
#: below). Human-typed SO numbers are short; a caller sending a pathological string is a
#: request to reject, not one to store.
_SoNumber = Annotated[str, Field(max_length=100)]


def require_start_on_or_before_end(start: Optional[date], end: Optional[date]) -> None:
    """Raises when a stated start falls after a stated end.

    One rule, shared by every `plan_horizon_start`/`plan_horizon_date` pair in the app -
    `CreateReorderRunRequest` and `ReplanReorderRunRequest` below, and `LoadingPlanCreate` /
    `LoadingPlanUpdate` in `app/api/v1/scm/fulfilment.py` - so a backwards window reads the
    same refusal on every screen that asks for one, never a second wording of the same rule.
    Either side missing is not an error: `None` means unbounded on that side.
    """
    if start is not None and end is not None and start > end:
        raise ValueError("plan_horizon_start must be on or before plan_horizon_date")


def require_so_numbers_need_project_demand_class(
    demand_class: Optional[str], so_numbers: List[str]
) -> None:
    """Raises when ``so_numbers`` is asked for without ``demand_class='project'`` (T2).

    An SO scope only means something against the project leg specifically - a retail run or
    an unscoped ("all") run nets without regard to which sales orders the buyer named, so a
    non-empty list on either of those is a request that cannot be honoured rather than one
    that is silently ignored.
    """
    if so_numbers and demand_class != "project":
        raise ValueError("so_numbers requires demand_class='project'")


# --- create / poll ----------------------------------------------------------

class CreateReorderRunRequest(BaseModel):
    """Manual-plan request (M8-D5). ``buy_scope`` is gone - planning scope is fixed
    (create_run defaults it internally); the FE manual modal sends only warehouse +
    budget. Market never enters a run (it reaches the plan through chat only), so
    ``include_market`` stays false here.
    """
    warehouse_codes: List[str] = []
    # Empty means every product, which is what the daily scheduled run sends. Human codes,
    # never ids, like every other field the frontend passes.
    product_codes: List[str] = []
    budget_id: Optional[str] = None  # M4 - ignored in M3
    include_market: bool = False  # M7 - opt-in market-trend priority factor
    # "Plan until" (captain, 20 Aug): omitted/None plans every open SO line regardless of
    # need date, unchanged from before this field existed. When set, demand needed AFTER
    # it is excluded from the run's netting; demand carrying no date is always still
    # counted.
    plan_horizon_date: Optional[date] = None
    # "Sales orders needed FROM" (S4, PLAN-reorder-feedback-9sep.md): the start-side twin.
    # Omitted/None plans every open SO line regardless of when it was needed. Demand
    # carrying no date is always still counted (G2, 9 Sep ruling), the same reading the end
    # date already gives it.
    plan_horizon_start: Optional[date] = None
    # Demand scope (PLAN-reorder-plan-demand-class-orders.md, 21 Sep 2026): which leg of
    # demand to net. Omitted/None nets BOTH legs, unchanged from before this field existed.
    demand_class: Optional[Literal["project", "retail"]] = None
    # The SO scope, project only. Omitted/empty means every project order in range - not
    # narrowed to none - so it is a real narrowing only when both non-empty AND
    # demand_class='project'. Capped at 500 - the measured universe is ~321 SOs (plan
    # section 2), so 500 is headroom, not a real limit - and each number at 100 chars.
    so_numbers: List[_SoNumber] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def _start_before_end(self):
        require_start_on_or_before_end(self.plan_horizon_start, self.plan_horizon_date)
        require_so_numbers_need_project_demand_class(self.demand_class, self.so_numbers)
        return self


class ReorderRunAccepted(BaseModel):
    run_id: str
    status: Literal["running", "completed", "failed"]
    buy_scope: str
    stage: str


class ReplanReorderRunRequest(BaseModel):
    """Re-plan a completed run (plan 5.1, G8): same shape as a manual Start Plan, since the
    FE's header edit form always submits its full current state - unedited fields simply
    carry the value the header was pre-filled with, which is what makes "only Plan until
    changed" and "only scope changed" both read as "the same remaining scope"."""
    warehouse_codes: List[str] = []
    product_codes: List[str] = []
    plan_horizon_date: Optional[date] = None
    plan_horizon_start: Optional[date] = None
    # Same demand scope as `CreateReorderRunRequest`; the FE re-submits it unchanged from
    # the run being replanned when the header edit form never touched it.
    demand_class: Optional[Literal["project", "retail"]] = None
    # Same cap as `CreateReorderRunRequest.so_numbers` - see its own comment.
    so_numbers: List[_SoNumber] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def _start_before_end(self):
        require_start_on_or_before_end(self.plan_horizon_start, self.plan_horizon_date)
        require_so_numbers_need_project_demand_class(self.demand_class, self.so_numbers)
        return self


class ReplanReorderRunAccepted(ReorderRunAccepted):
    """The new run's accepted envelope, plus which run it supersedes - so the FE can
    navigate straight to it exactly like Start Plan already does."""
    supersedes_run_id: str


class ReorderRunSummary(BaseModel):
    buy_count: int
    disposition_count: int
    exception_count: int
    total_cash_impact: float
    recommendation_count: int


class ReorderRunStatusResponse(BaseModel):
    run_id: str
    status: Literal["running", "completed", "failed"]
    stage: Optional[str] = None
    buy_scope: Optional[str] = None
    error: Optional[str] = None
    summary: Optional[ReorderRunSummary] = None
    # The grain this run may be DECIDED at, stamped from the admin plan-grain policy when
    # it was created (front-planning plan 5.1). NULL on a legacy run, which
    # `front_planning_contract_version IS NULL` identifies and which accepts no decision
    # in either grain. Never the live setting - the FE chip reads the stamp.
    decision_grain: Optional[Literal["product", "location"]] = None
    front_planning_contract_version: Optional[int] = None
    # The "Plan until" cutoff this run was launched with, ISO date, or None when the run
    # carried no horizon (every run has always planned every open SO line, unchanged).
    plan_horizon_date: Optional[str] = None
    # The start-side twin (S4), ISO date, or None when the run carried no start.
    plan_horizon_start: Optional[str] = None
    # When the engine started. The plan page's header is "Plan dd/mm/yyyy HH:mm" and this
    # response is the only thing that page reads, so without it the header can state the
    # date or a fabricated time and nothing else.
    started_at: Optional[str] = None
    # --- Header tab scope (plan 5.1, AC-5.1) - the same facts the plans list already
    # resolves per row, added here so the plan's OWN detail page can show + pre-fill them
    # for a Re-plan edit without a second endpoint. ---
    warehouse_codes: List[str] = []
    is_all_warehouses: bool = False
    # None = every product (the run stored no scope); a list, INCLUDING empty, is a real
    # narrowing - the same "None vs []" reading `_resolve_product_ids` already uses.
    product_codes: Optional[List[str]] = None
    # Re-plan supersede pointers (G8, AC-5.2/5.4). At most one of the two is ever set on a
    # given run: a run that supersedes an older one is never itself superseded on arrival.
    supersedes_run_id: Optional[str] = None
    superseded_by_run_id: Optional[str] = None
    # `chat` when the low stock report tool created this run over WhatsApp, None on every
    # other path (PLAN-low-stock-report S5, AC-48).
    requested_via: Optional[str] = None
    # Demand scope this run was launched with (21 Sep 2026). None = both legs, unchanged
    # from before this field existed - the FE header shows "Demand: ..." only when set.
    demand_class: Optional[Literal["project", "retail"]] = None
    # None means no SO scope was asked for; a list, INCLUDING empty, is a real narrowing -
    # the same "None vs []" reading `product_codes` above already uses.
    so_numbers: Optional[List[str]] = None


# --- run history (list) -----------------------------------------------------

class ReorderRunListItem(BaseModel):
    """One row in the newest-first run-history list. Runs are identified by time +
    warehouses (never the run_id) - ``warehouse_codes`` resolve the frozen
    ``warehouse_ids`` to human codes. ``summary`` populates once completed (read
    from the immutable ``run_log`` counts)."""
    run_id: str
    status: str  # running | completed | failed
    buy_scope: Optional[str] = None
    warehouse_codes: List[str] = []
    warehouse_count: int = 0
    started_at: Optional[str] = None   # naive-UTC ISO - FE formats in Malaysia time
    finished_at: Optional[str] = None
    summary: Optional[ReorderRunSummary] = None
    # Same stamp as ReorderRunStatusResponse, so the history list and today's run label a
    # run's grain identically. NULL = legacy run.
    decision_grain: Optional[Literal["product", "location"]] = None
    front_planning_contract_version: Optional[int] = None
    # Same field as ReorderRunStatusResponse - the plan header reads it off whichever of
    # the two responses is on screen (today's run vs a past one).
    plan_horizon_date: Optional[str] = None
    plan_horizon_start: Optional[str] = None
    # Same demand scope as ReorderRunStatusResponse (21 Sep 2026).
    demand_class: Optional[Literal["project", "retail"]] = None
    so_numbers: Optional[List[str]] = None
    # --- the plans list (PLAN-scm-reorder-revamp.md 4.1) ----------------------------
    # The scheduled daily run rather than one a person started (`created_by IS NULL` -
    # `task_scheduler._reorder_plan_tick` passes no actor). Drives the "daily" badge; the
    # FE deliberately refuses to guess it from the clock.
    is_scheduled: bool = False
    # Every ACTIVE warehouse. A plan launched with no warehouse scope stores them all, so
    # the column would otherwise read "60 warehouses" for what was asked for as "all".
    is_all_warehouses: bool = False
    # How many PRODUCTS the plan narrowed to, or null for the whole catalogue (the daily
    # run's own scope). Distinct from `summary.recommendation_count`, which counts rows.
    product_count: Optional[int] = None
    # How many products the run actually wrote rows for. The denominator of the Decided
    # column: `product_count` above is the SCOPE, and it is null on the daily run, which
    # would leave the most common plan reading "12 of -".
    planned_product_count: Optional[int] = None
    # Both by DISTINCT product, never by location (R14): a product held in three bins is
    # one thing to decide and one thing to confirm.
    decided_product_count: Optional[int] = None
    confirmed_product_count: Optional[int] = None
    # AC-5.4: the superseded run stays readable and labelled in the plans list. Set only
    # once its replacement actually completed (never on a still-running or failed re-plan).
    superseded_by_run_id: Optional[str] = None
    # The "via chat" marker on the plans list (AC-4): `chat`, or None for a run a person
    # or the scheduler started. Never inferred from anything else.
    requested_via: Optional[str] = None


class ReorderRunListResponse(BaseModel):
    data: List[ReorderRunListItem]
    pagination: dict  # {page, limit, total, total_pages}


class CandidateOrder(BaseModel):
    """One project SO the Orders picker in Start Plan (Demand = Project) can offer
    (PLAN-reorder-plan-demand-class-orders.md, 21 Sep 2026). `rows_total` is unfiltered -
    a row the requested range excludes still counts toward it, so the picker can say why
    an SO it lists shows zero in-range lines."""
    so_number: str
    project_label: Optional[str] = None
    customer_name: Optional[str] = None
    rows_total: int = 0
    rows_in_range: int = 0
    rows_awaiting: int = 0
    # PLAN-reorder-plan-raised-filter.md, 22 Sep 2026: rows in `raised_from`/`raised_to`
    # by their first upload day (`order_inquiry_rows.created_at`) - the book carries no
    # raise date of its own (owner ruling R1).
    rows_raised_in_window: int = 0
    first_delivery: Optional[str] = None
    last_delivery: Optional[str] = None


class ReorderRunTodayResponse(ReorderRunListItem):
    """The run the reorder page opens to without knowing an id (M8-D3/D4): today's
    scheduled snapshot when present, else the most-recent completed run (the last
    available snapshot). ``is_today`` tells the FE whether the header may say
    "Today's plan" or must show that run's date + time (M8-D11).

    ``in_progress`` is a SEPARATE fact from the run being returned: a plan started today
    that has not finished yet. The run shown is always a completed one, so the page keeps
    the last usable snapshot on screen while it says a newer plan is being built."""
    is_today: bool = False
    in_progress: bool = False


class UnlocatedDemandSample(BaseModel):
    product_code: str
    quantity: float


class UnlocatedDemandResponse(BaseModel):
    """Open demand the plan cannot see, because the line names no stock location.

    Planning nets per product AND location, so a line with no warehouse has nothing to net
    against and produces no recommendation. Reported rather than silently omitted: a plan
    that leaves out most of the demand without saying so is read as "nothing to buy"."""
    lines: int = 0
    products: int = 0
    quantity: float = 0.0
    sample: List[UnlocatedDemandSample] = []


# --- recommendations grid ---------------------------------------------------

class SupplierChoice(BaseModel):
    supplier_code: Optional[str] = None
    supplier_name: Optional[str] = None
    unit_cost: Optional[float] = None
    lead_time_days: Optional[float] = None
    composite_score: Optional[float] = None
    is_primary: bool = False
    # Scorecard detail for the "why this supplier" popover (frozen; may be null on
    # older runs / suppliers with no M2 performance sample).
    sample_size: Optional[int] = None
    confidence: Optional[str] = None
    lead_time_source: Optional[str] = None
    lead_time_variance: Optional[float] = None
    moq: Optional[float] = None
    order_multiple: Optional[float] = None


class AllocationLine(BaseModel):
    warehouse_code: Optional[str] = None
    warehouse_name: Optional[str] = None
    qty: float


class RankFactor(BaseModel):
    """One weighted factor behind a buy rec's frozen rank_score (M4-D1/D14). A dropped
    factor (no data) carries ``present=False`` + ``value=None`` (graceful degrade)."""
    key: str  # urgency | margin | abc | priority | committed
    weight: float
    value: Optional[float] = None
    present: bool = True


class ApplyBudgetResponse(BaseModel):
    """Result of persisting a budget to a run (PUT /reorder-runs/{id}/budget)."""
    run_id: str
    budget: float
    funded_count: int
    deferred_count: int
    needs_cost_count: int
    funded_cash: float
    deferred_cash: float


class ReorderRecommendationRow(BaseModel):
    id: str
    type: str  # buy | disposition | exception
    sku: str
    product_name: Optional[str] = None
    abc_class: Optional[str] = None
    xyz_class: Optional[str] = None
    warehouse_code: Optional[str] = None
    warehouse_name: Optional[str] = None
    is_network: bool
    allocation: Optional[List[AllocationLine]] = None
    order_qty: Optional[float] = None
    recommended_qty: Optional[float] = None  # pre-rounding (order-up-to − net)
    reorder_point: Optional[float] = None
    min_qty: Optional[float] = None
    max_qty: Optional[float] = None
    order_up_to: Optional[float] = None
    net_position: Optional[float] = None
    days_of_cover: Optional[float] = None
    reason: Optional[str] = None
    reason_label: Optional[str] = None
    confidence: Optional[str] = None
    sample_size: int = 0
    supplier: Optional[SupplierChoice] = None
    alternatives: List[SupplierChoice] = []
    is_exception: bool = False
    # Re-plan (plan 5.1, G8): this row's product/location carried a decision on the run
    # this one superseded, but the suggestion changed - flagged so the buyer decides
    # again rather than assuming a carried figure. False on a run nobody re-planned.
    needs_recheck: bool = False
    disposition_action: Optional[str] = None
    transfer_flag: Optional[str] = None
    # --- frozen derivation inputs (plain-language explanation popup) ---
    forecast_daily_demand: Optional[float] = None
    lead_time_days: Optional[float] = None
    lead_time_source: Optional[str] = None
    safety_stock: Optional[float] = None
    safety_stock_method: Optional[str] = None
    safety_stock_fallback: Optional[str] = None
    service_level: Optional[float] = None
    safety_days: Optional[float] = None
    review_days: Optional[float] = None
    moq: Optional[float] = None
    order_multiple: Optional[float] = None
    policy_type: Optional[str] = None
    supplier_selection: Optional[str] = None
    # --- M4 cash co-pilot (buy rows only) ---
    unit_cost: Optional[float] = None
    cash_impact: Optional[float] = None
    rank: Optional[int] = None
    rank_score: Optional[float] = None
    funding_status: Optional[str] = None  # funded | deferred | needs_cost | null
    days_to_stockout: Optional[float] = None
    rank_factors: List[RankFactor] = []


class RecommendationPage(BaseModel):
    data: List[ReorderRecommendationRow]
    pagination: dict  # {page, limit, total, total_pages}
