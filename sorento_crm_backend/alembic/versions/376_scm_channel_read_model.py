"""Front planning stage 2: the channel-aware read model and the Product-grain row.

Three things, one contract (PLAN-scm-front-planning.md sections 4, 5.3, 5.4, 6.2, 6.3, 6.4):

0. NOT `projects.so_supply_decisions` any more. This revision used to create that table and
   `projects.order_inquiry_rows.supply_decision_id` as its step 1, because Stage 2 needs a
   real table to make section 4's predicate a real predicate and Stage 1C had not merged
   yet. Both stages are in the same tree now, and the docstring above stated the owner:
   Stage 1C writes the decision, Stage 2 only READS it. So `374_so_supply_decisions` owns
   that DDL and this revision `depends_on` it - running both would abort on "relation
   already exists". `depends_on` rather than a renumbered `down_revision` because 374 is a
   landed revision on a sibling branch: it orders the two across the fork without rewriting
   either chain, which also guarantees this revision's view body lands AFTER 374's and not
   under it.

1. `scm.committed_v` gains `project_committed`, `retail_committed`,
   `unclassified_committed` and `project_confirmed_committed` on the SAME
   (product_id, warehouse_id) row. `committed` stays the sum of the first three, and
   `scm.net_position_v` keeps its keys, its cardinality and its columns, so every existing
   consumer is untouched. `project_confirmed_committed` is a SUBSET of `project_committed`:
   the confirmed-decision leg alone, which is the only leg the engine treats as firm Buy
   (plan 5.3, AC-E04, AC-E05). The sheet leg stays in the display column and is netted.

2. `scm.order_summary_row` gains the six front-planning columns, all nullable: a run
   created before the contract has no breakdown, and that NULL is a durable legacy marker
   rather than a backfill nobody has got round to (AC-F10).

3. `scm.order_summary_location_allocation` - the narrow child that persists the allocator
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
Depends on: 374_so_supply_decisions
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "376_scm_channel_read_model"
down_revision = "375_plan_grain_run_stamp"
branch_labels = None
#: Stage 1C creates `projects.so_supply_decisions` and the `supply_decision_id` pointer
#: this revision's view reads. The two lanes are siblings off `373_merge_scm_stage0_1a`,
#: so without this alembic is free to run them in either order and the view would either
#: name a table that does not exist yet or be overwritten by 374's older body afterwards.
depends_on = "374_so_supply_decisions"

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
           -- The sheet leg is project-class demand, never firm Buy: no CS decision points
           -- at it, so it is netted like any other commitment (S13b).
           0 AS project_confirmed_qty,
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
           oir.qty AS project_confirmed_qty,
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
       SUM(unclassified_qty) AS unclassified_committed,
       -- LAST on purpose: appended, so a CREATE OR REPLACE of this body over a database
       -- already carrying the four-column view is legal (Postgres lets a replacement add
       -- columns at the end and nowhere else). A SUBSET of `project_committed`, never a
       -- fourth addend of `committed` - adding it there would count confirmed Buy twice.
       SUM(project_confirmed_qty) AS project_confirmed_committed
FROM legs
GROUP BY product_id, warehouse_id;
"""

# The body as migration `374_so_supply_decisions` left it, for the downgrade. A verbatim
# copy of that revision's own `_AS_OF_374`, pinned equal by
# `tests/scm/test_committed_v_migration_chain.py` so the two cannot drift.
_AS_OF_374 = """
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
  -- S13b: project demand comes from the Order Inquiry; the book supplies the rest.
  -- Front planning section 4: and only while CS has not confirmed a supply decision for
  -- it, after which the confirmed Buy residual replaces the sheet quantity.
  AND (so.demand_class IS DISTINCT FROM 'project'
       OR (so.demand_origin = 'scm_order_inquiry'
           AND NOT EXISTS (
               SELECT 1
               FROM projects.sales_orders pso
               JOIN projects.so_supply_decisions d
                 ON d.project_sales_order_id = pso.id
               WHERE pso.so_id = so.id
                 AND d.state = 'active'
           )))
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
    # Steps 1 and 2 (creating `projects.so_supply_decisions` and adding
    # `order_inquiry_rows.supply_decision_id`) lived here and are gone: Stage 1C's
    # `374_so_supply_decisions` owns that DDL and `depends_on` above pins it to run
    # first. See the docstring, item 0.

    # --- 1. the channel-aware committed view (plan 4, 6.4) ----------------------------
    op.execute("DROP VIEW IF EXISTS scm.committed_v CASCADE")
    op.execute(_AS_OF_376)
    op.execute(_NET_POSITION_V)

    # --- 2. the Product-grain row and its location split (plan 6.4) -------------------
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
    # 374's body, not 346's. `depends_on` puts `374_so_supply_decisions` underneath this
    # revision, so downgrading one step lands on 374, and restoring 346's body here would
    # silently drop the sheet-leg narrowing 374 installed and still leave 374 stamped.
    op.execute(_AS_OF_374)
    op.execute(_NET_POSITION_V)

    # The decision table and the `supply_decision_id` pointer are NOT dropped here: they
    # belong to 374 and 374's own downgrade removes them.
