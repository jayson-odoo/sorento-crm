"""`scm.committed_v` decides per LINE, so partial confirmation cannot lose demand.

Contract: `documentation/plans/scm/PLAN-fulfilment-planning-from-autocount-so.md` 13.4,
and the amended AC-C01 in `STAGE1C-scm-front-planning-promising.md`.

The captain ruled that Confirm is not gated on an order being fully decided:

> "we shouldn't block the confirm when the decision for the order are incomplete yet, we
>  might want to flow a few product to reorder planning first"

A confirmation therefore covers the SUBSET of lines the planner chose, and the rest stay
undecided on purpose. The view's `decided` CTE was keyed per ORDER - any active decision
took the whole order out of the sheet leg - so confirming one line of a twelve-line order
would have removed all twelve while only the confirmed line came back through the
confirmed leg. Eleven lines of demand nobody could see: the exact opposite of the reason
partial confirmation was asked for.

`decided` becomes the set of core sales-order LINES an active decision covers, read out
of `so_supply_decisions.line_snapshots` (one object per covered line, each carrying its
`core_line_id`). No new table and no new column: 13.4 left that open and recommended
measuring the lateral first, which is what this does.

Nothing else about the view moves. Same keys, same cardinality, same six columns in the
same order, so `scm.net_position_v` and every consumer of it are untouched and a plain
CREATE OR REPLACE is legal (no drop, no CASCADE).

The body is FROZEN in this file rather than imported from
`app.services.scm.demand.COMMITTED_V_SQL`: importing live code into a migration is the bug
that broke production's first replay of the SCM chain (340 / 346, and
`tests/scm/test_committed_v_migration_chain.py`, which pins both this body and the
downgrade copy below).

Revision ID: 384_committed_v_line_decision
Revises: 383_adopted_autocount_planning
Depends on: 376_scm_channel_read_model
"""
from alembic import op

revision = "384_committed_v_line_decision"
down_revision = "383_adopted_autocount_planning"
branch_labels = None
#: The revision whose body this one replaces. It is already an ancestor on this chain, and
#: the pin says so out loud so a rebase that reorders the SCM lanes cannot land this view
#: underneath the one it supersedes.
depends_on = "376_scm_channel_read_model"


_AS_OF_384 = """
CREATE OR REPLACE VIEW scm.committed_v AS
WITH decided AS (
    -- The core sales-order LINES an active decision covers, read out of the snapshot
    -- that records them. Per line, not per order: a confirmation covers the subset the
    -- planner chose, and the lines it left undecided must go on counting below.
    SELECT DISTINCT (snap->>'core_line_id')::uuid AS core_line_id
    FROM projects.so_supply_decisions d
    CROSS JOIN LATERAL jsonb_array_elements(d.line_snapshots) AS snap
    WHERE d.state = 'active'
      AND snap->>'core_line_id' IS NOT NULL
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
      -- Front planning narrows the sheet leg further: once CS has confirmed a LINE, its
      -- confirmed Buy residual below is the only Project reading of that line. Its
      -- undecided siblings are untouched and keep counting here.
      AND (so.demand_class IS DISTINCT FROM 'project'
           OR (so.demand_origin = 'scm_order_inquiry'
               AND NOT EXISTS (SELECT 1 FROM decided dd
                               WHERE dd.core_line_id = sol.id)))
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

# The body as migration `376_scm_channel_read_model` left it, for the downgrade. A verbatim
# copy of that revision's own `_AS_OF_376`, pinned equal by
# `tests/scm/test_committed_v_migration_chain.py` so the two cannot drift.
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


def upgrade() -> None:
    op.execute(_AS_OF_384)


def downgrade() -> None:
    op.execute(_AS_OF_376)
