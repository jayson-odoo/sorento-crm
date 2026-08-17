"""Front planning stage 2: the channel-aware read model and the Product-grain row.

Four things, one contract (PLAN-scm-front-planning.md sections 4, 5.3, 5.4, 6.2, 6.3, 6.4):

1. `projects.so_supply_decisions` + `projects.order_inquiry_rows.supply_decision_id`.
   Section 4 defines Project demand as "confirmed unplaced Buy pointing at an ACTIVE
   decision", so the predicate needs a real table to be a real predicate. Stage 2 only
   READS these; Stage 1C owns the atomic confirmation that writes them.

2. `scm.committed_v` gains `project_committed`, `retail_committed` and
   `unclassified_committed` on the SAME (product_id, warehouse_id) row. `committed` stays
   their sum, and `scm.net_position_v` keeps its keys, its cardinality and its columns, so
   every existing consumer is untouched.

3. `scm.order_summary_row` gains the six front-planning columns, all nullable: a run
   created before the contract has no breakdown, and that NULL is a durable legacy marker
   rather than a backfill nobody has got round to (AC-F10).

4. `scm.order_summary_location_allocation` - the narrow child that persists the allocator
   rerun's split of a Product-grain chosen quantity back to locations.

The view is dropped and recreated rather than replaced. Postgres will only let CREATE OR
REPLACE VIEW append columns, which this change does happen to do, but the drop is CASCADE
anyway because `net_position_v` selects from `committed_v`, and recreating both from
frozen bodies is what makes the outcome independent of which of the two rules the
database was carrying beforehand (migration 311 established the same pattern).

The view body is FROZEN in this file rather than imported from
`app.services.scm.demand.COMMITTED_V_SQL`: importing live code into a migration is the
bug that broke production's first replay of the SCM chain (see 340 / 346 and
`tests/scm/test_committed_v_migration_chain.py`).

Revision ID: 376_scm_channel_read_model
Revises: 375_plan_grain_run_stamp
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "376_scm_channel_read_model"
down_revision = "375_plan_grain_run_stamp"
branch_labels = None
depends_on = None

SORENTO = "00000000-0000-0000-0000-000000000001"


_AS_OF_376 = """
CREATE OR REPLACE VIEW scm.committed_v AS
WITH decided AS (
    SELECT DISTINCT pso.so_id AS sales_order_id
    FROM projects.sales_orders pso
    JOIN projects.so_supply_decisions d
      ON d.project_sales_order_id = pso.id
     AND d.state = 'active'
    WHERE pso.so_id IS NOT NULL
),
legs AS (
    SELECT sol.product_id,
           sol.warehouse_id,
           CASE WHEN so.demand_class = 'project'
                THEN GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
                              - COALESCE(sol.qty_delivered, 0), 0)
                ELSE 0 END AS project_qty,
           CASE WHEN so.demand_class IS NOT NULL AND so.demand_class <> 'project'
                THEN GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
                              - COALESCE(sol.qty_delivered, 0), 0)
                ELSE 0 END AS retail_qty,
           CASE WHEN so.demand_class IS NULL
                THEN GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
                              - COALESCE(sol.qty_delivered, 0), 0)
                ELSE 0 END AS unclassified_qty
    FROM sales_order_lines sol
    JOIN sales_orders so ON so.id = sol.sales_order_id
    WHERE so.status = 'open'
      AND sol.line_status = 'open'
      AND sol.purchasing_status <> 'covered'
      AND GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
                   - COALESCE(sol.qty_delivered, 0), 0) > 0
      -- S13b: project demand comes from the Order Inquiry; the book supplies the rest.
      -- Front planning narrows the sheet leg further: once CS has confirmed a decision
      -- for the order, its confirmed Buy residual below is the only Project reading.
      AND (so.demand_class IS DISTINCT FROM 'project'
           OR (so.demand_origin = 'scm_order_inquiry'
               AND NOT EXISTS (SELECT 1 FROM decided dd
                               WHERE dd.sales_order_id = so.id)))
    UNION ALL
    -- The confirmed leg: what CS decided must be bought, at the reconciled core line's
    -- product and fulfilment location. Never matched on provisional_ref, autocount_doc_no
    -- or item code (plan 4).
    SELECT sol.product_id,
           sol.warehouse_id,
           oir.qty AS project_qty,
           0 AS retail_qty,
           0 AS unclassified_qty
    FROM projects.order_inquiry_rows oir
    JOIN projects.so_supply_decisions d
      ON d.id = oir.supply_decision_id
     AND d.state = 'active'
    JOIN projects.sales_order_lines psl ON psl.id = oir.so_line_id
    JOIN sales_order_lines sol ON sol.id = psl.core_sales_order_line_id
    WHERE oir.verb = 'ORDER'
      AND oir.state = 'raised'
      AND oir.qty > 0
)
SELECT product_id,
       warehouse_id,
       SUM(project_qty + retail_qty + unclassified_qty) AS committed,
       SUM(project_qty) AS project_committed,
       SUM(retail_qty) AS retail_committed,
       SUM(unclassified_qty) AS unclassified_committed
FROM legs
GROUP BY product_id, warehouse_id;
"""

# The body as migration 346 left it, for the downgrade.
_AS_OF_346 = """
CREATE OR REPLACE VIEW scm.committed_v AS
SELECT sol.product_id,
       sol.warehouse_id,
       SUM(GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
                    - COALESCE(sol.qty_delivered, 0), 0)) AS committed
FROM sales_order_lines sol
JOIN sales_orders so ON so.id = sol.sales_order_id
WHERE so.status = 'open'
  AND sol.line_status = 'open'
  AND sol.purchasing_status <> 'covered'
  AND GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
               - COALESCE(sol.qty_delivered, 0), 0) > 0
  -- S13b: project demand comes from the Order Inquiry; the book supplies the rest
  AND (so.demand_class IS DISTINCT FROM 'project'
       OR so.demand_origin = 'scm_order_inquiry')
GROUP BY sol.product_id, sol.warehouse_id;
"""

# Unchanged since migration 274, recreated here because the CASCADE drop above takes it
# with the view it selects from.
_NET_POSITION_V = """
CREATE VIEW scm.net_position_v AS
WITH keys AS (
    SELECT product_id, warehouse_id FROM stock
    UNION
    SELECT product_id, warehouse_id FROM scm.on_order_v
    UNION
    SELECT product_id, warehouse_id FROM scm.committed_v
)
SELECT k.product_id, k.warehouse_id,
       COALESCE(s.quantity_on_hand, 0) AS quantity_on_hand,
       COALESCE(oo.on_order, 0) AS on_order,
       COALESCE(cm.committed, 0) AS committed,
       COALESCE(s.quantity_on_hand, 0) + COALESCE(oo.on_order, 0)
           - COALESCE(cm.committed, 0) AS net_position
FROM keys k
LEFT JOIN stock s ON s.product_id = k.product_id AND s.warehouse_id = k.warehouse_id
LEFT JOIN scm.on_order_v oo
  ON oo.product_id = k.product_id AND oo.warehouse_id = k.warehouse_id
LEFT JOIN scm.committed_v cm
  ON cm.product_id = k.product_id AND cm.warehouse_id = k.warehouse_id;
"""


def upgrade() -> None:
    # --- 1. the atomic supply decision (plan 6.2) --------------------------------------
    op.create_table(
        "so_supply_decisions",
        sa.Column("id", PG_UUID(as_uuid=False), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_sales_order_id", PG_UUID(as_uuid=False),
                  sa.ForeignKey("projects.sales_orders.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default=sa.text("'active'")),
        sa.Column("source_revision", sa.String(64), nullable=True),
        sa.Column("line_snapshots", JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("confirmed_by", sa.String(100),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=False), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("supersedes_id", PG_UUID(as_uuid=False),
                  sa.ForeignKey("projects.so_supply_decisions.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("superseded_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("company_id", PG_UUID(as_uuid=False),
                  sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False,
                  server_default=sa.text(f"'{SORENTO}'::uuid")),
        sa.UniqueConstraint("project_sales_order_id", "revision_no",
                            name="uq_projects_so_supply_decision_rev"),
        sa.CheckConstraint("state IN ('active', 'superseded', 'challenged')",
                           name="ck_projects_so_supply_decision_state"),
        schema="projects",
    )
    # One active revision per Project SO, in the database rather than in a service that
    # has to remember: two of them would count one requirement twice.
    op.create_index(
        "uq_projects_so_supply_decision_active", "so_supply_decisions",
        ["project_sales_order_id"], unique=True, schema="projects",
        postgresql_where=sa.text("state = 'active'"),
    )
    op.create_index("ix_projects_so_supply_decisions_company_state", "so_supply_decisions",
                    ["company_id", "state"], schema="projects")

    # --- 2. the Buy row's decision pointer (plan 6.3) ----------------------------------
    op.add_column(
        "order_inquiry_rows",
        sa.Column("supply_decision_id", PG_UUID(as_uuid=False), nullable=True),
        schema="projects",
    )
    op.create_foreign_key(
        "fk_project_order_inquiry_rows_supply_decision",
        "order_inquiry_rows", "so_supply_decisions",
        ["supply_decision_id"], ["id"],
        source_schema="projects", referent_schema="projects", ondelete="SET NULL",
    )
    op.create_index("ix_project_order_inquiry_rows_supply_decision", "order_inquiry_rows",
                    ["supply_decision_id"], schema="projects")

    # --- 3. the channel-aware committed view (plan 4, 6.4) ----------------------------
    op.execute("DROP VIEW IF EXISTS scm.committed_v CASCADE")
    op.execute(_AS_OF_376)
    op.execute(_NET_POSITION_V)

    # --- 4. the Product-grain row and its location split (plan 6.4) -------------------
    # Every column nullable: an existing row belongs to a run created before the contract
    # and is not split, duplicated, defaulted or made actionable.
    for column in (
        sa.Column("project_buy_qty", sa.Numeric(), nullable=True),
        sa.Column("retail_replenishment_qty", sa.Numeric(), nullable=True),
        sa.Column("unclassified_demand_qty", sa.Numeric(), nullable=True),
        sa.Column("earliest_project_need_date", sa.Date(), nullable=True),
        sa.Column("channel_calculation_basis", JSONB(), nullable=True),
        sa.Column("uom_decimal_places", sa.SmallInteger(), nullable=True),
        # The one non-nullable addition, and deliberately so: it is a count of the open
        # order book beside the two line counts already on the row, not part of the
        # channel arithmetic. An existing row reads 0, which is what it counted.
        sa.Column("unclassified_line_count", sa.Integer(), nullable=False,
                  server_default=sa.text("0")),
    ):
        op.add_column("order_summary_row", column, schema="scm")

    op.create_table(
        "order_summary_location_allocation",
        sa.Column("id", PG_UUID(as_uuid=False), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("order_summary_row_id", PG_UUID(as_uuid=False),
                  sa.ForeignKey("scm.order_summary_row.id", ondelete="CASCADE"),
                  nullable=False),
        # Nullable: a product-grain split has no single owning recommendation row, and
        # naming one would imply a location decision nobody made.
        sa.Column("reorder_recommendation_id", PG_UUID(as_uuid=False),
                  sa.ForeignKey("scm.reorder_recommendation.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("warehouse_id", PG_UUID(as_uuid=False),
                  sa.ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("allocated_qty", sa.Numeric(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("company_id", PG_UUID(as_uuid=False),
                  sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False,
                  server_default=sa.text(f"'{SORENTO}'::uuid")),
        sa.CheckConstraint("allocated_qty >= 0",
                           name="ck_scm_order_summary_location_alloc_qty"),
        schema="scm",
    )
    op.create_index("uq_scm_order_summary_location_alloc",
                    "order_summary_location_allocation",
                    ["order_summary_row_id", "warehouse_id"], unique=True, schema="scm")


def downgrade() -> None:
    op.drop_index("uq_scm_order_summary_location_alloc",
                  table_name="order_summary_location_allocation", schema="scm")
    op.drop_table("order_summary_location_allocation", schema="scm")
    for name in ("unclassified_line_count", "uom_decimal_places",
                 "channel_calculation_basis", "earliest_project_need_date",
                 "unclassified_demand_qty", "retail_replenishment_qty",
                 "project_buy_qty"):
        op.drop_column("order_summary_row", name, schema="scm")

    op.execute("DROP VIEW IF EXISTS scm.committed_v CASCADE")
    op.execute(_AS_OF_346)
    op.execute(_NET_POSITION_V)

    op.drop_index("ix_project_order_inquiry_rows_supply_decision",
                  table_name="order_inquiry_rows", schema="projects")
    op.drop_constraint("fk_project_order_inquiry_rows_supply_decision",
                       "order_inquiry_rows", schema="projects", type_="foreignkey")
    op.drop_column("order_inquiry_rows", "supply_decision_id", schema="projects")

    op.drop_index("ix_projects_so_supply_decisions_company_state",
                  table_name="so_supply_decisions", schema="projects")
    op.drop_index("uq_projects_so_supply_decision_active",
                  table_name="so_supply_decisions", schema="projects")
    op.drop_table("so_supply_decisions", schema="projects")
