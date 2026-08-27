"""The form leg stops double counting a retail line the book already counts

Revision ID: 426_committed_v_form_leg_scope
Revises: 425_sales_orders_class_backfill
Create Date: 2026-08-26 22:00:00.000000

Review finding on P3 (`PLAN-scm-purchasing-uat-journey.md`), and a defect 424 opened.

424 dropped `so_line_id IS NULL` from the FORM leg, correctly: it only ever de-duplicated
against the SHEET leg, and with that leg retired the condition would have deleted the
ORDER BACK rows the CS form raises against a book line. What it did not do is put the other
half back. The book leg still speaks for the RETAIL channel, so a decision-less inquiry row
naming a retail line was counted twice from 424 onwards - once as the sales-order line, and
once as the row.

So the form leg now excludes exactly the rows whose line the BOOK leg counts: same class
test, same four openness conditions, phrased as a `NOT EXISTS` over the reconciled core
line. Phrased that way round on purpose. "The line is project-class" would have been the
shorter test and the wrong one: a row whose line is unreconciled, closed or fully delivered
is counted by nothing else at all, and a class test alone would drop it out of planning.

Measured on the dev copy before applying: every open inquiry row carries a supply decision,
so no row reaches the form leg today and this moves no live number. It is the shape of the
next CS form upload that it fixes.

The body is FROZEN here rather than imported from `app.services.scm.demand.COMMITTED_V_SQL`
(`tests/scm/test_committed_v_migration_chain.py`), and 424's body is frozen beside it for
the downgrade. 424 is NOT edited: it has been applied to the dev copy, and a migration
describes a point in history whether or not that history was short.

`CREATE OR REPLACE` is legal: same columns, same order, same names, same types - every
constant leg column keeps the `0::numeric` cast 424 needed to apply at all.
"""
from alembic import op

revision = "426_committed_v_form_leg_scope"
down_revision = "425_sales_orders_class_backfill"
branch_labels = None
#: The revision whose body this one replaces.
depends_on = "424_committed_v_project_oi_only"


_AS_OF_426 = """CREATE OR REPLACE VIEW scm.committed_v AS
WITH legs AS (
    -- The BOOK leg, and it is the RETAIL channel entire (P3). A project-class line is
    -- never demand as a book line: it becomes demand when CS raises an Order Inquiry
    -- ORDER row for it, which the confirmed and form legs below count, and it stops being
    -- demand when that row is linked. A NULL class reads as retail - the book-direct
    -- channel - because nothing is unclassified any more (P4).
    SELECT sol.product_id,
           sol.warehouse_id,
           0::numeric AS project_qty,
           0::numeric AS project_confirmed_qty,
           GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
                  - COALESCE(sol.qty_delivered, 0), 0) AS retail_qty,
           0::numeric AS unclassified_qty
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
           0::numeric AS retail_qty,
           0::numeric AS unclassified_qty
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
    -- `supply_decision_id IS NULL` keeps this leg disjoint from the CONFIRMED leg above:
    -- a row a CS decision points at is counted there, at the core line's product and
    -- location, and every OTHER raised row is counted here at its own. The leg used to
    -- demand `so_line_id IS NULL` as well, because a row naming a book line was already
    -- counted by the SHEET leg; P3 retired that leg, and the condition would now DELETE
    -- such a row from planning instead of de-duplicating it - the form raises ORDER BACK
    -- rows carrying an `so_line_id` (`project_order_inquiry_import_service`), and they are
    -- demand like any other.
    --
    -- The `NOT EXISTS` below keeps it disjoint from the BOOK leg, which is the other half
    -- of the same worry and the half P3 opened: the book still speaks for retail, so a
    -- decision-less row naming a RETAIL line would be counted twice, once as the line and
    -- once as the row. Stated as "the book leg does not count this line" - the same four
    -- openness conditions the book leg applies, plus its class test - rather than as "the
    -- line is project": a row whose line is unreconciled, closed or fully delivered is
    -- counted by nothing else, and a class test alone would drop it.
    SELECT fp.id AS product_id,
           fw.id AS warehouse_id,
           GREATEST(oir.qty - COALESCE(flk.linked, 0), 0) AS project_qty,
           GREATEST(oir.qty - COALESCE(flk.linked, 0), 0) AS project_confirmed_qty,
           0::numeric AS retail_qty,
           0::numeric AS unclassified_qty
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
      AND NOT EXISTS (
          SELECT 1
          FROM projects.sales_order_lines fpsl
          JOIN sales_order_lines fsol ON fsol.id = fpsl.core_sales_order_line_id
          JOIN sales_orders fso ON fso.id = fsol.sales_order_id
          WHERE fpsl.id = oir.so_line_id
            AND fso.demand_class IS DISTINCT FROM 'project'
            AND fso.status = 'open'
            AND fsol.line_status = 'open'
            AND fsol.purchasing_status <> 'covered'
            AND GREATEST(COALESCE(fsol.qty_required, fsol.qty_ordered)
                       - COALESCE(fsol.qty_delivered, 0), 0) > 0)
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


_AS_OF_424 = """CREATE OR REPLACE VIEW scm.committed_v AS
WITH legs AS (
    -- The BOOK leg, and it is the RETAIL channel entire (P3). A project-class line is
    -- never demand as a book line: it becomes demand when CS raises an Order Inquiry
    -- ORDER row for it, which the confirmed and form legs below count, and it stops being
    -- demand when that row is linked. A NULL class reads as retail - the book-direct
    -- channel - because nothing is unclassified any more (P4).
    SELECT sol.product_id,
           sol.warehouse_id,
           0::numeric AS project_qty,
           0::numeric AS project_confirmed_qty,
           GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
                  - COALESCE(sol.qty_delivered, 0), 0) AS retail_qty,
           0::numeric AS unclassified_qty
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
           0::numeric AS retail_qty,
           0::numeric AS unclassified_qty
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
           0::numeric AS retail_qty,
           0::numeric AS unclassified_qty
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

def upgrade() -> None:
    op.execute(_AS_OF_426)


def downgrade() -> None:
    op.execute(_AS_OF_424)
