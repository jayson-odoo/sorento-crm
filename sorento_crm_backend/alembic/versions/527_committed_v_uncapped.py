"""`scm.committed_v` never caps an ORDER row's owed quantity at its line's outstanding

Revision ID: 527_committed_v_uncapped
Revises: oirs_0002_reserve_round2
Create Date: 2026-09-23 00:00:00.000000

Owner ruling R1, 23 Sep 2026 (`PLAN-oi-order-rows-uncapped.md`, SO421985): "this is
delivered already and we want to replenish, I don't mind order back or order, as long as
it needs to order". SO421985 raised three ORDER rows of 493 on 18 Sep; the AutoCount pull
on 21 Sep then marked the three lines delivered 493/493 and closed the order, and Start
Plan (Demand = Project) stopped listing it while the OI detail still read Remaining 493 -
a raised, unlinked ORDER row is buy demand until purchasing links it, whatever the line's
own delivered column says. This retires the 7.3 / 14 Sep cap (SO368872 / SRTWC286-SH, "Buy
never exceeds what the line still owes") for the ORDER verb too - 525 had already retired
it for ORDER_BACK - so both project legs' owed-quantity expression
(`app.services.scm.demand._OWED_SQL` / `_OWED_FORM_SQL`) collapses to `oir.qty -
COALESCE(linked, 0) - oir.bundled_qty`, floored at zero, for every verb. Known
consequence, taken deliberately: the SO368872 shape now buys the row quantity again.

The body is FROZEN here rather than imported from `app.services.scm.demand.
COMMITTED_V_SQL` (`tests/scm/test_committed_v_migration_chain.py`'s own drift guard), and
525's body is frozen beside it for the downgrade. `CREATE OR REPLACE` is legal: same
columns, same order, same names, only the two project legs' owed-quantity CASE expressions
collapse to the same uncapped `GREATEST` every leg already used for a row on no core line.
"""
from alembic import op

revision = "527_committed_v_uncapped"
#: Chains onto the actual current head, not onto `525_committed_v_orderback` directly -
#: `526_chatbot_media_attach_type`, `bftp_0001_flows_to_purchasing`,
#: `oirs_0001_reserve_requests` and `oirs_0002_reserve_round2` sit between them and touch
#: no view, so none of them is a link in the `test_committed_v_migration_chain.py` replay
#: chain, but `down_revision` still has to name the real single head.
down_revision = "oirs_0002_reserve_round2"
branch_labels = None
depends_on = None


_AS_OF_527 = """
CREATE OR REPLACE VIEW scm.committed_v AS
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
           GREATEST(oir.qty - COALESCE(lk.linked, 0) - oir.bundled_qty, 0) AS project_qty,
           GREATEST(oir.qty - COALESCE(lk.linked, 0) - oir.bundled_qty, 0) AS project_confirmed_qty,
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
      AND oir.redirected_to_pool = FALSE
      AND oir.ack_state <> 'rejected'
      AND oir.qty > 0
      -- PLAN-scm-supplied-with-companions.md ruling 6: a bundled unit never reaches
      -- reorder planning, whatever the item it rides with is covered by. R1 (23 Sep):
      -- otherwise uncapped, so the leg drops a row only once it is fully linked/bundled.
      AND GREATEST(oir.qty - COALESCE(lk.linked, 0) - oir.bundled_qty, 0) > 0
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
           GREATEST(oir.qty - COALESCE(flk.linked, 0) - oir.bundled_qty, 0) AS project_qty,
           GREATEST(oir.qty - COALESCE(flk.linked, 0) - oir.bundled_qty, 0) AS project_confirmed_qty,
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
      AND oir.redirected_to_pool = FALSE
      AND oir.ack_state <> 'rejected'
      AND oir.qty > 0
      -- Ruling 6, form leg: the same "never reaches reorder planning" rule. R1 (23
      -- Sep): uncapped, same as the confirmed leg.
      AND GREATEST(oir.qty - COALESCE(flk.linked, 0) - oir.bundled_qty, 0) > 0
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


_AS_OF_525 = """
CREATE OR REPLACE VIEW scm.committed_v AS
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
           GREATEST((CASE WHEN oir.verb = 'ORDER_BACK' THEN oir.qty
              ELSE LEAST(oir.qty, GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
       - COALESCE(sol.qty_delivered, 0), 0)) END)
       - COALESCE(lk.linked, 0) - oir.bundled_qty, 0) AS project_qty,
           GREATEST((CASE WHEN oir.verb = 'ORDER_BACK' THEN oir.qty
              ELSE LEAST(oir.qty, GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
       - COALESCE(sol.qty_delivered, 0), 0)) END)
       - COALESCE(lk.linked, 0) - oir.bundled_qty, 0) AS project_confirmed_qty,
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
      AND oir.redirected_to_pool = FALSE
      AND oir.ack_state <> 'rejected'
      AND oir.qty > 0
      -- PLAN-scm-supplied-with-companions.md ruling 6: a bundled unit never reaches
      -- reorder planning, whatever the item it rides with is covered by. And 7.3: a row
      -- whose line owes nothing more is not owed either, so the leg drops it.
      AND GREATEST((CASE WHEN oir.verb = 'ORDER_BACK' THEN oir.qty
              ELSE LEAST(oir.qty, GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
       - COALESCE(sol.qty_delivered, 0), 0)) END)
       - COALESCE(lk.linked, 0) - oir.bundled_qty, 0) > 0
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
           GREATEST(CASE WHEN oir.verb = 'ORDER_BACK' THEN oir.qty
              WHEN csol.id IS NULL THEN oir.qty
              ELSE LEAST(oir.qty,
                         GREATEST(COALESCE(csol.qty_required, csol.qty_ordered)
                                - COALESCE(csol.qty_delivered, 0), 0)) END
       - COALESCE(flk.linked, 0) - oir.bundled_qty, 0) AS project_qty,
           GREATEST(CASE WHEN oir.verb = 'ORDER_BACK' THEN oir.qty
              WHEN csol.id IS NULL THEN oir.qty
              ELSE LEAST(oir.qty,
                         GREATEST(COALESCE(csol.qty_required, csol.qty_ordered)
                                - COALESCE(csol.qty_delivered, 0), 0)) END
       - COALESCE(flk.linked, 0) - oir.bundled_qty, 0) AS project_confirmed_qty,
           0::numeric AS retail_qty,
           0::numeric AS unclassified_qty
    FROM projects.order_inquiry_rows oir
    JOIN products fp
      ON fp.product_code = oir.item_code
     AND fp.company_id = oir.company_id
    LEFT JOIN warehouses fw
      ON fw.warehouse_code = oir.stock_location
     AND fw.company_id = oir.company_id
    LEFT JOIN projects.sales_order_lines cpsl ON cpsl.id = oir.so_line_id
    LEFT JOIN sales_order_lines csol ON csol.id = cpsl.core_sales_order_line_id
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
      AND oir.redirected_to_pool = FALSE
      AND oir.ack_state <> 'rejected'
      AND oir.qty > 0
      -- Ruling 6, form leg: the same "never reaches reorder planning" rule. No 7.3 cap
      -- here: this leg matches on item code for rows no supply decision points at, so
      -- there is no core sales order line in scope to owe anything.
      AND GREATEST(CASE WHEN oir.verb = 'ORDER_BACK' THEN oir.qty
              WHEN csol.id IS NULL THEN oir.qty
              ELSE LEAST(oir.qty,
                         GREATEST(COALESCE(csol.qty_required, csol.qty_ordered)
                                - COALESCE(csol.qty_delivered, 0), 0)) END
       - COALESCE(flk.linked, 0) - oir.bundled_qty, 0) > 0
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
    op.execute(_AS_OF_527)


def downgrade() -> None:
    op.execute(_AS_OF_525)
