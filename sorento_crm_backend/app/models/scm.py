"""SCM (Supply Chain & Inventory Optimisation) module brain models.

All tables live in a dedicated ``scm`` Postgres schema (``__table_args__`` carries
``{"schema": "scm"}``). They die with the module on uninstall; the core business
records (sales_order/purchase_order + product_suppliers/suppliers/picking_lines
extensions) stay in ``public``.

Cross-schema FKs into ``public`` are NORMAL Postgres foreign keys — public is the
default search-path schema, so references are unqualified (``ForeignKey("products.id")``).
scm→scm FKs are schema-qualified (``ForeignKey("scm.reorder_run.id")``).

Per AC-M0.3 every table carries ``source_system`` + ``source_ref`` (``'seed'`` for demo
rows, ``'manual'`` for future UI rows).
"""
from sqlalchemy import (
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
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
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
    policy_type = Column(String(30), nullable=False)  # reorder_point | periodic_review | min_max
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


class PurchasingBudget(Base):
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


class ReorderRun(Base):
    """One planning run; recommendations freeze their inputs against it."""
    __tablename__ = "reorder_run"
    __table_args__ = {"schema": "scm"}

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    created_by = Column(String, nullable=True)
    status = Column(String(30), default="running", nullable=False)  # running | completed | failed
    warehouse_ids = Column(JSONB, nullable=True)
    # The product scope of a manual plan. NULL means none was asked for (the daily run,
    # which plans everything); an EMPTY list means one was asked for and nothing resolved
    # (a mistyped code), which must plan nothing rather than widen to the whole catalogue.
    product_ids = Column(JSONB, nullable=True)
    buy_scope = Column(String(20), nullable=True)  # network | warehouse
    budget_id = Column(UUID(as_uuid=False), ForeignKey("scm.purchasing_budget.id", ondelete="SET NULL"), nullable=True)
    budget_amount = Column(Numeric(15, 2), nullable=True)  # M4 — chosen budget the "Apply budget" action persists
    include_market = Column(Boolean, nullable=False, default=False)  # M7 — opt-in market-trend priority factor
    policy_snapshot_ref = Column(String, nullable=True)
    started_at = Column(DateTime(timezone=False), nullable=True)
    finished_at = Column(DateTime(timezone=False), nullable=True)
    error_text = Column(Text, nullable=True)  # set on status='failed'
    run_log = Column(JSONB, nullable=True)  # {stage, buy, disposition, exceptions, total_cash_impact, recommendation_count, duration_ms}
    overview = Column(Text, nullable=True)  # LLM (M5) — lazy-cached run-level AI overview
    source_system = Column(String, nullable=True)
    source_ref = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    recommendations = relationship(
        "ReorderRecommendation",
        back_populates="run",
        cascade="all, delete-orphan",
    )


class ReorderRecommendation(Base):
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
    unit_cost = Column(Numeric(12, 2), nullable=True)
    cash_impact = Column(Numeric(15, 2), nullable=True)
    currency = Column(String(3), nullable=True)
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
    status = Column(String(20), default="proposed", nullable=False)  # proposed | accepted | adjusted | dismissed
    source_system = Column(String, nullable=True)
    source_ref = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    run = relationship("ReorderRun", back_populates="recommendations")
    overrides = relationship(
        "RecommendationOverride",
        back_populates="recommendation",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_scm_reorder_recommendation_run_id", "run_id"),
        Index("ix_scm_reorder_recommendation_product_id", "product_id"),
        {"schema": "scm"},
    )


class RecommendationOverride(Base):
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
    weight_market = Column(Numeric, nullable=True)  # M7 — market-trend priority factor
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


class ScmAnalyticsRun(Base):
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


class MarketResearchRun(Base):
    """Observability log for the M5 web-search market research job (mirrors
    ``scm_analytics_run``): one row per run, status running → completed | failed."""
    __tablename__ = "market_research_run"
    __table_args__ = {"schema": "scm"}

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    status = Column(String(30), default="running", nullable=False)  # running | completed | failed
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
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class OrderSummaryRow(Base):
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
    # NULL when nothing is outstanding, which is not the same as 0 days outstanding.
    max_days_outstanding = Column(Integer, nullable=True)

    chosen_qty = Column(Numeric, nullable=True)
    chosen_supplier_id = Column(
        UUID(as_uuid=False), ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True
    )
    decided_by = Column(String, nullable=True)
    decided_at = Column(DateTime(timezone=False), nullable=True)

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
        {"schema": "scm"},
    )
