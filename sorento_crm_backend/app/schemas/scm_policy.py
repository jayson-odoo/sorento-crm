"""SCM Policy Configuration — request/response schemas.

Mirror the Phase-2 FE contract documented at the top of
``app/(protected)/scm/policies/services/scmPolicyService.ts`` +
``types/policy.types.ts`` — every response field matches those TS types
field-for-field. Three policy families feed the shipped reorder engine:

  1. ``reorder_policy``          — scoped CRUD, resolved most-specific-active-wins.
  2. ``abc_xyz_policy``          — single global classification-threshold row.
  3. ``supplier_scoring_policy`` — single global supplier-scoring row.

Pure-field / cross-field-no-DB validation (AC-VAL-1..6, AC-CFG-2, AC-SUP-2) lives
here as Pydantic validators — the app's ``RequestValidationError`` handler
serializes them to 422. Coherence / uniqueness / referential checks that need the
DB (AC-VAL-7..9) raise ``AppException(422)`` from the service layer. No UUID is ever
rendered: ``scope_label`` is always human-readable (AC-NAV-4).
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, model_validator

ScopeType = Literal["sku", "product_class", "abc_xyz_cell", "global"]
PolicyType = Literal["reorder_point", "periodic_review", "min_max"]
SafetyStockMethod = Literal["fixed_days", "statistical", "manual"]
SupplierSelection = Literal["primary", "best_score", "lowest_cost"]
# Where a plan row may cover a shortage from before it buys. `own_pool` is the default
# everywhere (captain: "either I use stock from BRW, or buy"); anything else is a 422.
CoverScope = Literal["own_pool", "all_locations"]
ResolutionReason = Literal["most-specific-active", "priority-tiebreak", "no-match", "inactive"]


# --- reorder policy ---------------------------------------------------------

class ReorderPolicyWrite(BaseModel):
    """Create/update payload — the row minus server-owned id + scope_label."""
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
        # AC-VAL-2 — a global row never carries a scope_ref (stored NULL).
        if self.scope_type == "global":
            self.scope_ref = None
        # AC-VAL-1 — scope_ref is required for every non-global scope.
        elif not (self.scope_ref and str(self.scope_ref).strip()):
            raise ValueError("scope_ref is required for a non-global scope")

        # AC-VAL-3 — service_level strictly in (0, 1) when provided.
        if self.service_level is not None and not (0 < self.service_level < 1):
            raise ValueError("service_level must be strictly between 0 and 1")

        # AC-VAL-4 — day fields must be > 0 when provided.
        for name in ("safety_days", "review_period_days", "forecast_window_days",
                     "dead_stock_days", "overstock_days", "lead_time_default_days",
                     "trajectory_window_retail_months", "trajectory_window_project_months",
                     "price_stale_after_days", "price_movement_threshold_pct"):
            val = getattr(self, name)
            if val is not None and val <= 0:
                raise ValueError(f"{name} must be greater than 0")

        # AC-VAL-5 — min_override <= max_override when both provided.
        if (self.min_override is not None and self.max_override is not None
                and self.min_override > self.max_override):
            raise ValueError("min_override must be <= max_override")
        return self


class ReorderPolicyRow(ReorderPolicyWrite):
    """One reorder-policy row as returned by list / create / update / resolve."""
    id: str
    scope_label: str  # human-readable target, no UUID; "—" for global
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
