"""`scm.committed_v` counts an instruction the Order Inquiry Form raised with no SO line

Revision ID: 423_committed_v_form_rows
Revises: 422_committed_v_link_netting
Create Date: 2026-08-26 17:00:00.000000

`PLAN-scm-cs-planning-uat.md` section 3.I, AC-I3. Fourteen rows of SO381895's first two CS
forms are marked `[NL]` on `scm-cs-planning-uat-fixture.md`: CS writes `ORDER BACK` where a
delivery DATE belongs, and the sales-order lines those quantities came from were CLOSED in
AutoCount. The fulfilment board has nothing to decide about them, so the only writer that can
raise them is the form upload itself - and the row it writes has no `so_line_id` and no
supply decision, which is exactly what both existing confirmed legs join on.

So the instruction was raised, shown to purchasing, and invisible to the plan that decides
what to buy. This adds the leg that reads the ROW's own `item_code` and `stock_location`
instead of a line's.

Joined on the code AND the company together - what `uq_products_company_product_code` and
`uq_warehouses_company_warehouse_code` make unique - so a SKU two companies both hold cannot
multiply the row. INNER on both, so an item or a location this system does not hold is
counted nowhere rather than everywhere. `supply_decision_id IS NULL` keeps this leg and the
decision's own disjoint.

Measured on the dev copy before the change: 0 rows carry `so_line_id IS NULL`, so this moves
no live number and is correct for the first one.

The body is FROZEN here rather than imported from `app.services.scm.demand.COMMITTED_V_SQL`,
and the body it replaces is frozen beside it for the downgrade - the rule
`tests/scm/test_committed_v_migration_chain.py` holds, and the one whose breach killed
production's first replay of the SCM chain at migration 340.

`CREATE OR REPLACE` is legal: same columns, same order, same names. Only a UNION leg is
added inside the CTE.
"""
from alembic import op

revision = "423_committed_v_form_rows"
down_revision = "422_committed_v_link_netting"
branch_labels = None
#: The revision whose body this one replaces. Already an ancestor on this chain; the pin
#: says so out loud so a rebase that reorders the SCM lanes cannot land this view
#: underneath the one it supersedes.
depends_on = "422_committed_v_link_netting"


_AS_OF_423 = """
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
    UNION ALL
    -- The FORM leg: an instruction the CS Order Inquiry Form raised that the sales-order
    -- book carries no line for (`PLAN-scm-cs-planning-uat.md` section 3.I; the fixture
    -- sheet's `[NL]` rows). CS writes `ORDER BACK` where a delivery date belongs and the
    -- line that quantity came from was closed in AutoCount, so there is no `so_line_id` to
    -- read a product or a warehouse off - the ROW states both, and those are what this leg
    -- reads. Without it the fourteen instructions on SO381895's first two forms are raised,
    -- shown to purchasing, and invisible to the plan that decides what to buy.
    --
    -- Joined on the CODE and the company together, which is exactly what
    -- `uq_products_company_product_code` / `uq_warehouses_company_warehouse_code` make
    -- unique - a code alone would multiply the row once per company holding the same SKU.
    -- INNER on both, so a row naming an item or a location this system does not hold is
    -- counted nowhere rather than everywhere.
    --
    -- `supply_decision_id IS NULL` keeps the two confirmed legs disjoint: a decision's own
    -- Buy residual is counted above, at the reconciled core line's product and location.
    SELECT fp.id AS product_id,
           fw.id AS warehouse_id,
           GREATEST(oir.qty - COALESCE(flk.linked, 0), 0) AS project_qty,
           GREATEST(oir.qty - COALESCE(flk.linked, 0), 0) AS project_confirmed_qty,
           0 AS retail_qty,
           0 AS unclassified_qty
    FROM projects.order_inquiry_rows oir
    JOIN products fp
      ON fp.product_code = oir.item_code
     AND fp.company_id = oir.company_id
    JOIN warehouses fw
      ON fw.warehouse_code = oir.stock_location
     AND fw.company_id = oir.company_id
    LEFT JOIN LATERAL (
        SELECT COALESCE(SUM(l.qty), 0) AS linked
        FROM projects.order_inquiry_links l
        WHERE l.row_id = oir.id
    ) flk ON TRUE
    WHERE oir.so_line_id IS NULL
      AND oir.supply_decision_id IS NULL
      AND oir.verb IN ('ORDER', 'ORDER_BACK')
      AND oir.state IN ('raised', 'partly_linked')
      AND oir.qty > 0
      AND oir.qty > COALESCE(flk.linked, 0)
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

# The body as migration `422_committed_v_link_netting` left it, for the downgrade. A
# verbatim copy of that revision's own `_AS_OF_422`, pinned equal by
# `tests/scm/test_committed_v_migration_chain.py` so the two cannot drift.
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


def upgrade() -> None:
    op.execute(_AS_OF_423)


def downgrade() -> None:
    op.execute(_AS_OF_422)
