"""Project demand is the Order Inquiry alone: `scm.committed_v` loses its SHEET leg

Revision ID: 424_committed_v_project_oi_only
Revises: 423_committed_v_form_rows
Create Date: 2026-08-26 20:00:00.000000

`PLAN-scm-purchasing-uat-journey.md` P3 (captain, 26 Aug 2026). The plan row for M310-CR-PJ
showed 16 units of Project demand at BRW-BB on runs b805ba89 and 93305b25 while every Order
Inquiry row for that item was already placed, and MSK11B showed 243 at BRW-IB against two
inquiry rows totalling 26. Both figures came from the same place: the SHEET leg, which
counted the open lines of any `demand_origin = 'scm_order_inquiry'` order (the old Joey
feed) that no active CS decision covered. Those orders arrived months ago and nobody has
confirmed them on the fulfilment board.

So the sheet leg goes. Project demand is now the Order Inquiry and nothing else - the
un-linked remainder of raised ORDER / ORDER BACK rows - and a sheet-origin project order
with no decision is AWAITING CS, reported by `demand_source_service.set_aside_project_demand`
rather than netted. The book leg that remains is the retail channel entire.

Three consequences inside the body:

* `project_qty` on the book leg becomes a constant 0, so the `decided` CTE has nothing left
  to exclude and goes with it. `project_committed` and `project_confirmed_committed` are
  therefore equal on every row from here on.
* `unclassified_qty` becomes a constant 0 and a NULL `demand_class` counts as RETAIL (P4).
  Migration 425 stamps the NULLs and the SO import refuses a file that would make another,
  so nothing is unclassified; reading a stray NULL as the book-direct channel is truer than
  a fourth column nobody can act on. The COLUMN stays because `CREATE OR REPLACE VIEW` may
  only append columns, and dropping it would mean rebuilding `scm.net_position_v` and
  everything beneath it for a figure that is always 0.
* the FORM leg loses its `so_line_id IS NULL` condition. That condition existed to stop the
  leg double counting a row the SHEET leg already counted through its sales-order line;
  with the sheet leg gone it would instead DELETE such a row from planning, and the Order
  Inquiry Form does raise ORDER BACK rows carrying an `so_line_id`. `supply_decision_id IS
  NULL` alone keeps the form leg disjoint from the confirmed leg.

Measured on the dev copy before applying: 13 open inquiry rows, every one of them carrying
both an `so_line_id` and a supply decision, so the form leg's widened condition moves no
live number today. The sheet leg's removal is what moves: 148 open project-class orders
stop contributing book demand.

The body is FROZEN here rather than imported from `app.services.scm.demand.COMMITTED_V_SQL`,
and the body it replaces is frozen beside it for the downgrade - the rule
`tests/scm/test_committed_v_migration_chain.py` holds, and the one whose breach killed
production's first replay of the SCM chain at migration 340.

`CREATE OR REPLACE` is legal: same columns, same order, same names. Only leg predicates
change inside the CTE.
"""
from alembic import op

revision = "424_committed_v_project_oi_only"
down_revision = "423_committed_v_form_rows"
branch_labels = None
#: The revision whose body this one replaces. Already an ancestor on this chain; the pin
#: says so out loud so a rebase that reorders the SCM lanes cannot land this view
#: underneath the one it supersedes.
depends_on = "423_committed_v_form_rows"


_AS_OF_424 = """CREATE OR REPLACE VIEW scm.committed_v AS
WITH legs AS (
    -- The BOOK leg, and it is the RETAIL channel entire (P3). A project-class line is
    -- never demand as a book line: it becomes demand when CS raises an Order Inquiry
    -- ORDER row for it, which the confirmed and form legs below count, and it stops being
    -- demand when that row is linked. A NULL class reads as retail - the book-direct
    -- channel - because nothing is unclassified any more (P4).
    SELECT sol.product_id,
           sol.warehouse_id,
           0 AS project_qty,
           0 AS project_confirmed_qty,
           GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
                  - COALESCE(sol.qty_delivered, 0), 0) AS retail_qty,
           0 AS unclassified_qty
    FROM sales_order_lines sol
    JOIN sales_orders so ON so.id = sol.sales_order_id
    WHERE so.status = 'open'
      AND sol.line_status = 'open'
      AND sol.purchasing_status <> 'covered'
      AND GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
                 - COALESCE(sol.qty_delivered, 0), 0) > 0
      AND so.demand_class IS DISTINCT FROM 'project'
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
    -- The FORM leg: an instruction the CS Order Inquiry Form raised that no supply decision
    -- points at (`PLAN-scm-cs-planning-uat.md` section 3.I; the fixture sheet's `[NL]`
    -- rows). CS writes `ORDER BACK` where a delivery date belongs, and the form is the only
    -- writer that can raise it - the fulfilment board has nothing to decide about a line
    -- AutoCount has closed. The ROW states its own item and location, and those are what
    -- this leg reads, whether or not it also names a sales-order line. Without it the
    -- fourteen instructions on SO381895's first two forms are raised, shown to purchasing,
    -- and invisible to the plan that decides what to buy.
    --
    -- Joined on the CODE and the company together, which is exactly what
    -- `uq_products_company_product_code` / `uq_warehouses_company_warehouse_code` make
    -- unique - a code alone would multiply the row once per company holding the same SKU.
    --
    -- INNER on `products`, because a row naming an item this system does not hold is demand
    -- for nothing and there is no product to attribute it to. LEFT on `warehouses`, because
    -- a row that names no location, or one we do not hold, is still demand - it comes out
    -- with a NULL warehouse, which every reader joins on `(product, warehouse)` and so
    -- matches nowhere. Counted at no location rather than invented at one, and visible in
    -- the view rather than dropped from it.
    --
    -- `supply_decision_id IS NULL` is the whole guard, and it is what keeps this leg
    -- disjoint from the confirmed leg above: a row a CS decision points at is counted
    -- there, at the core line's product and location, and every OTHER raised row is
    -- counted here at its own. The leg used to demand `so_line_id IS NULL` as well,
    -- because a row naming a book line was already counted by the SHEET leg. P3 retired
    -- that leg, so the extra condition would now DELETE such a row from planning instead
    -- of de-duplicating it - the form raises ORDER BACK rows carrying an `so_line_id`
    -- (`project_order_inquiry_import_service`), and they are demand like any other.
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
    LEFT JOIN warehouses fw
      ON fw.warehouse_code = oir.stock_location
     AND fw.company_id = oir.company_id
    LEFT JOIN LATERAL (
        SELECT COALESCE(SUM(l.qty), 0) AS linked
        FROM projects.order_inquiry_links l
        WHERE l.row_id = oir.id
    ) flk ON TRUE
    WHERE oir.supply_decision_id IS NULL
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
    --
    -- INNER on `products`, because a row naming an item this system does not hold is demand
    -- for nothing and there is no product to attribute it to. LEFT on `warehouses`, because
    -- a row that names no location, or one we do not hold, is still demand - it comes out
    -- with a NULL warehouse, which every reader joins on `(product, warehouse)` and so
    -- matches nowhere. Counted at no location rather than invented at one, and visible in
    -- the view rather than dropped from it.
    --
    -- `so_line_id IS NULL` is what stops this leg double counting. A row raised against a
    -- line the book DOES carry is already counted by the sheet leg above, at that line's own
    -- product and warehouse; adding the row on top would have the planner buy the same
    -- quantity twice. `supply_decision_id IS NULL` keeps it disjoint from the confirmed leg
    -- for the same reason.
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
    LEFT JOIN warehouses fw
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


def upgrade() -> None:
    op.execute(_AS_OF_424)


def downgrade() -> None:
    op.execute(_AS_OF_423)
