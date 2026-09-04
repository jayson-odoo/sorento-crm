"""SCM (Supply Chain & Inventory Optimisation) module brain models.

All tables live in a dedicated ``scm`` Postgres schema (``__table_args__`` carries
``{"schema": "scm"}``). They die with the module on uninstall; the core business
records (sales_order/purchase_order + product_suppliers/suppliers/picking_lines
extensions) stay in ``public``.

Cross-schema FKs into ``public`` are NORMAL Postgres foreign keys - public is the
default search-path schema, so references are unqualified (``ForeignKey("products.id")``).
scm→scm FKs are schema-qualified (``ForeignKey("scm.reorder_run.id")``).

Per AC-M0.3 every table carries ``source_system`` + ``source_ref`` (``'seed'`` for demo
rows, ``'manual'`` for future UI rows).
"""
from datetime import date

from sqlalchemy import (
    CheckConstraint,
    Column,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    Integer,
    Numeric,
    Date,
    Index,
    SmallInteger,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
from app.models.base import CompanyScopedMixin
import uuid


def _uuid_str():
    return str(uuid.uuid4())


class ReorderPolicy(Base):
    """Reorder configuration resolved SKU → abc/xyz cell → product_class → global."""
    __tablename__ = "reorder_policy"
    __table_args__ = {"schema": "scm"}

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    scope_type = Column(String(30), nullable=False)  # sku | product_class | abc_xyz_cell | global
    scope_ref = Column(String(255), nullable=True)
    # reorder_point | periodic_review | min_max | reorder_level. This field IS the planning
    # basis switch: it already resolves global -> product_class -> sku, so turning the
    # forecast basis back on for a class or a SKU is a row here, never a deploy.
    policy_type = Column(String(30), nullable=False)
    service_level = Column(Numeric, nullable=True)
    safety_stock_method = Column(String(30), nullable=True)  # statistical | fixed_days | manual
    safety_days = Column(Numeric, nullable=True)
    review_period_days = Column(Integer, nullable=True)
    forecast_window_days = Column(Integer, nullable=True)
    baseline_source = Column(String(30), nullable=True)  # continuous_only | all
    spike_handling = Column(String(30), nullable=True)  # committed_only | statistical | ignore
    buy_scope = Column(String(20), nullable=True)  # network | warehouse
    dead_stock_days = Column(Integer, nullable=True)
    overstock_days = Column(Integer, nullable=True)  # M2 (overstock state)
    # Coverage Timeline config (S3). This table is the right home rather than a new one:
    # it already carries scope resolution (scope_type / scope_ref / priority) plus an
    # admin UI, so a per-warehouse or per-category override comes free.
    # How far ahead the dated coverage axis runs. NULL = unconfigured, resolved to
    # DEFAULT_PLANNING_HORIZON_MONTHS by the service.
    planning_horizon_months = Column(Integer, nullable=True)
    # Cross-site transfer economics. Both stay NULL when unconfigured and are NEVER
    # defaulted to 0: a zero cost reads as a free move and a zero lead time as an instant
    # one, and either would make a transfer proposal look better than the truth.
    transfer_lead_time_days = Column(Integer, nullable=True)
    transfer_cost_per_unit = Column(Numeric(12, 2), nullable=True)
    # May a sibling bin's surplus cover another bin's shortage? OFF: this phase does not
    # propose transfers, so it must not assume one. Both behaviours stay in the engine.
    pool_netting = Column(Boolean, nullable=True, server_default=text("false"))
    # Where "use stock" may draw from before buying: own_pool (the row's own site) or
    # all_locations. Unset reads as own_pool, never as the whole network.
    cover_scope = Column(String(16), nullable=True, server_default=text("'own_pool'"))
    # reorder_level basis dials. How many months of movement to study, and how many months
    # of it a level should cover. Both only ever shape the SUGGESTION.
    level_study_months = Column(Integer, nullable=True, server_default=text("3"))
    level_cover_months = Column(Numeric(6, 2), nullable=True, server_default=text("2"))
    # S13d trajectory windows: how many months of orders decide sustaining vs dying off.
    # NULL = code default (retail 3, project 12). Config from day 1, never a constant.
    trajectory_window_retail_months = Column(Integer, nullable=True)
    trajectory_window_project_months = Column(Integer, nullable=True)
    # S13e price-advice thresholds: when a last price is too old to trust, and what
    # price difference is worth acting on (staleness flag AND change-supplier gate).
    # NULL = code default (180 days, 5%).
    price_stale_after_days = Column(Integer, nullable=True)
    price_movement_threshold_pct = Column(Numeric(6, 2), nullable=True)
    factor_toggles = Column(JSONB, nullable=True)
    factor_weights = Column(JSONB, nullable=True)
    min_override = Column(Numeric, nullable=True)
    max_override = Column(Numeric, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    priority = Column(Integer, nullable=True)
    source_system = Column(String, nullable=True)
    source_ref = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)


class ReorderLevel(Base, CompanyScopedMixin):
    """The reorder level a buyer owns, and the suggestion it was derived from.

    Two columns, never one. `level` is what the plan uses and only a person sets it;
    `suggested_level` is what three months of movement implies and a refresh may move it
    freely. Merging them would let a recompute silently change what gets bought, which is
    the behaviour the reorder_level basis exists to end.

    A NULL `level` is NOT a level of zero: it means nobody has set one, and the engine emits
    the item as `needs_level` rather than planning it.
    """
    __tablename__ = "reorder_level"
    __table_args__ = {"schema": "scm"}

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    product_id = Column(UUID(as_uuid=False), nullable=False)
    # NULL = the level applies to the product everywhere; a per-location row wins.
    warehouse_id = Column(UUID(as_uuid=False), nullable=True)
    level = Column(Numeric(18, 4), nullable=True)
    # AutoCount's own reorder quantity, uploaded with the level (S13c). Nothing in our UI
    # edits it: it is the starting point the quantity suggestion offers, with the engine's
    # computed figure shown beside it when they disagree.
    reorder_qty = Column(Numeric(18, 4), nullable=True)
    source = Column(String(30), nullable=True)  # manual | accepted_suggestion | autocount
    suggested_level = Column(Numeric(18, 4), nullable=True)
    suggested_at = Column(DateTime(timezone=False), nullable=True)
    # The months studied, their average, the cover applied - so the number is arguable.
    suggestion_basis = Column(JSONB, nullable=True)
    # S14: the buyer's amendment of the suggestion, kept BESIDE the engine's number so the
    # screen can say "you set 30; the engine said 24". A fresh engine refresh clears it -
    # the amendment was a judgement about that run's suggestion, not a standing override.
    amended_level = Column(Numeric(14, 4), nullable=True)
    amended_at = Column(DateTime(timezone=False), nullable=True)
    amended_by = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)


class ItemClassification(Base):
    """ABC/XYZ classification per SKU×warehouse (network rollup = null warehouse)."""
    __tablename__ = "item_classification"
    __table_args__ = (
        UniqueConstraint("product_id", "warehouse_id", name="uq_scm_item_classification_product_warehouse"),
        {"schema": "scm"},
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    product_id = Column(UUID(as_uuid=False), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    warehouse_id = Column(UUID(as_uuid=False), ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=True)
    abc_class = Column(String(1), nullable=True)
    xyz_class = Column(String(1), nullable=True)
    annual_value = Column(Numeric, nullable=True)
    # Migration 389 (captain, 19 Aug 2026): hot-selling is judged by delivered QUANTITY
    # per demand class (project vs retail/dealer, see app.services.scm.demand_class),
    # never money - unlike `abc_class`/`annual_value` above (the reorder engine's
    # inventory-value lens), which stay unchanged. A SKU can be A for a project customer
    # and C for the dealer channel. NULL = no demand of that class in the trailing-12mo
    # window (unknown), never a computed C.
    abc_class_project = Column(String(1), nullable=True)
    abc_class_retail = Column(String(1), nullable=True)
    annual_qty_project = Column(Numeric, nullable=True)
    annual_qty_retail = Column(Numeric, nullable=True)
    demand_cv = Column(Numeric, nullable=True)
    computed_at = Column(DateTime(timezone=False), nullable=True)
    source_system = Column(String, nullable=True)
    source_ref = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)


class AbcXyzPolicy(Base):
    """Configurable ABC value cut-points + XYZ CV thresholds (M2)."""
    __tablename__ = "abc_xyz_policy"
    __table_args__ = {"schema": "scm"}

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    abc_a_pct = Column(Numeric, nullable=True)
    abc_b_pct = Column(Numeric, nullable=True)
    xyz_x_max = Column(Numeric, nullable=True)
    xyz_y_max = Column(Numeric, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    source_system = Column(String, nullable=True)
    source_ref = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)


class SupplierScoringPolicy(Base):
    """Weights + sample thresholds for supplier composite scoring."""
    __tablename__ = "supplier_scoring_policy"
    __table_args__ = {"schema": "scm"}

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    delivery_weight = Column(Numeric, nullable=True)
    quality_weight = Column(Numeric, nullable=True)
    grace_days = Column(Integer, nullable=True)  # M2 (on-time grace)
    min_sample_size = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    source_system = Column(String, nullable=True)
    source_ref = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)


class SupplierPerformance(Base):
    """Computed supplier scorecard per supplier×product (product null = supplier-level fallback)."""
    __tablename__ = "supplier_performance"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    supplier_id = Column(UUID(as_uuid=False), ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(UUID(as_uuid=False), ForeignKey("products.id", ondelete="CASCADE"), nullable=True)
    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)
    on_time_rate = Column(Numeric, nullable=True)
    avg_lead_time_days = Column(Numeric, nullable=True)
    lead_time_variance = Column(Numeric, nullable=True)
    reject_rate = Column(Numeric, nullable=True)
    fill_rate = Column(Numeric, nullable=True)
    composite_score = Column(Numeric, nullable=True)
    sample_size = Column(Integer, nullable=True)
    confidence = Column(String(20), nullable=True)
    computed_at = Column(DateTime(timezone=False), nullable=True)
    source_system = Column(String, nullable=True)
    source_ref = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_scm_supplier_performance_supplier_id", "supplier_id"),
        Index("ix_scm_supplier_performance_product_id", "product_id"),
        {"schema": "scm"},
    )


class PurchasingBudget(Base, CompanyScopedMixin):
    """Cash budget window for the reorder run (global | supplier | category)."""
    __tablename__ = "purchasing_budget"
    __table_args__ = {"schema": "scm"}

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)
    budget_amount = Column(Numeric(15, 2), nullable=True)
    currency = Column(String(3), nullable=True)
    scope_type = Column(String(20), nullable=True)  # global | supplier | category
    scope_ref = Column(String(255), nullable=True)
    set_by = Column(String, nullable=True)
    note = Column(Text, nullable=True)
    source_system = Column(String, nullable=True)
    source_ref = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)


class ReorderRun(Base, CompanyScopedMixin):
    """One planning run; recommendations freeze their inputs against it."""
    __tablename__ = "reorder_run"
    __table_args__ = {"schema": "scm"}

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    created_by = Column(String, nullable=True)
    status = Column(String(30), default="running", nullable=False, server_default="running")  # running | completed | failed
    warehouse_ids = Column(JSONB, nullable=True)
    # The product scope of a manual plan. NULL means none was asked for (the daily run,
    # which plans everything); an EMPTY list means one was asked for and nothing resolved
    # (a mistyped code), which must plan nothing rather than widen to the whole catalogue.
    product_ids = Column(JSONB, nullable=True)
    buy_scope = Column(String(20), nullable=True)  # network | warehouse
    budget_id = Column(UUID(as_uuid=False), ForeignKey("scm.purchasing_budget.id", ondelete="SET NULL"), nullable=True)
    budget_amount = Column(Numeric(15, 2), nullable=True)  # M4 - chosen budget the "Apply budget" action persists
    include_market = Column(Boolean, nullable=False, default=False, server_default="false")  # M7 - opt-in market-trend priority factor
    # "Plan until" (captain, 20 Aug): demand needed AFTER this date is excluded from the
    # run's netting; NULL (the default) plans every open SO line regardless of need date,
    # unchanged from before this column existed. Stamped once at creation, like
    # decision_grain - a per-RUN choice, not a live policy, so it cannot move under a run
    # already planned.
    plan_horizon_date = Column(Date, nullable=True)
    policy_snapshot_ref = Column(String, nullable=True)
    started_at = Column(DateTime(timezone=False), nullable=True)
    finished_at = Column(DateTime(timezone=False), nullable=True)
    error_text = Column(Text, nullable=True)  # set on status='failed'
    run_log = Column(JSONB, nullable=True)  # {stage, buy, disposition, exceptions, total_cash_impact, recommendation_count, duration_ms}
    overview = Column(Text, nullable=True)  # LLM (M5) - lazy-cached run-level AI overview
    source_system = Column(String, nullable=True)
    source_ref = Column(String, nullable=True)
    # Front planning (plan 5.1 / 5.4). `decision_grain` is the ONE grain this run may be
    # decided at - `product` (the order_summary_row chosen quantity) or `location` (the
    # recommendation decisions and overrides) - stamped from the admin plan-grain policy
    # when the run is created and never changed, so a later policy edit cannot move a
    # frozen run and the two grains can never order the same requirement.
    # `front_planning_contract_version` is 1 on every run created under the contract and
    # NULL on every run that predates it; NULL is what makes a run legacy and read-only,
    # and neither column is backfilled.
    decision_grain = Column(String(20), nullable=True)
    front_planning_contract_version = Column(SmallInteger, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    # S3 perf quick wins (PLAN-scm-reorder-oi-feedback-1sep.md, AC-3.3): the plans list and
    # its Decided sort used to LEFT JOIN the whole `purchase_order_lines` table per page to
    # answer "how many of this run's products are decided / confirmed" (by DISTINCT
    # PRODUCT, R14) - `decision_service._refresh_run_counts` keeps these three current on
    # every decision write (accept/adjust/reject, a row decision, confirm, reset) and at run
    # completion, so a read is a plain column instead of a join.
    planned_count = Column(Integer, nullable=False, default=0, server_default=text("0"))
    decided_count = Column(Integer, nullable=False, default=0, server_default=text("0"))
    confirmed_count = Column(Integer, nullable=False, default=0, server_default=text("0"))
    # Re-plan supersede link (plan 5.1 / G8). Two columns rather than one, so the RQ worker
    # can find the OLD run's decisions the moment it starts (`supersedes_run_id`, stamped at
    # creation) without waiting on the reverse pointer, which is only written once THIS run
    # actually completes (`superseded_by_run_id`, stamped on the OLD row) - a still-running
    # or failed re-plan must never make a still-valid old run look superseded.
    supersedes_run_id = Column(
        UUID(as_uuid=False), ForeignKey("scm.reorder_run.id", ondelete="SET NULL"), nullable=True
    )
    superseded_by_run_id = Column(
        UUID(as_uuid=False), ForeignKey("scm.reorder_run.id", ondelete="SET NULL"), nullable=True
    )

    recommendations = relationship(
        "ReorderRecommendation",
        back_populates="run",
        cascade="all, delete-orphan",
    )


class ReorderRecommendation(Base, CompanyScopedMixin):
    """A frozen buy/disposition recommendation produced by a run."""
    __tablename__ = "reorder_recommendation"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    run_id = Column(UUID(as_uuid=False), ForeignKey("scm.reorder_run.id", ondelete="CASCADE"), nullable=False)
    rec_type = Column(String(20), nullable=True)  # buy | disposition | exception (discriminator + filter)
    product_id = Column(UUID(as_uuid=False), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    warehouse_id = Column(UUID(as_uuid=False), ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True)  # null = network
    supplier_id = Column(UUID(as_uuid=False), ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True)
    net_position = Column(Numeric, nullable=True)
    reorder_point = Column(Numeric, nullable=True)
    forecast_daily_demand = Column(Numeric, nullable=True)
    days_of_cover = Column(Numeric, nullable=True)
    recommended_qty = Column(Numeric, nullable=True)
    rounded_qty = Column(Numeric, nullable=True)
    #: The buyer's own MoQ, replacing the frozen master figure for THIS row only. NULL =
    #: use the master value frozen in `inputs.moq` at run time. Setting it RECALCULATES
    #: AND PERSISTS `rounded_qty` / `cash_impact` (see `reorder_run_service.set_moq_override`)
    #: so every consumer of those columns - draft PO lines, the budget allocator, sort -
    #: is correct with no override-awareness of its own. `inputs` (AC-M3.11's freeze) never
    #: moves - a fresh run with no override still reproduces byte-for-byte.
    moq_override = Column(Numeric, nullable=True)
    #: What the SUPPLIER charges, in `currency`. This is the figure a PO will carry.
    unit_cost = Column(Numeric(12, 2), nullable=True)
    #: What the buy costs in the BASE currency, always. The budget is one pot of ringgit, so
    #: a USD line summed into it at its face value understates the cash fourfold.
    cash_impact = Column(Numeric(15, 2), nullable=True)
    currency = Column(String(3), nullable=True)
    #: The rate this run used, frozen, so a plan printed today still explains its own
    #: figures after somebody updates the rate tomorrow.
    rate_to_base = Column(Numeric(18, 6), nullable=True)
    rate_as_of = Column(Date, nullable=True)
    urgency_score = Column(Numeric, nullable=True)
    priority_score = Column(Numeric, nullable=True)
    rank_score = Column(Numeric, nullable=True)  # M4 (cash stage, frozen)
    rank = Column(Integer, nullable=True)  # M4
    confidence_band = Column(String(20), nullable=True)
    triggered_reason = Column(String(100), nullable=True)  # human reason label
    allocation = Column(JSONB, nullable=True)  # M3 network allocation breakdown (per-wh, with codes)
    inputs = Column(JSONB, nullable=True)  # frozen engine inputs (AC-M3.11 reproducibility) + display extras
    explanation = Column(Text, nullable=True)  # LLM (M5)
    market_advisory = Column(Text, nullable=True)  # LLM (M5)
    funding_status = Column(String(20), nullable=True)  # funded | deferred
    status = Column(String(20), default="proposed", nullable=False, server_default="proposed")  # proposed | accepted | adjusted | dismissed
    # Whether THIS location's purchase order has been keyed into AutoCount (AC-E2.2), for a
    # run decided at LOCATION grain, where the decision lives here rather than on the
    # product summary row. Same three values and the same manual semantics as
    # `OrderSummaryRow.keyed_status`; exactly one of the two applies to a run (AC-F09).
    keyed_status = Column(
        String(20), nullable=False, default="not_keyed", server_default=text("'not_keyed'")
    )
    keyed_by = Column(String, nullable=True)
    keyed_at = Column(DateTime(timezone=False), nullable=True)
    source_system = Column(String, nullable=True)
    source_ref = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    # S3 perf quick wins (AC-3.4): the pool a row's location(s) draw on, precomputed at
    # generation time (`reorder_run_service._plan_basis`) rather than re-derived on every
    # read of `list_recommendations` via a per-row LATERAL that unnests
    # `inputs.plan_basis.locations` - that LATERAL ran on the majority of rows (every
    # product-grain row names no single warehouse) and was the read path's own cost, not a
    # one-off. NULL on a network/product row whose members span more than one pool (the
    # LATERAL's own "name none rather than one of several" rule, unchanged).
    pool_warehouse_id = Column(
        UUID(as_uuid=False), ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True
    )
    pool_warehouse_code = Column(String(50), nullable=True)

    run = relationship("ReorderRun", back_populates="recommendations")
    overrides = relationship(
        "RecommendationOverride",
        back_populates="recommendation",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_scm_reorder_recommendation_run_id", "run_id"),
        Index("ix_scm_reorder_recommendation_product_id", "product_id"),
        Index("ix_scm_reorder_recommendation_run_keyed", "run_id", "keyed_status"),
        CheckConstraint(
            "keyed_status IN ('not_keyed', 'keying', 'keyed')",
            name="ck_scm_reorder_recommendation_keyed_status",
        ),
        {"schema": "scm"},
    )


class RecommendationOverride(Base, CompanyScopedMixin):
    """Append-only human override of a recommendation; never mutates the recommendation."""
    __tablename__ = "recommendation_override"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    recommendation_id = Column(UUID(as_uuid=False), ForeignKey("scm.reorder_recommendation.id", ondelete="CASCADE"), nullable=False)
    original_qty = Column(Numeric, nullable=True)
    override_qty = Column(Numeric, nullable=True)
    override_supplier_id = Column(UUID(as_uuid=False), ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True)  # M4
    reason_text = Column(Text, nullable=True)
    reason_code = Column(String(50), nullable=True)  # LLM-classified
    reason_confidence = Column(Numeric, nullable=True)
    suggested_action = Column(String(100), nullable=True)  # deterministic
    action_applied = Column(Boolean, default=False, nullable=False)
    overridden_by = Column(String, nullable=True)
    overridden_at = Column(DateTime(timezone=False), nullable=True)
    source_system = Column(String, nullable=True)
    source_ref = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    recommendation = relationship("ReorderRecommendation", back_populates="overrides")

    __table_args__ = (
        Index("ix_scm_recommendation_override_recommendation_id", "recommendation_id"),
        {"schema": "scm"},
    )


class PlanRowDecision(Base, CompanyScopedMixin):
    """The buyer's CURRENT decision on one recommendation row - buy / use stock / use an
    existing PO / skip, or a mixture of the first three.

    > captain, 21 Aug (third time this fix requested): "I want the decision made here...
    > there is only buy / use stock / use SPO / mixture, right" - the results grid used to
    > send the buyer to the product sheet to decide ("Decided on the Product sheet - open
    > it"); this is that decision, recorded on the row.

    ONE row per recommendation, kept CURRENT rather than append-only like
    ``RecommendationOverride`` - "record a decision" replaces whatever was there,
    "clear a decision" deletes the row outright, so `undecided` is the absence of a row
    here exactly as it is the absence of an entry in the FE's own in-memory
    `PlanDecisionMap` (`reorder/lib/planDecisions.ts`) before this landed.

    Recorded on ANY decidable rec_type (buy / covered / needs_level / disposition) -
    the captain's question was the same shape for every row on the grid, not just buy
    recs, so this is guarded only by ``plan_grain.assert_not_legacy`` (a closed run
    stays read-only) and NEVER by ``decision_grain``: a product-grain run's grouped
    product fans this write out one member recommendation id at a time, the same way
    ``reorder_run_service.set_moq_override`` already fans a MoQ edit out to every
    member - the write itself does not need to know which grain it landed on.
    A row written HERE DOES reach a draft PO on a product-grain run too, as of the
    captain's same-day correction (21 Aug): "I need the confirm decision to be in
    reorder planning, not in another page called order summary" - the results grid IS
    where a product-grain buyer decides, so ``decision_service._confirm_product_grain``
    reads THIS table first (grouped one row per product, since ``usePlanLines.decide``
    fans the SAME decision out to every member rec of a grouped row rather than
    splitting it - consolidated ONCE per product on confirm, then split back across
    the group's REAL member warehouses so every drafted line names one, never summed
    per member and never a NULL one, B2). ``OrderSummaryRow.chosen_qty``
    (``summary_order_service.record_decision``, the Summary Order Report's own older
    quantity sheet) is read only as a FALLBACK, for a product this table holds no
    decision for - mirrors this same table's own precedence over the legacy
    accepted/adjusted/dismissed status on the location side. On a LOCATION-grain run
    this table still reaches a PO the way it always has, via
    ``_confirm_location_grain``.

    ``use_stock`` records the buyer's INTENTION only - no stock is reserved or held by
    writing this row. An actual hold would collide with the project-sales ladder's own
    reservations against the same stock (`PLAN-scm-reorder-decision-to-autocount.md`,
    open question, answered: intention-only, never a reservation).
    """
    __tablename__ = "plan_row_decision"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    recommendation_id = Column(
        UUID(as_uuid=False),
        ForeignKey("scm.reorder_recommendation.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind = Column(String(20), nullable=False)  # buy | use_stock | use_po | skip | mixture
    buy_qty = Column(Numeric, nullable=True)
    #: [{location: warehouse CODE, location_name, qty}] - the bins the buyer named for
    #: the stock portion. Never a UUID on the wire (mirrors override_supplier_code).
    stock_takes = Column(JSONB, nullable=True)
    po_qty = Column(Numeric, nullable=True)
    #: PO numbers the "use PO" portion points at - display-only, no FK (the existing PO
    #: book is read by number elsewhere; this is the buyer's own note of which one(s)).
    po_refs = Column(JSONB, nullable=True)
    reason_text = Column(Text, nullable=True)
    #: `use_last` (cost the line at what we last paid) or `ask_new` (the price is still a
    #: question, so the drafted line carries none). AC-R13.
    price_mode = Column(String(20), nullable=True)
    #: The supplier the BUYER chose, when they overrode the engine's. NULL = the
    #: recommendation's own proposed supplier stands (AC-R14).
    supplier_id = Column(
        UUID(as_uuid=False), ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True
    )
    #: The price this row is costed at, in the chosen supplier's currency. NULL under
    #: `ask_new`: an unknown price is not a price of zero.
    unit_cost = Column(Numeric, nullable=True)
    decided_by = Column(String, nullable=True)
    decided_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    recommendation = relationship("ReorderRecommendation")

    __table_args__ = (
        Index(
            "uq_scm_plan_row_decision_recommendation_id", "recommendation_id", unique=True
        ),
        {"schema": "scm"},
    )


class OverrideReason(Base):
    """Master vocabulary of override reason codes (LLM classifies into these)."""
    __tablename__ = "override_reason"
    __table_args__ = {"schema": "scm"}

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    reason_code = Column(String(50), unique=True, nullable=False)
    label = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    source_system = Column(String, nullable=True)
    source_ref = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)


class ReasonActionMap(Base):
    """Deterministic reason_code → suggested policy action mapping."""
    __tablename__ = "reason_action_map"
    __table_args__ = {"schema": "scm"}

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    reason_code = Column(String(50), nullable=False)
    suggested_action = Column(String(100), nullable=True)
    target_policy_field = Column(String(100), nullable=True)
    adjustment = Column(String(100), nullable=True)
    trigger_type = Column(String(20), nullable=True)  # immediate | pattern (M4)
    threshold_n = Column(Integer, nullable=True)  # M4
    window_days = Column(Integer, nullable=True)  # M4
    source_system = Column(String, nullable=True)
    source_ref = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)


class CashRankingPolicy(Base):
    """Factor weights for cash-constrained recommendation ranking (M4)."""
    __tablename__ = "cash_ranking_policy"
    __table_args__ = {"schema": "scm"}

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    weight_urgency = Column(Numeric, nullable=True)
    weight_margin = Column(Numeric, nullable=True)
    weight_abc = Column(Numeric, nullable=True)
    weight_priority = Column(Numeric, nullable=True)
    weight_committed = Column(Numeric, nullable=True)
    weight_market = Column(Numeric, nullable=True)  # M7 - market-trend priority factor
    is_active = Column(Boolean, default=True, nullable=False)
    note = Column(Text, nullable=True)
    source_system = Column(String, nullable=True)
    source_ref = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)


class DemandNatureMap(Base):
    """Configurable order_type (lookup option) → demand nature (continuous|spike)."""
    __tablename__ = "demand_nature_map"
    __table_args__ = {"schema": "scm"}

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    order_type_option_id = Column(UUID(as_uuid=False), ForeignKey("lookup_options.id", ondelete="CASCADE"), nullable=True)
    demand_nature = Column(String(20), nullable=True)  # continuous | spike
    source_system = Column(String, nullable=True)
    source_ref = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)


class DemandStat(Base):
    """Stored demand rate per SKU×warehouse (written by the M2 analytics job; empty at M0)."""
    __tablename__ = "demand_stat"
    __table_args__ = (
        UniqueConstraint("product_id", "warehouse_id", name="uq_scm_demand_stat_product_warehouse"),
        {"schema": "scm"},
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    product_id = Column(UUID(as_uuid=False), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    warehouse_id = Column(UUID(as_uuid=False), ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=True)
    avg_daily_demand = Column(Numeric, nullable=True)
    baseline_rate = Column(Numeric, nullable=True)
    spike_rate = Column(Numeric, nullable=True)
    demand_cv = Column(Numeric, nullable=True)
    variability = Column(Numeric, nullable=True)
    window_days = Column(Integer, nullable=True)
    sample_days = Column(Integer, nullable=True)
    method = Column(String(30), nullable=True)
    channel_split = Column(JSONB, nullable=True)
    computed_at = Column(DateTime(timezone=False), nullable=True)
    source_system = Column(String, nullable=True)
    source_ref = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)


class MarketResearchTopic(Base):
    """Configurable market/economic research topic driving web-search signals (M5)."""
    __tablename__ = "market_research_topic"
    __table_args__ = {"schema": "scm"}

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    label = Column(String(255), nullable=False)
    category_ref = Column(String(255), nullable=True)
    currency = Column(String(3), nullable=True)
    search_prompt = Column(Text, nullable=True)
    cadence = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    source_system = Column(String, nullable=True)
    source_ref = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)


class MarketSignal(Base):
    """Cached advisory-only market signal captured for a topic (M5)."""
    __tablename__ = "market_signal"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    topic_id = Column(UUID(as_uuid=False), ForeignKey("scm.market_research_topic.id", ondelete="CASCADE"), nullable=True)
    category_ref = Column(String(255), nullable=True)
    currency = Column(String(3), nullable=True)
    value = Column(Numeric, nullable=True)
    trend = Column(String(30), nullable=True)
    summary = Column(Text, nullable=True)
    source_url = Column(Text, nullable=True)
    # M8-F: multiple citation sources ([{url, title}, ...]) harvested from the web-search
    # result, so the market card can PROVE the figure with several links. Falls back to
    # [source_url] for legacy signals that carry only the single url.
    sources = Column(JSONB, nullable=True)
    captured_at = Column(DateTime(timezone=False), nullable=True)
    source_system = Column(String, nullable=True)
    source_ref = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_scm_market_signal_topic_id", "topic_id"),
        Index("ix_scm_market_signal_category_ref", "category_ref"),
        {"schema": "scm"},
    )


class ScmAnalyticsRun(Base, CompanyScopedMixin):
    """Observability log for the M2 demand/classification/supplier analytics job."""
    __tablename__ = "scm_analytics_run"
    __table_args__ = {"schema": "scm"}

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    started_at = Column(DateTime(timezone=False), nullable=True)
    finished_at = Column(DateTime(timezone=False), nullable=True)
    status = Column(String(30), nullable=True)
    scope = Column(JSONB, nullable=True)
    counts = Column(JSONB, nullable=True)
    window_days = Column(Integer, nullable=True)
    config_ref = Column(String, nullable=True)
    error_text = Column(Text, nullable=True)
    source_system = Column(String, nullable=True)
    source_ref = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)


class MarketResearchRun(Base, CompanyScopedMixin):
    """Observability log for the M5 web-search market research job (mirrors
    ``scm_analytics_run``): one row per run, status running → completed | failed."""
    __tablename__ = "market_research_run"
    __table_args__ = {"schema": "scm"}

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    status = Column(String(30), default="running", nullable=False, server_default="running")  # running | completed | failed
    started_at = Column(DateTime(timezone=False), nullable=True)
    finished_at = Column(DateTime(timezone=False), nullable=True)
    topic_count = Column(Integer, nullable=True)  # active topics searched this run
    signal_count = Column(Integer, nullable=True)  # fresh signals captured this run
    error_text = Column(Text, nullable=True)  # human message when status='failed'
    source_system = Column(String, nullable=True)
    source_ref = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)


class PriorityPolicy(Base):
    """Fulfilment Priority: the order in which competing demand gets scarce stock.

    Module-side on purpose. This is a tuning knob, and a tenant without SCM has no
    allocation suggestions to rank, so it dies with the module while the OUTCOMES it
    produced (SPO allocations, sent notices) survive in ``public``.

    Applied at BOTH allocation moments - what goes in a container, and which order
    arriving stock is assigned to. The same row must serve both or the two decisions
    contradict each other.

    ``factors`` and ``demand_class_weights`` are JSONB rather than a column per factor so
    adding a factor, or a third demand class, is a data change and never a migration.
    Exactly one row may be active, enforced by a partial unique index rather than by
    remembering to check (the ``system_settings`` singleton lesson).
    """
    __tablename__ = "priority_policy"
    __table_args__ = {"schema": "scm"}

    # server_default too: the row is seeded by raw SQL (migration 311 and bootstrap_env),
    # which a Python-side default never reaches.
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str,
                server_default=text("gen_random_uuid()"))
    name = Column(String(120), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False,
                       server_default=text("true"))
    # e.g. {"po_document_sequence": 1.0, "need_by_date": 0.0, "demand_class": 0.0}
    # Seeded to reproduce today's manual answer so week-one output is checkable by hand.
    factors = Column(JSONB, nullable=False, default=dict)
    # e.g. {"project": 1.0, "retail": 0.4}. Keyed by market_segments.code, so a new class
    # is a row plus a weight.
    demand_class_weights = Column(JSONB, nullable=False, default=dict)
    notes = Column(Text, nullable=True)
    # Ladder v2 (E) settings, added by migration ed706a98ddc6. Read-only from this slice's
    # side (`priority.py` exposes them; the ladder itself is a later workstream) - kept on
    # THIS row rather than a sibling table for the same reason `factors` is: one policy,
    # activated as a whole, so a planner tuning "how far out is Buy all" cannot leave the
    # weights and the horizon pointing at two different revisions.
    #
    # A CALENDAR DATE, not a rolling day count (19 Aug follow-up, migration
    # 394_reorder_coverage_until, replacing `buy_all_horizon_days`): the captain's own
    # framing was "purchasing reorders until October" - a fixed date, not "N days from
    # today". A line required AFTER this date is proposed as `Buy now`, untouched - no
    # reservation, no borrow attempted. NULL means no coverage limit is set.
    reorder_coverage_until = Column(Date, nullable=True)
    # The other end of the same idea (borrow ladder v7.1, R20, migration 443). Demand dated
    # ON or AFTER this date is TBA: it takes no supply, is never covered, and never donates.
    # This client books "no date agreed yet" as 2030-01-01, so the default sits just before
    # it; the next client's convention is a different date, which is exactly why it is a
    # policy field and not a constant in the engine. NOT NULL - "no TBA date" would mean a
    # placeholder line competing with real promises for real stock.
    #
    # `cross_group_borrow_max_qty` / `cross_group_borrow_max_pct` used to sit here and were
    # dropped by the same migration (R5): any ownership group may donate now, so there is
    # nothing left for a cap to cap.
    tba_date_from = Column(
        Date, nullable=False, default=date(2029, 1, 1),
        server_default=text("'2029-01-01'::date"),
    )
    # The flat 2-day transfer charge (`front_planning_engine.TRANSFER_DAYS`) retired 31 Aug
    # (R-B): an option whose stock is not already at the asking line's own bin used to be
    # charged a hard-coded 2 days, and the captain asked for it to be configurable, default
    # 0. Migration 451. NOT NULL - an unconfigured install charges nothing rather than
    # falling back to a guessed number.
    transfer_days = Column(Integer, nullable=False, default=0, server_default=text("0"))
    # The site pool's share step (fulfilment feedback batch, S1, 2 Sep ruling R-B,
    # migration 460). A line due within `immediate_window_days` may take up to
    # `pool_share_pct`'s complement of the pool's free pile now, bounded by the five-pool
    # net; beyond the window a line takes the whole allowance or nothing. Two numbers on
    # this row rather than a sibling table - one policy, activated as a whole, the same
    # reason `tba_date_from` and `transfer_days` live here.
    immediate_window_days = Column(
        Integer, nullable=False, default=30, server_default=text("30")
    )
    pool_share_pct = Column(
        Integer, nullable=False, default=50, server_default=text("50")
    )
    # The overdue grace (R-O, 3 Sep 2026, migration 464). R31 counted a document whose
    # arrival has passed as nothing at all on its outstanding balance; on SO419417 that left
    # the ladder lending 4 units off the 11 on the floor at BRW while 725 SPO units dated
    # July and August sat unreceived. A late-but-alive document now counts as supply landing on
    # `today + overdue_grace_days`, and one later than `overdue_dead_days` counts as
    # nothing, which is R31 kept for the dead. Two numbers on this row for the same reason
    # `immediate_window_days` is here: one policy, activated as a whole.
    #
    # SHIPPED at 0 / 0 (captain's ruling, 3 Sep 2026): with dead at 0 any lateness at all is
    # past it, so a document one day late counts as nothing exactly as R31 always had it -
    # production keeps today's behaviour until someone raises these. 14 / 90 is the
    # RECOMMENDED pair once the captain is ready to turn the grace on.
    overdue_grace_days = Column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    overdue_dead_days = Column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class OrderSummaryRow(Base, CompanyScopedMixin):
    """One product's FROZEN Summary Order Report row for a run, plus its decision.

    Frozen because AC-C2.9 requires a past week to be reviewable: what the decider saw has to
    be recoverable, and the order book moves daily, so a recomputation is a different report
    wearing the same date.

    The grain is (run, product), NOT (run, product, warehouse). AC-C2.1 makes the report one
    row per product network wide because a purchase order is raised once for the company,
    while M8-D5 keeps recommendations per warehouse so each buy is tied to a real location.
    Both stand, so the product-level decision has no per-warehouse recommendation to hang off
    and lives here; splitting one chosen quantity across locations is the allocator's job.

    Nullability is load-bearing: `avg_daily_demand` (absent for ~38% of the book) and
    `unit_volume_cbm` (~84%) are NULL rather than 0, because a zero reads as "already out of
    stock" and "no space needed" - decisions taken on a figure nobody measured.
    """
    __tablename__ = "order_summary_row"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    run_id = Column(
        UUID(as_uuid=False),
        ForeignKey("scm.reorder_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id = Column(
        UUID(as_uuid=False), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )

    as_of = Column(Date, nullable=False)
    on_hand = Column(Numeric, nullable=False, default=0)
    project_demand = Column(Numeric, nullable=False, default=0)
    dealer_outstanding = Column(Numeric, nullable=False, default=0)
    # Separate on purpose (AC-C2.2): their sum drives the balance, the split is what a person
    # reads, because only the on-order half is still negotiable.
    qty_on_order = Column(Numeric, nullable=False, default=0)
    qty_in_transit = Column(Numeric, nullable=False, default=0)
    # The DATED shortfall (peak deficit), never `on hand + on order - demand`.
    shortfall = Column(Numeric, nullable=False, default=0)
    shortfall_at = Column(Date, nullable=True)
    suggested_qty = Column(Numeric, nullable=False, default=0)

    avg_daily_demand = Column(Numeric, nullable=True)
    unit_volume_cbm = Column(Numeric, nullable=True)
    spare_lands_at_warehouse_id = Column(
        UUID(as_uuid=False), ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True
    )

    project_demand_line_count = Column(Integer, nullable=False, default=0)
    dealer_outstanding_line_count = Column(Integer, nullable=False, default=0)
    # How many open SO lines carry no persisted demand class, so the exception can be
    # opened rather than only counted. Sits beside its two siblings rather than inside
    # `channel_calculation_basis`: it is a diagnostic of the open order book, computed on
    # every run including a legacy one, not part of the channel arithmetic that a legacy
    # run has none of.
    unclassified_line_count = Column(Integer, nullable=False, default=0,
                                     server_default=text("0"))
    # NULL when nothing is outstanding, which is not the same as 0 days outstanding.
    max_days_outstanding = Column(Integer, nullable=True)

    # --- front planning: the channel breakdown of ONE product row (plan 5.3 / 6.4) ---
    # Channel is analysis INSIDE the row, never row identity: the key stays
    # (run_id, product_id) and stock / SPO / PO / reorder level remain single shared
    # facts. All six are nullable because a run created before the contract has no
    # breakdown at all, and a legacy NULL is a durable marker rather than a gap waiting
    # to be backfilled (AC-F10).
    #: Confirmed unplaced Buy on Project-class lines, summed across locations (AC-E04).
    #: FIRM: Retail free-supply netting never reduces it.
    project_buy_qty = Column(Numeric, nullable=True)
    #: Normally netted Retail replenishment, summed across locations.
    retail_replenishment_qty = Column(Numeric, nullable=True)
    #: Demand whose SO carries no persisted class. Visible, and excluded from the
    #: actionable suggestion until somebody classifies it (AC-E06).
    unclassified_demand_qty = Column(Numeric, nullable=True)
    #: Required only when `project_buy_qty > 0`; NULL says there is no firm Buy to date.
    earliest_project_need_date = Column(Date, nullable=True)
    #: The frozen arithmetic behind `suggested_qty`, plus the per-location facts it was
    #: summed from, so the Locations drill reconciles without re-deriving anything.
    channel_calculation_basis = Column(JSONB, nullable=True)
    #: The product's base-UOM divisibility AS IT WAS when the run was calculated.
    #: Chosen-quantity validation and the allocator rerun read THIS, never live UOM
    #: master data, so a later UOM edit cannot change a frozen run (AC-F12).
    uom_decimal_places = Column(SmallInteger, nullable=True)

    chosen_qty = Column(Numeric, nullable=True)
    chosen_supplier_id = Column(
        UUID(as_uuid=False), ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True
    )
    decided_by = Column(String, nullable=True)
    decided_at = Column(DateTime(timezone=False), nullable=True)

    # Whether the purchase order has been keyed into AutoCount (S4, AC-E2.2). MANUAL:
    # nothing can detect it, so the person keying is the only source of truth. `keying` is
    # load-bearing rather than decorative - it is what stops two people keying the same PO.
    # `keyed_by` is a human NAME, not a user id, because it is rendered beside the row.
    keyed_status = Column(
        String(20), nullable=False, default="not_keyed", server_default=text("'not_keyed'")
    )
    keyed_by = Column(String, nullable=True)
    keyed_at = Column(DateTime(timezone=False), nullable=True)

    computed_at = Column(DateTime(timezone=False), nullable=False)
    source_system = Column(String, nullable=True)
    source_ref = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        # One row per product per run, or the report reads whichever duplicate comes back
        # first (the `system_settings` singleton lesson).
        Index(
            "uq_scm_order_summary_row_run_product", "run_id", "product_id", unique=True
        ),
        Index("ix_scm_order_summary_row_run_id", "run_id"),
        # Filtering to not-keyed is the primary use of the worklist (AC-E2.4), always
        # within one run.
        Index("ix_scm_order_summary_row_run_keyed", "run_id", "keyed_status"),
        CheckConstraint(
            "keyed_status IN ('not_keyed', 'keying', 'keyed')",
            name="ck_scm_order_summary_row_keyed_status",
        ),
        {"schema": "scm"},
    )


class OrderSummaryLocationAllocation(Base, CompanyScopedMixin):
    """One location's share of a Product-grain chosen quantity (plan 5.4 / 6.4).

    A product-grain decision is ONE quantity for the company, and a purchase order still
    has to say where the stock lands. So the accepted quantity is replayed through the
    existing `reorder_engine.allocate` against the run's frozen location inputs, in the
    row's frozen UOM minor units, and the resulting decimal quantities are persisted here.

    Narrow on purpose: this is persistence for the PO worklist, not a second allocator.
    These STORED quantities sum exactly to the parent's `chosen_qty` because the allocator
    apportions integer minor units of the frozen precision - no rescaling formula is
    applied, and a re-decision REPLACES the split rather than scaling the old one. The
    exactness is a property of the persisted decimals: the allocator hands its shares back
    as floats, and at a non-zero precision a float sum of them can differ from `chosen_qty`
    in the last bit, so reconcile against these columns rather than against that sum.

    `reorder_recommendation_id` is nullable: a product-grain split has no single owning
    recommendation row, and naming one would imply a location decision that was never made.
    """

    __tablename__ = "order_summary_location_allocation"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str,
                server_default=text("gen_random_uuid()"))
    order_summary_row_id = Column(
        UUID(as_uuid=False),
        ForeignKey("scm.order_summary_row.id", ondelete="CASCADE"),
        nullable=False,
    )
    reorder_recommendation_id = Column(
        UUID(as_uuid=False),
        ForeignKey("scm.reorder_recommendation.id", ondelete="SET NULL"),
        nullable=True,
    )
    warehouse_id = Column(
        UUID(as_uuid=False), ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False
    )
    allocated_qty = Column(Numeric, nullable=False, default=0)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index(
            "uq_scm_order_summary_location_alloc",
            "order_summary_row_id",
            "warehouse_id",
            unique=True,
        ),
        CheckConstraint(
            "allocated_qty >= 0",
            name="ck_scm_order_summary_location_alloc_qty",
        ),
        {"schema": "scm"},
    )


class PlanExceptionBatch(Base, CompanyScopedMixin):
    """One confirmed restatement, and the exceptions it produced.

    The batch exists as its own row because it carries a fact none of its exceptions can:
    `delta_count`, the number of order lines that upload CHANGED. AC-D2b requires the screen
    to reconcile that figure with the number of exceptions, and the reduction between them
    (412 changed, 6 disagree with a placed order) is the value of the feature. Recounting the
    deltas from the exceptions would make the two agree by construction, so the count is
    carried through unchanged from the upload that computed it.

    `run_id` is nullable on purpose. A batch is produced by an UPLOAD, and an upload confirmed
    before any plan has ever run has no run to name - the exceptions are still real, because a
    purchase order can be placed without a plan.
    """
    __tablename__ = "plan_exception_batch"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    run_id = Column(
        UUID(as_uuid=False),
        ForeignKey("scm.reorder_run.id", ondelete="SET NULL"),
        nullable=True,
    )
    as_of = Column(Date, nullable=False)
    generated_at = Column(DateTime(timezone=False), nullable=False)
    last_upload_at = Column(DateTime(timezone=False), nullable=True)
    delta_count = Column(Integer, nullable=False, default=0)
    source_documents = Column(JSONB, nullable=True)
    created_by = Column(UUID(as_uuid=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_scm_plan_exception_batch_generated", "generated_at"),
        {"schema": "scm"},
    )


class PlanException(Base, CompanyScopedMixin):
    """One disagreement between the restated plan and supply already placed.

    Three JSONB columns are FROZEN at generation rather than recomputed on read. The order
    book moves daily, so a timeline recomputed when somebody opens the row is a different
    position wearing the same date, and a reclassified item would silently re-order the
    proposed actions of a decision already taken. What the reviewer approves has to be what
    the engine saw:

      * `timeline_json` - before and after, side by side (AC-D4).
      * `reading_json` - lifecycle, velocity, business class, last purchase date, each with
        the field it was read from (AC-D9, AC-D12).
      * `actions_json` - the proposed actions and their rank, which IS the reading's verdict
        (AC-D10) and so is stored rather than re-derived.

    `quantity` is always positive; the TYPE carries the direction. A signed quantity would let
    a surplus and a shortfall be told apart two different ways, which is one too many.
    """
    __tablename__ = "plan_exception"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    batch_id = Column(
        UUID(as_uuid=False),
        ForeignKey("scm.plan_exception_batch.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id = Column(
        UUID(as_uuid=False), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    warehouse_id = Column(
        UUID(as_uuid=False), ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True
    )
    pool_code = Column(String(50), nullable=True)

    exception_type = Column(String(40), nullable=False)
    quantity = Column(Numeric, nullable=False)

    purchase_order_id = Column(
        UUID(as_uuid=False),
        ForeignKey("purchase_orders.id", ondelete="SET NULL"),
        nullable=True,
    )
    po_expected_date = Column(Date, nullable=True)

    timeline_json = Column(JSONB, nullable=True)
    reading_json = Column(JSONB, nullable=True)
    actions_json = Column(JSONB, nullable=True)

    status = Column(String(20), nullable=False, default="open")
    decided_by = Column(UUID(as_uuid=False), nullable=True)
    decided_at = Column(DateTime(timezone=False), nullable=True)
    decided_action = Column(String(40), nullable=True)
    decision_reason = Column(Text, nullable=True)
    split_qty = Column(Numeric, nullable=True)

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_scm_plan_exception_batch", "batch_id"),
        # The queue query: this batch's open rows. Status leads because "what is left to
        # decide" is the question the screen opens on.
        Index("ix_scm_plan_exception_batch_status", "batch_id", "status"),
        # The FK check when a purchase order is deleted (migration 420 deletes 3,983 at once).
        Index("ix_scm_plan_exception_purchase_order", "purchase_order_id"),
        CheckConstraint(
            "exception_type IN ('shortfall_earlier', 'supply_early', 'supply_surplus', "
            "'supply_wrong_location')",
            name="ck_scm_plan_exception_type",
        ),
        CheckConstraint(
            "status IN ('open', 'approved', 'rejected')",
            name="ck_scm_plan_exception_status",
        ),
        {"schema": "scm"},
    )


class OrderLinkClaim(Base, CompanyScopedMixin):
    """A claimed SO<->PO pairing, resolved when both documents exist.

    A purchase order can be uploaded before its sales order and a sales order before its
    purchase order, and neither order may lose the pairing. A nullable FK on the PO line
    cannot express that: a claim made before the other side exists has nowhere to live, so it
    is dropped and the linkage silently depends on which file somebody opened first.

    So the numbers are held as TEXT, exactly as the source spelled them, and `so_line_id` /
    `po_line_id` are filled in later by the resolver. An unresolved claim is a number the
    upload result reports - "34 orders name a purchase order we have not seen" is how
    somebody finds out the PO book is a month behind.

    The PURCHASE side is one of two columns, never both: `po_line_id` for a `######-S####`
    purchase order, `spo_allocation_id` for an `SPO-####/##-####` shipping order, which since
    migration 420 is a row in `spo_allocations`. Which one a claim uses is decided by the
    number it already holds, so nothing has to be re-parsed at read time.

    `item_code` is nullable because the two feeds know different things. The Order Inquiry
    sheet states the item, so its claims are per line. The `**SO:174830**` notes inside the PO
    export do not - a note sits between lines and nothing says which side it describes - so
    those claims are order-level. Guessing a line there would assign one customer's stock to
    another customer's order.
    """
    __tablename__ = "order_link_claim"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    so_number = Column(String(100), nullable=False)
    po_number = Column(String(100), nullable=False)
    item_code = Column(String(100), nullable=True)
    source = Column(String(30), nullable=False)

    claimed_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    resolved_at = Column(DateTime(timezone=False), nullable=True)
    so_line_id = Column(
        UUID(as_uuid=False), ForeignKey("sales_order_lines.id", ondelete="SET NULL"),
        nullable=True,
    )
    po_line_id = Column(
        UUID(as_uuid=False), ForeignKey("purchase_order_lines.id", ondelete="SET NULL"),
        nullable=True,
    )
    #: The purchase side when the document is a SHIPPING order. An `SPO-` number names a row
    #: in `spo_allocations`, not in `purchase_order_lines` (migration 420), and a claim with
    #: nowhere to record that half could never resolve: 12,393 of them, naming 2,989 sales
    #: orders, would have read "awaiting purchase order" for ever. Exactly one of the two
    #: columns is filled, decided by the number the claim itself carries.
    spo_allocation_id = Column(
        UUID(as_uuid=False),
        ForeignKey(
            "spo_allocations.id",
            ondelete="SET NULL",
            name="fk_scm_order_link_claim_spo_allocation",
        ),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_scm_order_link_claim_so", "so_number"),
        Index("ix_scm_order_link_claim_po", "po_number"),
        Index("ix_scm_order_link_claim_spo_allocation", "spo_allocation_id"),
        # The FK check when a purchase order line is deleted: without it every deleted line
        # costs a sequential scan of this table (migration 420 deleted 80k lines).
        Index("ix_scm_order_link_claim_po_line", "po_line_id"),
        # WHO attributed this pairing, and it is the only way to tell an attribution
        # apart from an echo of one. `po_history` / `po_upload` are the book's own
        # `FromSODocList` column on the two purchase channels; `manual` is a person in
        # the Link dialog; `crm_supply` is the supply WRITER claiming a line it has just
        # created for known demand (`app/services/scm/supply_claim.py`, G12's write-time
        # rule); `order_inquiry` is the audit row `_write_link` writes in lockstep with
        # a link, which therefore names a quantity that link already accounts for;
        # `autocount` is the ESB naming a pairing via `from_so_numbers` on a pushed
        # document (V4, migration 473).
        CheckConstraint(
            "source IN ('po_history', 'order_inquiry', 'so_upload', 'po_upload', "
            "'manual', 'crm_supply', 'autocount')",
            name="ck_scm_order_link_claim_source",
        ),
        {"schema": "scm"},
    )


#: Coalesce target for company-scoped unique indexes. `company_id` is nullable on legacy
#: rows and Postgres treats NULLs as distinct, so an unstamped row would slip past the lock.
_NIL_COMPANY = "00000000-0000-0000-0000-000000000000"


class ContainerSize(Base):
    """How many cubic metres a container holds, per tenant (AC-E3).

    A table rather than a constant because the loadable volume of a 40HQ is a commercial
    fact that differs by packing practice, and a client who ships in something else should
    edit a row, not wait for a release.
    """
    __tablename__ = "container_size"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    company_id = Column(UUID(as_uuid=False), nullable=True)
    code = Column(String(30), nullable=False)
    label = Column(String(100), nullable=True)
    cbm = Column(Numeric, nullable=False)
    is_default = Column(Boolean, nullable=False, server_default=text("false"))
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("cbm > 0", name="ck_scm_container_size_cbm"),
        Index(
            "uq_scm_container_size_code",
            text("coalesce(company_id, '%s'::uuid)" % _NIL_COMPANY),
            text("upper(code)"),
            unique=True,
        ),
        {"schema": "scm"},
    )


class SupplierProductCodeAlias(Base, CompanyScopedMixin):
    """One supplier's spelling of one of our product codes (R16, migration 431).

    Suppliers do not write our codes. They reorder the tokens, spell out a trap size ours
    omits because it is the default, glue a suffix on. `supplier_code_matcher` works that
    out with a ladder, and this table is where the answer is KEPT - so the ladder is never
    re-run against a code somebody has already ruled on, and a wrong guess is corrected once
    instead of being re-derived on every upload.

    `source` is who decided and `matched_by` is which rung did it. Both are on the row
    because an automatic bind has to be visible AS one: a screen that cannot tell a guess
    from a decision cannot ask anyone to check the guess.

    The code is stored VERBATIM - it is what the supplier's file says. Normalising happens
    where codes are compared, never on the way in.
    """
    __tablename__ = "supplier_product_code_alias"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    supplier_id = Column(
        UUID(as_uuid=False), ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False
    )
    supplier_code = Column(String(120), nullable=False)
    #: Nullable because "none of ours" is an answer too (R17, migration 432): a dismissal is
    #: a row with no product, and it is the only shape that can say the code names something
    #: our catalogue is never going to hold.
    product_id = Column(
        UUID(as_uuid=False), ForeignKey("products.id", ondelete="CASCADE"), nullable=True
    )
    #: The other thing a supplier code can name (R19, R20, migration 433): a product SET.
    #: `CWC605-RL` is the whole WC - pedestal plus cistern - and no product carries that
    #: code, so a code spelled as one of our set codes could never bind before this column.
    #: Exactly one of `product_id` / `product_set_id` is set, unless the row is a dismissal
    #: and neither is.
    product_set_id = Column(
        UUID(as_uuid=False), ForeignKey("product_sets.id", ondelete="CASCADE"), nullable=True
    )
    source = Column(String(10), nullable=False, server_default=text("'auto'"))
    matched_by = Column(Text, nullable=True)
    created_by = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "source IN ('auto', 'manual', 'dismissed')",
            name="ck_scm_supplier_code_alias_source",
        ),
        # `source` and what the row names are one fact, so the database says so: dismissed
        # means exactly "nothing of ours", and a row claiming both is unreadable by every
        # screen that renders it.
        CheckConstraint(
            "(source = 'dismissed') = (product_id IS NULL AND product_set_id IS NULL)",
            name="ck_scm_supplier_code_alias_dismissed",
        ),
        # One code means ONE thing. A row naming a product and a set at once cannot be
        # re-bound - the stock row and the invoice line each carry one of the two - so the
        # database refuses it rather than leaving every reader to choose.
        CheckConstraint(
            "NOT (product_id IS NOT NULL AND product_set_id IS NOT NULL)",
            name="ck_scm_supplier_code_alias_one_target",
        ),
        Index("ix_scm_supplier_code_alias_supplier", "supplier_id"),
        Index("ix_scm_supplier_code_alias_product", "product_id"),
        Index("ix_scm_supplier_code_alias_set", "product_set_id"),
        # Declared on the MODEL as well as in migration 431: a CI database is built with
        # `create_all` and never runs a migration body, so without it the guard against one
        # supplier code meaning two products exists in production and nowhere else.
        Index(
            "uq_scm_supplier_code_alias_identity",
            text("coalesce(company_id, '%s'::uuid)" % _NIL_COMPANY),
            "supplier_id",
            text("upper(supplier_code)"),
            unique=True,
        ),
        {"schema": "scm"},
    )


class SupplierInventory(Base, CompanyScopedMixin):
    """What one supplier is holding for us right now: packed, unfinished, and how big it is.

    A SNAPSHOT, not a ledger. The supplier sends their stock list; the next list they send
    replaces it wholesale for that supplier, because an item the new file no longer mentions
    is stock they no longer hold, and keeping the old row would offer Ms Tee a container of
    something that is not there. History of what a supplier once held is not a question
    anybody asks; "can I load it this week" is.

    Two quantities because they answer different questions (AC-E1, AC-E2). `qty_packed` is
    loadable today. `qty_unfinished` is 空瓷 - the body exists, the finishing does not - and
    it is loadable only after the supplier produces it, so it is listed as something to ask
    for, never fed to the allocator.

    `cbm_per_unit` is nullable, and nullable is load-bearing: a missing volume must reach the
    allocator as `unmeasured` rather than as zero, or an item nobody measured looks like an
    item that takes no space and gets loaded ahead of everything real.

    `product_id` is nullable because the supplier writes their own model numbers. An
    unmatched row is still shown (it is stock we might want) but it cannot join a loading
    plan, whose lines hang off our purchase orders.
    """
    __tablename__ = "supplier_inventory"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    supplier_id = Column(
        UUID(as_uuid=False), ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False
    )
    item_code = Column(String(100), nullable=False)
    product_id = Column(
        UUID(as_uuid=False), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    #: The row's other possible binding (R19, migration 433): the supplier's code names a
    #: product SET, not a product. `CWC605-RL` is a whole WC and no product carries that
    #: code, so before this column the row could only sit unmatched. Never both - the
    #: matcher answers one code with one thing.
    product_set_id = Column(
        UUID(as_uuid=False), ForeignKey("product_sets.id", ondelete="SET NULL"), nullable=True
    )

    qty_packed = Column(Numeric, nullable=False, server_default=text("0"))
    qty_unfinished = Column(Numeric, nullable=False, server_default=text("0"))
    cbm_per_unit = Column(Numeric, nullable=True)

    product_name = Column(String, nullable=True)
    brand = Column(String, nullable=True)
    spec = Column(String, nullable=True)
    remark = Column(Text, nullable=True)

    as_of = Column(Date, nullable=False)
    uploaded_by = Column(String, nullable=True)
    source_system = Column(String, nullable=True)
    source_ref = Column(String, nullable=True)
    #: WHICH loading plan this snapshot belongs to (S6, migration 454). A plan reads its own
    #: rows and nobody else's: before this the snapshot was one per supplier, so a plan
    #: started with no file at all still showed the last file anybody had uploaded for that
    #: supplier - and said "No file" while doing it. NULL is the standalone stock-list page's
    #: upload, and every row that predates 454.
    loading_plan_id = Column(
        UUID(as_uuid=False), ForeignKey("scm.loading_plan.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_scm_supplier_inventory_supplier", "supplier_id"),
        Index("ix_scm_supplier_inventory_product", "product_id"),
        Index("ix_scm_supplier_inventory_set", "product_set_id"),
        Index("ix_scm_supplier_inventory_loading_plan", "loading_plan_id"),
        # Declared on the MODEL as well as in migrations 336 and 454, because a CI database is
        # built with `create_all` and never runs a migration body: without it the guard
        # against a doubled packed quantity exists in production and nowhere else.
        #
        # The plan is IN the key (454), coalesced for the same reason the company is: Postgres
        # treats every NULL as distinct, and the identity has to hold across the plan-less
        # rows too. Without it the second plan to upload one model number for a supplier
        # collides with the first and the upload fails.
        Index(
            "uq_scm_supplier_inventory_identity",
            text("coalesce(company_id, '%s'::uuid)" % _NIL_COMPANY),
            "supplier_id",
            text("coalesce(loading_plan_id, '%s'::uuid)" % _NIL_COMPANY),
            "item_code",
            unique=True,
        ),
        {"schema": "scm"},
    )


class LoadingPlan(Base, CompanyScopedMixin):
    """One container plan at one supplier: what to ask them for, and what became of the ask.

    THE plan row since part 4 (R1). It was a stage-2 CBM fit before that, and the columns
    below still carry both halves: `status` / `plan_horizon_date` / `document_kind` /
    `line_edits` are the plan a buyer works on, and `container_*` / `planned_cbm` /
    `deferred_count` are the CBM fit that was cut on the captain's 20 Aug ruling. A second
    "container plan" table would have been the same row under a second name, and
    `supplier_notices.loading_plan_id` already points here.

    Kept as a row rather than computed on demand because two people have to be able to open
    the same plan, and because what was sent to a supplier has to stay readable after the
    order book moves underneath it.
    """
    __tablename__ = "loading_plan"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    supplier_id = Column(
        UUID(as_uuid=False), ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False
    )
    container_type = Column(String(30), nullable=True)
    container_count = Column(Integer, nullable=False, server_default=text("1"))
    #: Nullable since 441: the CBM fit is the stage-2 half, and a plan started from a stock
    #: list has no container chosen yet (the supplier decides that when they pack).
    container_cbm = Column(Numeric, nullable=True)
    capacity_cbm = Column(Numeric, nullable=True)

    #: `planning` -> `sent` (a notice went out) or `cancelled`. Never `opened`: an open is an
    #: event that repeats, and a status that flipped back and forth would lie.
    status = Column(String(20), nullable=False, server_default=text("'planning'"))
    #: "Sales order cut-off". NULL means every open order counts, the same words and the same
    #: rule the reorder run uses.
    plan_horizon_date = Column(Date, nullable=True)
    #: `stock_list` | `proforma` | `none` - which document the plan was started from.
    document_kind = Column(String(20), nullable=False, server_default=text("'none'"))
    #: The retained sheet itself, so the record can offer "View uploaded list". Not an FK:
    #: attachments are pruned on their own schedule and a pruned file must not delete a plan.
    source_attachment_id = Column(UUID(as_uuid=False), nullable=True)
    #: The typed quantities, `row_key -> qty`. Replaced whole on save (R6), never patched: a
    #: cleared cell must not survive as a stale override.
    line_edits = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    #: What the LAST build of this plan asked for. A cache of a derived figure, so the list
    #: can print a "To request" column without running one full suggestion per listed row.
    to_request_qty = Column(Numeric, nullable=True)
    to_request_cbm = Column(Numeric, nullable=True)

    sent_at = Column(DateTime(timezone=False), nullable=True)
    cancelled_at = Column(DateTime(timezone=False), nullable=True)
    cancelled_by = Column(String, nullable=True)

    policy_id = Column(
        UUID(as_uuid=False), ForeignKey("scm.priority_policy.id", ondelete="SET NULL"),
        nullable=True,
    )
    inventory_as_of = Column(Date, nullable=True)

    planned_cbm = Column(Numeric, nullable=False, server_default=text("0"))
    line_count = Column(Integer, nullable=False, server_default=text("0"))
    deferred_count = Column(Integer, nullable=False, server_default=text("0"))
    unmeasured_count = Column(Integer, nullable=False, server_default=text("0"))

    created_by = Column(String, nullable=True)
    computed_at = Column(DateTime(timezone=False), nullable=False, server_default=func.now())
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    lines = relationship(
        "LoadingPlanLine", back_populates="plan", cascade="all, delete-orphan",
        order_by="LoadingPlanLine.rank",
    )

    __table_args__ = (
        CheckConstraint("container_count > 0", name="ck_scm_loading_plan_containers"),
        CheckConstraint("container_cbm > 0", name="ck_scm_loading_plan_container_cbm"),
        Index("ix_scm_loading_plan_supplier", "supplier_id"),
        {"schema": "scm"},
    )


class LoadingPlanLine(Base, CompanyScopedMixin):
    """One outstanding purchase-order line's outcome on a loading plan.

    Every candidate line is written, INCLUDING the ones that did not make it, because
    "why is this not on the container" is the question Ms Tee actually asks (AC-E5) and a
    plan that only lists winners cannot answer it.

    `factors_json` holds the ranking factors and their contributions for this line (AC-E7):
    a rank a planner cannot decompose is a number they have to take on faith, and the first
    time it disagrees with them they stop using the screen.
    """
    __tablename__ = "loading_plan_line"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    plan_id = Column(
        UUID(as_uuid=False), ForeignKey("scm.loading_plan.id", ondelete="CASCADE"),
        nullable=False,
    )
    po_line_id = Column(
        UUID(as_uuid=False), ForeignKey("purchase_order_lines.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id = Column(
        UUID(as_uuid=False), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )

    po_number = Column(String(100), nullable=True)
    item_code = Column(String(100), nullable=True)
    qty_outstanding = Column(Numeric, nullable=False, server_default=text("0"))
    qty_packed_available = Column(Numeric, nullable=True)
    qty_planned = Column(Numeric, nullable=False, server_default=text("0"))
    cbm_per_unit = Column(Numeric, nullable=True)
    cbm_planned = Column(Numeric, nullable=True)
    volume_basis = Column(String(20), nullable=True)

    rank = Column(Integer, nullable=True)
    rank_score = Column(Numeric, nullable=True)
    factors_json = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))

    status = Column(String(20), nullable=False, server_default=text("'deferred'"))
    deferral_reason = Column(String(40), nullable=True)

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    plan = relationship("LoadingPlan", back_populates="lines")

    __table_args__ = (
        Index("ix_scm_loading_plan_line_plan", "plan_id"),
        Index("uq_scm_loading_plan_line_identity", "plan_id", "po_line_id", unique=True),
        # The FK check when a purchase order line is deleted (see OrderLinkClaim).
        Index("ix_scm_loading_plan_line_po_line", "po_line_id"),
        CheckConstraint(
            "status IN ('allocated', 'partial', 'deferred', 'unmeasured')",
            name="ck_scm_loading_plan_line_status",
        ),
        {"schema": "scm"},
    )


class CurrencyRate(Base):
    """What one unit of a currency is worth in the base currency (`money.BASE_CURRENCY`).

    The purchase-order book prices in four currencies, and most SKUs with more than one
    priced supplier have those suppliers in different ones, so nothing can be ranked or
    summed until they are expressed in the same money.

    One row per currency, holding the rate in force NOW. History is deliberately absent: a
    planning run freezes the rate it used onto its own recommendations, so an old plan
    explains itself without this table remembering. The base currency has no row - it is 1
    by definition, and a stored 1 is a number somebody can edit to something else.
    """
    __tablename__ = "currency_rate"

    currency = Column(String(3), primary_key=True)
    rate_to_base = Column(Numeric(18, 6), nullable=False)
    #: When this rate was true. Shown next to every converted figure, because a buyer
    #: reading a six-month-old rate should be able to see that is what they are reading.
    as_of = Column(Date, nullable=True)
    note = Column(String(255), nullable=True)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(),
                        onupdate=func.now(), nullable=False)
    updated_by = Column(UUID(as_uuid=False), nullable=True)

    __table_args__ = (
        # A non-positive rate would zero out a real cost or invert it. The service refuses
        # one too; this holds when something writes around the service.
        CheckConstraint("rate_to_base > 0", name="ck_currency_rate_positive"),
        {"schema": "scm"},
    )


class ProformaInvoice(Base, CompanyScopedMixin):
    """The supplier's own priced document, as they sent it (G3b).

    A document of record rather than a derived view: it is what the next task verifies a
    purchase order against, so it has to survive the file it came from being deleted and the
    order book moving underneath it.

    Identity is `(company, supplier, pi_number)`, which is why `pi_number` is NOT NULL even
    on the documents that state none - the pre-loading list's five blocks carry no invoice
    number at all, and a positional one (`PI-<file stem>-<block>`) is derived so a re-upload
    lands on the same five invoices instead of a second set (AC-P1.4, AC-P2.5).

    `currency` is nullable and never defaulted. It is NULL only on a document with no priced
    line at all: a price with no currency is a number with no meaning, so a PRICED document
    whose currency resolves to nothing is refused before it is written rather than stored in
    a house default nobody would ever question (AC-P3.2).

    `container_ref` / `bl_ref` are nullable and never invented: at proforma time the
    container usually has not been assigned, and the pre-loading list leaves both cells blank.
    """
    __tablename__ = "proforma_invoice"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    supplier_id = Column(
        UUID(as_uuid=False), ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False
    )
    pi_number = Column(String(100), nullable=False)
    invoice_date = Column(Date, nullable=True)
    # NULL only for a document with no priced line at all: a priced one is refused before
    # it is written unless the currency resolved (AC-P3.2). Never a house default.
    currency = Column(String(3), nullable=True)

    container_ref = Column(String(100), nullable=True)
    bl_ref = Column(String(100), nullable=True)

    #: What the document totals ITSELF to when it states a total, else the sum of its lines.
    #: Stored rather than summed on read so the verification screen compares like with like.
    total_amount = Column(Numeric, nullable=True)
    line_count = Column(Integer, nullable=False, server_default=text("0"))

    source_ref = Column(String, nullable=True)
    block_index = Column(Integer, nullable=True)
    uploaded_by = Column(String, nullable=True)

    #: Who trimmed this document to fit, and when. NULL on an invoice nobody has touched,
    #: which is what tells the screen to show the supplier's figures unqualified.
    adjusted_by = Column(String(200), nullable=True)
    adjusted_at = Column(DateTime(timezone=False), nullable=True)

    #: The revision chain (AC-E7). A supplier resending the same container with new prices
    #: is a REVISION of one document, not a second document sitting beside it: the two would
    #: otherwise both answer "what is this container costing", and only one of them is true.
    #: `revision_of_id` points at the immediately-previous revision, so the chain reads
    #: backwards from the current one; `revision_no` is its position, 1 for an original.
    revision_of_id = Column(
        UUID(as_uuid=False), ForeignKey("scm.proforma_invoice.id", ondelete="SET NULL"),
        nullable=True,
    )
    revision_no = Column(Integer, nullable=False, server_default=text("1"))
    #: The loading plan this invoice was uploaded INTO (S6, migration 454). One sheet holds
    #: five stacked invoice blocks, and the plan binds to every one of them, so its "They
    #: hold" figure is the sum across its own blocks rather than whichever single invoice
    #: sorted first for the supplier. NULL on the standalone proforma page's uploads and on
    #: every row that predates 454.
    loading_plan_id = Column(
        UUID(as_uuid=False), ForeignKey("scm.loading_plan.id", ondelete="SET NULL"),
        nullable=True,
    )
    #: `current` or `superseded`. A superseded revision is KEPT and read-only: it is what the
    #: supplier actually sent on the day, and the diff against it is the reason anybody looks
    #: at the new one. It is never a cost and never converts (AC-E9, AC-E10).
    status = Column(String(20), nullable=False, server_default=text("'current'"))

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    lines = relationship(
        "ProformaInvoiceLine", back_populates="invoice", cascade="all, delete-orphan",
        order_by="ProformaInvoiceLine.line_no",
    )

    __table_args__ = (
        Index("ix_scm_proforma_invoice_supplier", "supplier_id"),
        Index("ix_scm_proforma_invoice_revision_of", "revision_of_id"),
        Index("ix_scm_proforma_invoice_loading_plan", "loading_plan_id"),
        CheckConstraint(
            "status IN ('current', 'superseded')", name="ck_scm_proforma_invoice_status"
        ),
        # Declared on the MODEL as well as in migration 375, because a CI database is built
        # with `create_all` and never runs a migration body: without it the guard against a
        # doubled invoice exists in production and nowhere else (the supplier_inventory
        # precedent).
        Index(
            "uq_scm_proforma_invoice_identity",
            text("coalesce(company_id, '%s'::uuid)" % _NIL_COMPANY),
            "supplier_id",
            "pi_number",
            unique=True,
        ),
        {"schema": "scm"},
    )


class ProformaInvoiceLine(Base, CompanyScopedMixin):
    """One priced line of a proforma, in the supplier's own spelling.

    `item_code` is verbatim - trimmed of outer whitespace and nothing else. Kailu writes
    `SRTWT8258\\n-GM` with a newline inside it, and normalising that away would quietly make
    the document disagree with the paper the supplier sent.

    `product_id` is nullable and set ONLY on an exact, case-insensitive, company-scoped match
    of `products.product_code` (AC-P1.3). An unmatched line is still stored and named in the
    preview: it is a real charge, and dropping it would make the invoice total wrong.

    `po_ref` is what the line says it is against, when it says anything. It is null on most
    lines and indexed anyway, because the verification task reads it across invoices.
    """
    __tablename__ = "proforma_invoice_line"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    invoice_id = Column(
        UUID(as_uuid=False), ForeignKey("scm.proforma_invoice.id", ondelete="CASCADE"),
        nullable=False,
    )
    line_no = Column(Integer, nullable=False)
    #: Where in the file this line was, so a question about it can be taken back to the row.
    row_number = Column(Integer, nullable=True)

    item_code = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    qty = Column(Numeric, nullable=False)
    uom = Column(String(20), nullable=True)
    unit_price = Column(Numeric, nullable=True)
    amount = Column(Numeric, nullable=True)
    po_ref = Column(String(100), nullable=True)
    remark = Column(Text, nullable=True)

    #: How the supplier packs it, and how much room it takes. All three are NULL rather than
    #: 0 on a document that states no volume (Kailu's), because 0 cbm and "not measured" are
    #: different answers to "will this fit" and only one of them is honest (AC-D1).
    cartons = Column(Numeric, nullable=True)
    cbm_per_unit = Column(Numeric, nullable=True)
    cbm_total = Column(Numeric, nullable=True)

    #: What the line weighs, as the supplier stated it (净重 / 毛重, N.W. / G.W.). NULL on a
    #: document that states neither, for the same reason the volumes are: a shipping weight
    #: of 0 kg and an unstated one are different answers, and only one of them is honest.
    net_weight = Column(Numeric(15, 4), nullable=True)
    gross_weight = Column(Numeric(15, 4), nullable=True)

    #: What it is made of and how it is boxed, as the supplier printed it (材质 / 装箱数 /
    #: 外箱尺寸). The container workbook derives the carton count and the volume from these,
    #: and `convert_to_draft_shipment` copies them onto the packing-list line so the sheet
    #: is printable without anybody re-typing the supplier's own measurements.
    #: Centimetres, as the documents state them.
    material = Column(String(255), nullable=True)
    pcs_per_carton = Column(Numeric(15, 4), nullable=True)
    carton_length_cm = Column(Numeric(10, 2), nullable=True)
    carton_width_cm = Column(Numeric(10, 2), nullable=True)
    carton_height_cm = Column(Numeric(10, 2), nullable=True)

    #: What the supplier said, frozen at import and never written again. `qty` and
    #: `unit_price` above are OURS to adjust to fit the container; these two are theirs, and
    #: the whole fulfilment journey rests on the two never being confused (AC-E2).
    supplier_qty = Column(Numeric, nullable=True)
    supplier_unit_price = Column(Numeric, nullable=True)

    product_id = Column(
        UUID(as_uuid=False), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    #: The line's other possible binding (R19/R21, migration 433): the supplier priced a
    #: SET. Stock lives on the members, so `convert_to_draft_shipment` explodes such a line
    #: into one shipment line per member - the invoice itself keeps the set code, because
    #: that is what the supplier reads.
    product_set_id = Column(
        UUID(as_uuid=False), ForeignKey("product_sets.id", ondelete="SET NULL"), nullable=True
    )

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    invoice = relationship("ProformaInvoice", back_populates="lines")

    __table_args__ = (
        Index("ix_scm_proforma_invoice_line_invoice", "invoice_id"),
        Index("ix_scm_proforma_invoice_line_po_ref", "po_ref"),
        Index("ix_scm_proforma_invoice_line_set", "product_set_id"),
        {"schema": "scm"},
    )


class ProformaInvoiceShipmentLink(Base, CompanyScopedMixin):
    """Where a proforma invoice line's goods actually went: the draft inbound shipment line
    created from it (the packing-list amendment, 20 Aug evening -
    `PLAN-scm-proforma-to-spo.md`).

    One row per PI line that the convert action touched. A link table rather than a column on
    `ProformaInvoiceLine`, because the later reconciliation against the REAL packing list can
    split one PI line's quantity across more than one shipment line - the same reason the next
    slice's PI-line -> SPO-line trail is also planned as a link table, not a column.

    `inbound_shipment_line_id` is nullable for the row that records a SKIP rather than a link:
    a PI line with no catalogue product match still needs its story told on the PI detail page
    ("where did this line go"), and `unmatched_reason` is that story. `inbound_shipment_id`
    is carried on every row (matched or skipped) so "which shipment did this PI convert into"
    answers without a null-line join.

    Existence of ANY row for a PI is what makes a second convert of the same PI idempotent -
    the service refuses it, naming the shipment this row already points at, rather than
    creating a second draft silently.
    """
    __tablename__ = "proforma_invoice_shipment_link"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    proforma_invoice_id = Column(
        UUID(as_uuid=False), ForeignKey("scm.proforma_invoice.id", ondelete="CASCADE"),
        nullable=False,
    )
    proforma_invoice_line_id = Column(
        UUID(as_uuid=False), ForeignKey("scm.proforma_invoice_line.id", ondelete="CASCADE"),
        nullable=False,
    )
    inbound_shipment_id = Column(
        UUID(as_uuid=False), ForeignKey("inbound_shipments.id", ondelete="CASCADE"),
        nullable=False,
    )
    inbound_shipment_line_id = Column(
        UUID(as_uuid=False), ForeignKey("inbound_shipment_lines.id", ondelete="SET NULL"),
        nullable=True,
    )
    #: Why this line has no `inbound_shipment_line_id` - e.g. "no catalogue product match".
    #: Null on a real link.
    unmatched_reason = Column(String(255), nullable=True)
    #: HOW MUCH of the line went to that shipment (Q9, migration 429). One line may be split
    #: across two containers, so the quantity lives on the link rather than being implied by
    #: the line. NULL on a SKIP row: nothing was placed, and a number there would say goods
    #: went somewhere they did not.
    qty = Column(Numeric, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_scm_pi_shipment_link_invoice", "proforma_invoice_id"),
        Index("ix_scm_pi_shipment_link_shipment", "inbound_shipment_id"),
        # NOT unique since migration 429: one PI line legitimately sits in two packing lists
        # (Q9). What stops a silent double convert is now the service, which compares what
        # is already placed against what the line holds - arithmetic an index cannot do.
        Index("ix_scm_pi_shipment_link_line", "proforma_invoice_line_id"),
        {"schema": "scm"},
    )


class ShipmentLineSpoLink(Base, CompanyScopedMixin):
    """Where a shipment line's demand actually went: the CRM SPO line "Create SPO" made for
    it, or why it made none (`PLAN-scm-proforma-to-spo.md`'s "Separate button after
    packing-list apply" decision, 20 Aug evening).

    Completes the trail the Amendment describes as two links composed - PI line -> shipment
    line (`ProformaInvoiceShipmentLink`, migration 405) and shipment line -> SPO line (this
    table). A shipment line reached from a real packing-list upload with no PI behind it at
    all still gets a row here; the PI half of the trail is simply absent for it.

    One row per shipment line PER "Create SPO" run that touched it - matched (points at
    the new SPO line) or skipped, with `unmatched_reason` naming why (no remainder left to
    pull, no supplier on the line, or simply left unticked). A shipment line can carry
    SEVERAL matched rows over its life (R1, `PLAN-scm-spo-planner-feedback-3sep.md`: "many
    SPOs per container") - one Create SPO run can leave a remainder for a later run to
    convert, and each run that matches the line writes its own row rather than replacing
    the one before it. `inbound_shipment_line_id` therefore carries a plain (non-unique)
    index (migration 469 dropped the UNIQUE one migration 406 first wrote, when one row per
    line, ever, was still the rule) - a line's total already-SPO'd quantity is the SUM of
    every matched row's own PO line `qty_ordered`, read by `spo_conversion_service`.
    """
    __tablename__ = "shipment_line_spo_link"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    inbound_shipment_id = Column(
        UUID(as_uuid=False), ForeignKey("inbound_shipments.id", ondelete="CASCADE"),
        nullable=False,
    )
    inbound_shipment_line_id = Column(
        UUID(as_uuid=False), ForeignKey("inbound_shipment_lines.id", ondelete="CASCADE"),
        nullable=False,
    )
    purchase_order_id = Column(
        UUID(as_uuid=False), ForeignKey("purchase_orders.id", ondelete="SET NULL"),
        nullable=True,
    )
    purchase_order_line_id = Column(
        UUID(as_uuid=False), ForeignKey("purchase_order_lines.id", ondelete="SET NULL"),
        nullable=True,
    )
    #: Why this line has no `purchase_order_line_id` - e.g. "Already covered by PO-...", "No
    #: supplier recorded on this line", "Not selected". Null on a real link.
    unmatched_reason = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_scm_shipment_spo_link_shipment", "inbound_shipment_id"),
        Index("ix_scm_shipment_spo_link_po", "purchase_order_id"),
        # The FK check when a purchase order line is deleted (see OrderLinkClaim).
        Index("ix_scm_shipment_spo_link_po_line", "purchase_order_line_id"),
        # One conversion OUTCOME per shipment line per Create SPO run - NOT unique (R1,
        # migration 469 dropped the unique index migration 406 first wrote): a line can
        # carry several matched rows across several runs once a remainder is convertible
        # again. Kept as a plain index since every reader still filters/aggregates by it.
        Index("ix_scm_shipment_spo_link_line", "inbound_shipment_line_id"),
        {"schema": "scm"},
    )
