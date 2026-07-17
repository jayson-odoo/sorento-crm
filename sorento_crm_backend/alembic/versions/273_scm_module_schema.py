"""SCM module foundation — public SO/PO core + scm brain schema (M0 CP1).

Creates the ``scm`` Postgres schema and its brain tables, the public
``sales_orders``/``purchase_orders`` core records, and extends
``product_suppliers``/``suppliers``/``picking_lines``/``market_segments``/``customers``
with SCM columns. Cross-schema FKs (scm.* → public.*) are normal Postgres FKs.

No views, no module registration, no seed, no RBAC here — those land in later
checkpoints. Data model only.

Revision ID: 273_scm_module_schema
Revises: 271_audit_action_allow_import
Create Date: 2026-07-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = "273_scm_module_schema"
down_revision = "271_audit_action_allow_import"
branch_labels = None
depends_on = None


def _source_cols():
    return (
        sa.Column("source_system", sa.String(), nullable=True),
        sa.Column("source_ref", sa.String(), nullable=True),
    )


def _created_at():
    return sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.text("now()"), nullable=False)


def _updated_at():
    return sa.Column("updated_at", sa.DateTime(timezone=False), server_default=sa.text("now()"), nullable=False)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS scm")

    # ------------------------------------------------------------------ public
    op.create_table(
        "sales_orders",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("so_number", sa.String(100), nullable=False, unique=True),
        sa.Column("customer_id", UUID(as_uuid=False), sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("order_date", sa.Date(), nullable=True),
        sa.Column("order_type", sa.String(50), nullable=True),
        sa.Column("priority", sa.String(20), nullable=True),
        sa.Column("status", sa.String(50), server_default="open", nullable=False),
        *_source_cols(),
        _created_at(),
        _updated_at(),
    )
    op.create_index("ix_sales_orders_customer_id", "sales_orders", ["customer_id"])
    op.create_index("ix_sales_orders_so_number", "sales_orders", ["so_number"])
    op.create_index("ix_sales_orders_status", "sales_orders", ["status"])

    op.create_table(
        "sales_order_lines",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("sales_order_id", UUID(as_uuid=False), sa.ForeignKey("sales_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", UUID(as_uuid=False), sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("warehouse_id", UUID(as_uuid=False), sa.ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("qty_ordered", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("qty_delivered", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("priority", sa.String(20), nullable=True),
        sa.Column("line_status", sa.String(50), server_default="open", nullable=False),
        *_source_cols(),
        _created_at(),
        _updated_at(),
    )
    op.create_index("ix_sales_order_lines_sales_order_id", "sales_order_lines", ["sales_order_id"])
    op.create_index("ix_sales_order_lines_product_id", "sales_order_lines", ["product_id"])
    op.create_index("ix_sales_order_lines_warehouse_id", "sales_order_lines", ["warehouse_id"])
    op.create_index("ix_sales_order_lines_product_warehouse_status", "sales_order_lines", ["product_id", "warehouse_id", "line_status"])

    op.create_table(
        "purchase_orders",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("po_number", sa.String(100), nullable=False, unique=True),
        sa.Column("supplier_id", UUID(as_uuid=False), sa.ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("expected_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(50), server_default="draft", nullable=False),
        sa.Column("currency", sa.String(3), nullable=True),
        *_source_cols(),
        _created_at(),
        _updated_at(),
    )
    op.create_index("ix_purchase_orders_supplier_id", "purchase_orders", ["supplier_id"])
    op.create_index("ix_purchase_orders_po_number", "purchase_orders", ["po_number"])
    op.create_index("ix_purchase_orders_status", "purchase_orders", ["status"])

    op.create_table(
        "purchase_order_lines",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("purchase_order_id", UUID(as_uuid=False), sa.ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", UUID(as_uuid=False), sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("warehouse_id", UUID(as_uuid=False), sa.ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("qty_ordered", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("qty_received", sa.Numeric(15, 4), server_default="0", nullable=False),
        sa.Column("unit_cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("expected_date", sa.Date(), nullable=True),
        sa.Column("moq_snapshot", sa.Integer(), nullable=True),
        sa.Column("order_multiple_snapshot", sa.Integer(), nullable=True),
        sa.Column("line_status", sa.String(50), server_default="open", nullable=False),
        *_source_cols(),
        _created_at(),
        _updated_at(),
    )
    op.create_index("ix_purchase_order_lines_purchase_order_id", "purchase_order_lines", ["purchase_order_id"])
    op.create_index("ix_purchase_order_lines_product_id", "purchase_order_lines", ["product_id"])
    op.create_index("ix_purchase_order_lines_warehouse_id", "purchase_order_lines", ["warehouse_id"])
    op.create_index("ix_purchase_order_lines_product_warehouse_status", "purchase_order_lines", ["product_id", "warehouse_id", "line_status"])

    # --------------------------------------------------------------- scm brain
    op.create_table(
        "reorder_policy",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("scope_type", sa.String(30), nullable=False),
        sa.Column("scope_ref", sa.String(255), nullable=True),
        sa.Column("policy_type", sa.String(30), nullable=False),
        sa.Column("service_level", sa.Numeric(), nullable=True),
        sa.Column("safety_stock_method", sa.String(30), nullable=True),
        sa.Column("safety_days", sa.Numeric(), nullable=True),
        sa.Column("review_period_days", sa.Integer(), nullable=True),
        sa.Column("forecast_window_days", sa.Integer(), nullable=True),
        sa.Column("baseline_source", sa.String(30), nullable=True),
        sa.Column("spike_handling", sa.String(30), nullable=True),
        sa.Column("buy_scope", sa.String(20), nullable=True),
        sa.Column("dead_stock_days", sa.Integer(), nullable=True),
        sa.Column("overstock_days", sa.Integer(), nullable=True),
        sa.Column("factor_toggles", JSONB(), nullable=True),
        sa.Column("factor_weights", JSONB(), nullable=True),
        sa.Column("min_override", sa.Numeric(), nullable=True),
        sa.Column("max_override", sa.Numeric(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=True),
        *_source_cols(),
        _created_at(),
        _updated_at(),
        schema="scm",
    )

    op.create_table(
        "item_classification",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("product_id", UUID(as_uuid=False), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("warehouse_id", UUID(as_uuid=False), sa.ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=True),
        sa.Column("abc_class", sa.String(1), nullable=True),
        sa.Column("xyz_class", sa.String(1), nullable=True),
        sa.Column("annual_value", sa.Numeric(), nullable=True),
        sa.Column("demand_cv", sa.Numeric(), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=False), nullable=True),
        *_source_cols(),
        _created_at(),
        sa.UniqueConstraint("product_id", "warehouse_id", name="uq_scm_item_classification_product_warehouse"),
        schema="scm",
    )

    op.create_table(
        "abc_xyz_policy",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("abc_a_pct", sa.Numeric(), nullable=True),
        sa.Column("abc_b_pct", sa.Numeric(), nullable=True),
        sa.Column("xyz_x_max", sa.Numeric(), nullable=True),
        sa.Column("xyz_y_max", sa.Numeric(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *_source_cols(),
        _created_at(),
        _updated_at(),
        schema="scm",
    )

    op.create_table(
        "supplier_scoring_policy",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("delivery_weight", sa.Numeric(), nullable=True),
        sa.Column("quality_weight", sa.Numeric(), nullable=True),
        sa.Column("grace_days", sa.Integer(), nullable=True),
        sa.Column("min_sample_size", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *_source_cols(),
        _created_at(),
        _updated_at(),
        schema="scm",
    )

    op.create_table(
        "supplier_performance",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("supplier_id", UUID(as_uuid=False), sa.ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", UUID(as_uuid=False), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("on_time_rate", sa.Numeric(), nullable=True),
        sa.Column("avg_lead_time_days", sa.Numeric(), nullable=True),
        sa.Column("lead_time_variance", sa.Numeric(), nullable=True),
        sa.Column("reject_rate", sa.Numeric(), nullable=True),
        sa.Column("fill_rate", sa.Numeric(), nullable=True),
        sa.Column("composite_score", sa.Numeric(), nullable=True),
        sa.Column("sample_size", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.String(20), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=False), nullable=True),
        *_source_cols(),
        _created_at(),
        schema="scm",
    )
    op.create_index("ix_scm_supplier_performance_supplier_id", "supplier_performance", ["supplier_id"], schema="scm")
    op.create_index("ix_scm_supplier_performance_product_id", "supplier_performance", ["product_id"], schema="scm")

    op.create_table(
        "purchasing_budget",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("budget_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("scope_type", sa.String(20), nullable=True),
        sa.Column("scope_ref", sa.String(255), nullable=True),
        sa.Column("set_by", sa.String(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        *_source_cols(),
        _created_at(),
        _updated_at(),
        schema="scm",
    )

    op.create_table(
        "reorder_run",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("status", sa.String(30), server_default="running", nullable=False),
        sa.Column("warehouse_ids", JSONB(), nullable=True),
        sa.Column("buy_scope", sa.String(20), nullable=True),
        sa.Column("budget_id", UUID(as_uuid=False), sa.ForeignKey("scm.purchasing_budget.id", ondelete="SET NULL"), nullable=True),
        sa.Column("policy_snapshot_ref", sa.String(), nullable=True),
        *_source_cols(),
        _created_at(),
        schema="scm",
    )

    op.create_table(
        "reorder_recommendation",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("run_id", UUID(as_uuid=False), sa.ForeignKey("scm.reorder_run.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", UUID(as_uuid=False), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("warehouse_id", UUID(as_uuid=False), sa.ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True),
        sa.Column("supplier_id", UUID(as_uuid=False), sa.ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("net_position", sa.Numeric(), nullable=True),
        sa.Column("reorder_point", sa.Numeric(), nullable=True),
        sa.Column("forecast_daily_demand", sa.Numeric(), nullable=True),
        sa.Column("days_of_cover", sa.Numeric(), nullable=True),
        sa.Column("recommended_qty", sa.Numeric(), nullable=True),
        sa.Column("rounded_qty", sa.Numeric(), nullable=True),
        sa.Column("unit_cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("cash_impact", sa.Numeric(15, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("urgency_score", sa.Numeric(), nullable=True),
        sa.Column("priority_score", sa.Numeric(), nullable=True),
        sa.Column("rank_score", sa.Numeric(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("confidence_band", sa.String(20), nullable=True),
        sa.Column("triggered_reason", sa.String(100), nullable=True),
        sa.Column("allocation", JSONB(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("market_advisory", sa.Text(), nullable=True),
        sa.Column("funding_status", sa.String(20), nullable=True),
        sa.Column("status", sa.String(20), server_default="proposed", nullable=False),
        *_source_cols(),
        _created_at(),
        schema="scm",
    )
    op.create_index("ix_scm_reorder_recommendation_run_id", "reorder_recommendation", ["run_id"], schema="scm")
    op.create_index("ix_scm_reorder_recommendation_product_id", "reorder_recommendation", ["product_id"], schema="scm")

    op.create_table(
        "recommendation_override",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("recommendation_id", UUID(as_uuid=False), sa.ForeignKey("scm.reorder_recommendation.id", ondelete="CASCADE"), nullable=False),
        sa.Column("original_qty", sa.Numeric(), nullable=True),
        sa.Column("override_qty", sa.Numeric(), nullable=True),
        sa.Column("override_supplier_id", UUID(as_uuid=False), sa.ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reason_text", sa.Text(), nullable=True),
        sa.Column("reason_code", sa.String(50), nullable=True),
        sa.Column("reason_confidence", sa.Numeric(), nullable=True),
        sa.Column("suggested_action", sa.String(100), nullable=True),
        sa.Column("action_applied", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("overridden_by", sa.String(), nullable=True),
        sa.Column("overridden_at", sa.DateTime(timezone=False), nullable=True),
        *_source_cols(),
        _created_at(),
        schema="scm",
    )
    op.create_index("ix_scm_recommendation_override_recommendation_id", "recommendation_override", ["recommendation_id"], schema="scm")

    op.create_table(
        "override_reason",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("reason_code", sa.String(50), nullable=False, unique=True),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *_source_cols(),
        _created_at(),
        _updated_at(),
        schema="scm",
    )

    op.create_table(
        "reason_action_map",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("reason_code", sa.String(50), nullable=False),
        sa.Column("suggested_action", sa.String(100), nullable=True),
        sa.Column("target_policy_field", sa.String(100), nullable=True),
        sa.Column("adjustment", sa.String(100), nullable=True),
        sa.Column("trigger_type", sa.String(20), nullable=True),
        sa.Column("threshold_n", sa.Integer(), nullable=True),
        sa.Column("window_days", sa.Integer(), nullable=True),
        *_source_cols(),
        _created_at(),
        _updated_at(),
        schema="scm",
    )

    op.create_table(
        "cash_ranking_policy",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("weight_urgency", sa.Numeric(), nullable=True),
        sa.Column("weight_margin", sa.Numeric(), nullable=True),
        sa.Column("weight_abc", sa.Numeric(), nullable=True),
        sa.Column("weight_priority", sa.Numeric(), nullable=True),
        sa.Column("weight_committed", sa.Numeric(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        *_source_cols(),
        _created_at(),
        _updated_at(),
        schema="scm",
    )

    op.create_table(
        "demand_nature_map",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("order_type_option_id", UUID(as_uuid=False), sa.ForeignKey("lookup_options.id", ondelete="CASCADE"), nullable=True),
        sa.Column("demand_nature", sa.String(20), nullable=True),
        *_source_cols(),
        _created_at(),
        _updated_at(),
        schema="scm",
    )

    op.create_table(
        "demand_stat",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("product_id", UUID(as_uuid=False), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("warehouse_id", UUID(as_uuid=False), sa.ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=True),
        sa.Column("avg_daily_demand", sa.Numeric(), nullable=True),
        sa.Column("baseline_rate", sa.Numeric(), nullable=True),
        sa.Column("spike_rate", sa.Numeric(), nullable=True),
        sa.Column("demand_cv", sa.Numeric(), nullable=True),
        sa.Column("variability", sa.Numeric(), nullable=True),
        sa.Column("window_days", sa.Integer(), nullable=True),
        sa.Column("sample_days", sa.Integer(), nullable=True),
        sa.Column("method", sa.String(30), nullable=True),
        sa.Column("channel_split", JSONB(), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=False), nullable=True),
        *_source_cols(),
        _created_at(),
        sa.UniqueConstraint("product_id", "warehouse_id", name="uq_scm_demand_stat_product_warehouse"),
        schema="scm",
    )

    op.create_table(
        "market_research_topic",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("category_ref", sa.String(255), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("search_prompt", sa.Text(), nullable=True),
        sa.Column("cadence", sa.String(50), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *_source_cols(),
        _created_at(),
        _updated_at(),
        schema="scm",
    )

    op.create_table(
        "market_signal",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("topic_id", UUID(as_uuid=False), sa.ForeignKey("scm.market_research_topic.id", ondelete="CASCADE"), nullable=True),
        sa.Column("category_ref", sa.String(255), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("value", sa.Numeric(), nullable=True),
        sa.Column("trend", sa.String(30), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=False), nullable=True),
        *_source_cols(),
        _created_at(),
        schema="scm",
    )
    op.create_index("ix_scm_market_signal_topic_id", "market_signal", ["topic_id"], schema="scm")

    op.create_table(
        "scm_analytics_run",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("status", sa.String(30), nullable=True),
        sa.Column("scope", JSONB(), nullable=True),
        sa.Column("counts", JSONB(), nullable=True),
        sa.Column("window_days", sa.Integer(), nullable=True),
        sa.Column("config_ref", sa.String(), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        *_source_cols(),
        _created_at(),
        schema="scm",
    )

    op.create_table(
        "market_research_run",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("status", sa.String(30), nullable=True),
        sa.Column("counts", JSONB(), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        *_source_cols(),
        _created_at(),
        schema="scm",
    )

    # ----------------------------------------------- extend existing public tables
    op.add_column("product_suppliers", sa.Column("moq", sa.Integer(), nullable=True))
    op.add_column("product_suppliers", sa.Column("order_multiple", sa.Integer(), nullable=True))
    op.add_column("product_suppliers", sa.Column("unit_cost", sa.Numeric(12, 2), nullable=True))
    op.add_column("product_suppliers", sa.Column("currency", sa.String(3), nullable=True))
    op.add_column("product_suppliers", sa.Column("is_primary_supplier", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("product_suppliers", sa.Column("lead_time_variability_days", sa.Numeric(), nullable=True))

    op.add_column("suppliers", sa.Column("current_performance_score", sa.Numeric(), nullable=True))

    op.add_column(
        "picking_lines",
        sa.Column("po_line_id", UUID(as_uuid=False), sa.ForeignKey("purchase_order_lines.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column("picking_lines", sa.Column("qty_accepted", sa.Integer(), nullable=True))
    op.add_column("picking_lines", sa.Column("qty_rejected", sa.Integer(), nullable=True))
    op.create_index("ix_picking_lines_po_line_id", "picking_lines", ["po_line_id"])

    op.add_column("market_segments", sa.Column("demand_nature", sa.String(20), nullable=True))

    op.add_column(
        "customers",
        sa.Column("market_segment_code", sa.String(50), sa.ForeignKey("market_segments.code", ondelete="SET NULL"), nullable=True),
    )


def downgrade() -> None:
    # 1. Drop the columns added to existing public tables (removes their FKs first).
    op.drop_column("customers", "market_segment_code")
    op.drop_column("market_segments", "demand_nature")
    op.drop_index("ix_picking_lines_po_line_id", table_name="picking_lines")
    op.drop_column("picking_lines", "qty_rejected")
    op.drop_column("picking_lines", "qty_accepted")
    op.drop_column("picking_lines", "po_line_id")
    op.drop_column("suppliers", "current_performance_score")
    op.drop_column("product_suppliers", "lead_time_variability_days")
    op.drop_column("product_suppliers", "is_primary_supplier")
    op.drop_column("product_suppliers", "currency")
    op.drop_column("product_suppliers", "unit_cost")
    op.drop_column("product_suppliers", "order_multiple")
    op.drop_column("product_suppliers", "moq")

    # 2. Drop the public SO/PO core tables (child lines before parents).
    op.drop_table("purchase_order_lines")
    op.drop_table("purchase_orders")
    op.drop_table("sales_order_lines")
    op.drop_table("sales_orders")

    # 3. Drop the scm schema and all its brain tables in one shot.
    op.execute("DROP SCHEMA IF EXISTS scm CASCADE")
