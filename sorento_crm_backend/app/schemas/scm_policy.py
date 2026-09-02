"""SCM Policy Configuration - request/response schemas.

Mirror the Phase-2 FE contract documented at the top of
``app/(protected)/scm/policies/services/scmPolicyService.ts`` +
``types/policy.types.ts`` - every response field matches those TS types
field-for-field. Three policy families feed the shipped reorder engine:

  1. ``reorder_policy``        - scoped CRUD, resolved most-specific-active-wins.
  2. ``abc_xyz_policy``        - single global classification-threshold row.
  3. ``supplier_scoring_policy`` - single global supplier-scoring row.

Pure-field / cross-field-no-DB validation (AC-VAL-1..6, AC-CFG-2, AC-SUP-2) lives
here as Pydantic validators - the app's ``RequestValidationError`` handler
serializes them to 422. Coherence / uniqueness / referential checks that need the
DB (AC-VAL-7..9) raise ``AppException(422)`` from the service layer. No UUID is ever
rendered: ``scope_label`` is always human-readable (AC-NAV-4).
"""
from __future__ import annotations

from datetime import date
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, model_validator

ScopeType = Literal["sku", "product_class", "abc_xyz_cell", "global"]
# "reorder_level" is the manual-planning basis (`app.services.scm.reorder_policy`'s
# `_MANUAL_POLICY_TYPE`, migration 356) - the GLOBAL row carries it whenever S1's
# planning-mode switch is set to "manual". Missing here is the AC-3025 bug: the seeded
# global row can legitimately hold it, and `GET /scm/policies` 500'd serializing that
# row through this Literal.
PolicyType = Literal["reorder_point", "periodic_review", "min_max", "reorder_level"]
SafetyStockMethod = Literal["fixed_days", "statistical", "manual"]
SupplierSelection = Literal["primary", "best_score", "lowest_cost"]
# Where a plan row may cover a shortage from before it buys. `own_pool` is the default
# everywhere (captain: "either I use stock from BRW, or buy"); anything else is a 422.
CoverScope = Literal["own_pool", "all_locations"]
ResolutionReason = Literal["most-specific-active", "priority-tiebreak", "no-match", "inactive"]


# --- reorder policy ---------------------------------------------------------

class ReorderPolicyWrite(BaseModel):
    """Create/update payload - the row minus server-owned id + scope_label."""
    scope_type: ScopeType
    scope_ref: Optional[str] = None
    policy_type: PolicyType = "reorder_point"
    service_level: Optional[float] = None
    safety_stock_method: SafetyStockMethod = "fixed_days"
    safety_days: Optional[float] = None
    review_period_days: Optional[int] = None
    forecast_window_days: Optional[int] = None
    baseline_source: Optional[str] = None
    spike_handling: Optional[str] = None
    buy_scope: Optional[str] = None
    dead_stock_days: Optional[int] = None
    overstock_days: Optional[int] = None
    min_override: Optional[float] = None
    max_override: Optional[float] = None
    priority: int = 0
    is_active: bool = True
    supplier_selection: SupplierSelection = "primary"
    lead_time_default_days: Optional[int] = None
    # S13d trajectory windows: months of orders deciding sustaining vs dying off.
    # None = code default (retail 3, project 12). Config from day 1.
    trajectory_window_retail_months: Optional[int] = None
    trajectory_window_project_months: Optional[int] = None
    # S13e price-advice thresholds. None = code default (180 days, 5%).
    price_stale_after_days: Optional[int] = None
    price_movement_threshold_pct: Optional[float] = None

    @model_validator(mode="after")
    def _coherence(self) -> "ReorderPolicyWrite":
        # AC-VAL-2 - a global row never carries a scope_ref (stored NULL).
        if self.scope_type == "global":
            self.scope_ref = None
        # AC-VAL-1 - scope_ref is required for every non-global scope.
        elif not (self.scope_ref and str(self.scope_ref).strip()):
            raise ValueError("scope_ref is required for a non-global scope")

        # AC-VAL-3 - service_level strictly in (0, 1) when provided.
        if self.service_level is not None and not (0 < self.service_level < 1):
            raise ValueError("service_level must be strictly between 0 and 1")

        # AC-VAL-4 - day fields must be > 0 when provided.
        for name in ("safety_days", "review_period_days", "forecast_window_days",
                     "dead_stock_days", "overstock_days", "lead_time_default_days",
                     "trajectory_window_retail_months", "trajectory_window_project_months",
                     "price_stale_after_days", "price_movement_threshold_pct"):
            val = getattr(self, name)
            if val is not None and val <= 0:
                raise ValueError(f"{name} must be greater than 0")

        # AC-VAL-5 - min_override <= max_override when both provided.
        if (self.min_override is not None and self.max_override is not None
                and self.min_override > self.max_override):
            raise ValueError("min_override must be <= max_override")
        return self


class ReorderPolicyRow(ReorderPolicyWrite):
    """One reorder-policy row as returned by list / create / update / resolve."""
    id: str
    scope_label: str  # human-readable target, no UUID; "-" for global
    # READ-ONLY here. `cover_scope` is a GLOBAL setting with exactly one writer
    # (PUT /scm/config/cover-scope): it is deliberately absent from the write schema above,
    # because a grid save that omitted it would otherwise reset the global value to the
    # field default. Declared explicitly all the same - a field the response model does not
    # declare is dropped, so inheriting it was never an option.
    cover_scope: CoverScope = "own_pool"


class ReorderPolicyPage(BaseModel):
    data: List[ReorderPolicyRow]
    total: int


# --- classification thresholds (single global row) --------------------------

class AbcXyzWrite(BaseModel):
    """Fractions in (0,1): abc_a_pct = A cumulative share, abc_b_pct = B *band*
    share; a + b < 1 (remainder = C). xyz_* are demand-CV ceilings."""
    abc_a_pct: float
    abc_b_pct: float
    xyz_x_max: float
    xyz_y_max: float

    @model_validator(mode="after")
    def _check(self) -> "AbcXyzWrite":
        # AC-CFG-2
        if not (0 < self.abc_a_pct < 1):
            raise ValueError("abc_a_pct must be strictly between 0 and 1")
        if not (0 < self.abc_b_pct < 1):
            raise ValueError("abc_b_pct must be strictly between 0 and 1")
        if self.abc_a_pct + self.abc_b_pct >= 1:
            raise ValueError("abc_a_pct + abc_b_pct must be < 1 (remainder = class C)")
        if self.xyz_x_max <= 0 or self.xyz_y_max <= 0:
            raise ValueError("xyz thresholds must be greater than 0")
        if self.xyz_x_max > self.xyz_y_max:
            raise ValueError("xyz_x_max must be <= xyz_y_max")
        return self


class AbcXyzPolicy(AbcXyzWrite):
    exists: bool


# --- supplier scoring (single global row) -----------------------------------

class SupplierScoringWrite(BaseModel):
    delivery_weight: float
    quality_weight: float
    grace_days: int
    min_sample_size: int

    @model_validator(mode="after")
    def _check(self) -> "SupplierScoringWrite":
        # AC-SUP-2
        for name in ("delivery_weight", "quality_weight"):
            val = getattr(self, name)
            if not (0 <= val <= 1):
                raise ValueError(f"{name} must be in [0, 1]")
        if abs((self.delivery_weight + self.quality_weight) - 1.0) > 0.001:
            raise ValueError("delivery_weight + quality_weight must sum to 1.0")
        if self.grace_days < 0:
            raise ValueError("grace_days must be >= 0")
        if self.min_sample_size < 1:
            raise ValueError("min_sample_size must be >= 1")
        return self


class SupplierScoringPolicy(SupplierScoringWrite):
    exists: bool


# --- fulfilment priority (single active `scm.priority_policy` row) ----------
#
# PLAN-demo-followups-19aug-ladder-v2.md workstream C1/C2. Same shape as classification /
# supplier scoring - a single "the active row" GET/PUT - with one difference: a PUT here
# NEVER updates the row in place. `app.services.scm.priority.create_revision` writes a NEW
# row and activates it, so the ranking history a planner is judged against is never quietly
# rewritten (`app/models/scm.py::PriorityPolicy` docstring).

class FulfilmentPriorityWrite(BaseModel):
    """PUT body - the whole active policy, saved as one new revision.

    ``factors`` keys are the ranking factors `app.services.scm.priority.FACTOR_KEYS` knows
    (``po_document_sequence``, ``demand_class``, ``need_by_date``, ``document_age``,
    ``customer_credit``); an unrecognised key is stored and simply never scores anything,
    the same "a factor with no value is dropped" tolerance the engine already has for a
    factor no candidate carries. ``demand_class_weights`` is keyed by market-segment code
    (``project``, ``retail`` today).
    """
    factors: Dict[str, float]
    demand_class_weights: Dict[str, float]
    # Ladder v2 (E) settings this slice stores but does not yet wire into scoring.
    # A CALENDAR DATE (19 Aug follow-up, replacing the rolling `buy_all_horizon_days`
    # day count): a line required after this date is proposed as `Buy now`, untouched.
    # None clears the setting - no coverage limit is in force.
    reorder_coverage_until: Optional[date] = None
    # Borrow ladder v7.1 (R20, migration 443). Demand dated ON or AFTER this date is TBA:
    # it takes no supply, is never covered, and never donates.
    #
    # OPTIONAL on the body, and None means "leave the configured date alone" - the route
    # falls back to the ACTIVE revision's value the way it already does for `name` and
    # `notes`. A default of `2029-01-01` here would let any writer that does not know the
    # field yet (an older bundle, a script, n8n) silently move the TBA line back to the
    # column default while saving something else entirely.
    #
    # FRESHNESS is checked in the ROUTE, not here (fixed 30 Aug, review of S2). A TBA date
    # in the past turns every open order into a placeholder overnight - every line dated on
    # or after it stops taking supply, and "on or after yesterday" is the whole book - so
    # SETTING one is refused with 422. But the rule is about a CHANGE: once a configured
    # date has quietly passed, this panel saves weights, coverage dates and class weights
    # too, and refusing all of them because a field nobody touched is now historic locked
    # the whole screen. The comparison needs the active revision's value, which is a
    # database read, so it cannot live in a schema validator.
    #
    # `cross_group_borrow_max_qty` / `cross_group_borrow_max_pct` were dropped with the
    # cap they gated (R5): any ownership group may donate now.
    tba_date_from: Optional[date] = None
    # The flat 2-day transfer charge retired 31 Aug (R-B): a policy field, default 0, in
    # place of `front_planning_engine.TRANSFER_DAYS`'s literal. OPTIONAL and None-means-
    # unchanged, the same shape as `tba_date_from` above - an older writer that does not
    # know the field yet must not silently reset it to 0 while saving something else.
    # Negative is refused with a 422 in the service layer (`priority.save_fulfilment_priority`,
    # code `transfer_days_negative`), the same coded-422 shape as the TBA freshness rule,
    # because it too needs the ACTIVE policy's own value to decide "unchanged".
    transfer_days: Optional[int] = None
    # The site pool's share step settings (fulfilment feedback batch, S1, 2 Sep ruling
    # R-B, migration 460) - the same "optional, None-means-unchanged" shape as
    # `transfer_days` above, so an older writer that does not know either field yet
    # cannot silently reset it while saving something else. Range (0-365 / 0-100) is
    # checked here since, unlike the TBA freshness rule, it needs nothing from the
    # active row - AC-1.2, 0 is a valid value for both.
    immediate_window_days: Optional[int] = None
    pool_share_pct: Optional[int] = None

    @model_validator(mode="after")
    def _check(self) -> "FulfilmentPriorityWrite":
        for key, value in self.factors.items():
            if value < 0:
                raise ValueError(f"the weight for {key!r} must be >= 0")
        for key, value in self.demand_class_weights.items():
            if value < 0:
                raise ValueError(f"the demand-class weight for {key!r} must be >= 0")
        if self.immediate_window_days is not None and not (
            0 <= self.immediate_window_days <= 365
        ):
            raise ValueError("immediate_window_days must be between 0 and 365")
        if self.pool_share_pct is not None and not (0 <= self.pool_share_pct <= 100):
            raise ValueError("pool_share_pct must be between 0 and 100")
        # The TBA freshness rule is NOT here. It has to compare the submitted date with
        # the ACTIVE policy's own, which needs the database, so it lives in the route
        # (`policies.put_fulfilment_priority`). See the note on `tba_date_from` above.
        # `transfer_days`'s negative check is likewise in the service layer - see the note
        # on the field above.
        return self


class FulfilmentPriorityPolicy(BaseModel):
    """GET/PUT response - the active policy, or a documented default when none exists yet.

    A SIBLING of `FulfilmentPriorityWrite`, deliberately not a subclass of it. The write
    body carries a FRESHNESS rule (`tba_date_from` may not be in the past), which is a rule
    about what a person may SET today; inherited here it would validate what is READ, so
    every GET of a policy whose date has since passed would 500 on its own stored value.
    """
    factors: Dict[str, float]
    demand_class_weights: Dict[str, float]
    reorder_coverage_until: Optional[date] = None
    #: NOT NULL on the row, so a response always states it - past dates included, because
    #: this is what WAS saved and history is allowed to be old.
    tba_date_from: date
    #: NOT NULL on the row (migration 451), default 0. `response_model` drops an undeclared
    #: field, so this is declared explicitly even though it travels alongside the others.
    transfer_days: int = 0
    #: NOT NULL on the row (migration 460), defaults 30 / 50. Same "declared explicitly"
    #: reason as `transfer_days` above.
    immediate_window_days: int = 30
    pool_share_pct: int = 50
    name: str
    #: False only on a database that has never activated a fulfilment-priority policy at
    #: all - every seeded/migrated database (migration 385) has one.
    exists: bool


# --- resolution preview -----------------------------------------------------

class ResolutionChainLink(BaseModel):
    scope_type: ScopeType
    scope_ref: Optional[str] = None
    scope_label: str
    matched: bool
    is_winner: bool
    reason: ResolutionReason


class ResolutionProduct(BaseModel):
    product_code: str
    product_name: str


class ResolutionWarehouse(BaseModel):
    warehouse_code: str
    warehouse_name: str


class ResolutionResult(BaseModel):
    product: ResolutionProduct
    warehouse: Optional[ResolutionWarehouse] = None
    abc_xyz_cell: Optional[str] = None
    product_class: Optional[str] = None
    winner: Optional[ReorderPolicyRow] = None
    chain: List[ResolutionChainLink]
