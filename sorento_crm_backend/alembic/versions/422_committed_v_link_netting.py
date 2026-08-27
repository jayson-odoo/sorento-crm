"""`scm.committed_v` nets the UNLINKED remainder of a row, instead of testing its state

Revision ID: 422_committed_v_link_netting
Revises: 421_order_inquiry_links
Create Date: 2026-08-26 15:30:00.000000

`PLAN-scm-cs-planning-uat.md` section 3.I: "`committed_v` nets `qty - linked qty` per row
instead of testing `state = 'placed'`".

The confirmed leg used to be all or nothing. A `raised` row counted its whole quantity and
a `placed` one counted none, so a cascade that could only cover PART of a row had nowhere
to put the arithmetic and SPLIT the row instead - which is how SO414285's nine sales-order
lines came to read as eleven instructions. Migration 421 gave a row many links and a middle
state; this is the reading that makes the middle mean something: a fully linked row leaves
confirmed demand exactly as `placed` did, and a row linked 5 of 8 leaves 3.

Two smaller changes ride with it, both from part 2 section 4b.

`ORDER_BACK` joins `ORDER` in the leg: an order back is still demand until it is linked, and
counting only ORDER would have made the verb invisible to the plan the moment section 3.I
made it linkable.

It is counted at the DONOR's location. An order-back row hangs off the BORROWING line
(`project_order_inquiry_service._raise_borrow_shortfalls`), so the core line's warehouse is
not where the hole is; the row's own `stock_location` is, and it names the donor. Reading
`sol.warehouse_id` for it would have put the shortfall in a warehouse that never had one -
the exact mis-attribution the verb was created to avoid. Measured on the dev copy: 0 rows
carry the verb today, so this changes no live number and is correct for the first one.

The body is FROZEN in this file rather than imported from
`app.services.scm.demand.COMMITTED_V_SQL`, and the body it replaces is frozen beside it for
the downgrade - the rule `tests/scm/test_committed_v_migration_chain.py` holds, and the one
whose breach killed production's first replay of the SCM chain at migration 340.

`CREATE OR REPLACE` is legal here: same columns, same order, same names. Only the leg's
predicates and its arithmetic move.
"""
from alembic import op

revision = "422_committed_v_link_netting"
down_revision = "421_order_inquiry_links"
branch_labels = None
#: The revision whose body this one replaces. Already an ancestor on this chain; the pin
#: says so out loud so a rebase that reorders the SCM lanes cannot land this view
#: underneath the one it supersedes.
depends_on = "384_committed_v_line_decision"


_AS_OF_422 = """
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
    -- product and fulfilment location, LESS whatever of it now sits on a document
    -- (PLAN-scm-cs-planning-uat.md section 3.I). Never matched on provisional_ref,
    -- autocount_doc_no or item code (plan 4).
    --
    -- Netted per ROW rather than tested per STATE. Before `order_inquiry_links` a row was
    -- all or nothing - `raised` counted the whole quantity, `placed` counted none - so a
    -- cascade that could only cover part of a row had to SPLIT the row for the arithmetic
    -- to come out, which is how nine sales-order lines became eleven instructions. A fully
    -- linked row now leaves confirmed demand exactly as `placed` did, and a half-linked
    -- one leaves half of it.
    --
    -- ORDER_BACK counts here too (PLAN-scm-purchasing-uat-journey.md section 4b): it is
    -- still demand until it is linked. At the DONOR's location, which is what the row's
    -- own `stock_location` names: the row hangs off the BORROWING line, so reading the
    -- core line's warehouse would put the hole in a warehouse that never had one.
    SELECT sol.product_id,
           CASE WHEN oir.verb = 'ORDER_BACK'
                THEN COALESCE(donor.id, sol.warehouse_id)
                ELSE sol.warehouse_id END AS warehouse_id,
           GREATEST(oir.qty - COALESCE(lk.linked, 0), 0) AS project_qty,
           GREATEST(oir.qty - COALESCE(lk.linked, 0), 0) AS project_confirmed_qty,
           0 AS retail_qty,
           0 AS unclassified_qty
    FROM projects.order_inquiry_rows oir
    JOIN projects.so_supply_decisions d
      ON d.id = oir.supply_decision_id
     AND d.state = 'active'
    JOIN projects.sales_order_lines psl ON psl.id = oir.so_line_id
    JOIN sales_order_lines sol ON sol.id = psl.core_sales_order_line_id
    LEFT JOIN warehouses donor ON donor.warehouse_code = oir.stock_location
    LEFT JOIN LATERAL (
        SELECT COALESCE(SUM(l.qty), 0) AS linked
        FROM projects.order_inquiry_links l
        WHERE l.row_id = oir.id
    ) lk ON TRUE
    WHERE oir.verb IN ('ORDER', 'ORDER_BACK')
      AND oir.state IN ('raised', 'partly_linked')
      AND oir.qty > 0
      AND oir.qty > COALESCE(lk.linked, 0)
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

# The body as migration `384_committed_v_line_decision` left it, for the downgrade. A
# verbatim copy of that revision's own `_AS_OF_384`, pinned equal by
# `tests/scm/test_committed_v_migration_chain.py` so the two cannot drift.
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


def upgrade() -> None:
    op.execute(_AS_OF_422)


def downgrade() -> None:
    op.execute(_AS_OF_384)
