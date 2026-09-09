"""`scm.committed_v` subtracts a bundled row's `bundled_qty`

Revision ID: 496_committed_v_bundled_qty
Revises: 495_product_companion_rules
Create Date: 2026-09-09 00:00:00.000000

PLAN-scm-supplied-with-companions.md ruling 6: a bundled quantity never reaches reorder
planning, whatever the item it rides with is covered by - only the ala carte remainder
does. The confirmed and form legs both change from `qty - linked` to
`qty - linked - bundled_qty`, in the quantity column and in the "is this row still
owed" predicate that gates whether the leg counts it at all.

The body is FROZEN here rather than imported from `app.services.scm.demand.
COMMITTED_V_SQL` (`test_committed_v_migration_chain.py`'s own drift guard), and the body
it replaces (`428_order_inquiry_ack_state`'s `_AS_OF_428`) is frozen beside it for the
downgrade. `CREATE OR REPLACE` is legal here: same columns, same order, same names -
only the two project legs' arithmetic changes.
"""
from alembic import op

revision = "496_committed_v_bundled_qty"
down_revision = "495_product_companion_rules"
branch_labels = None
depends_on = "495_product_companion_rules"


_AS_OF_496 = """
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
    -- (PLAN-scm-cs-planning-uat.md section 3.I), LESS a "supplied with" bundle
    -- (PLAN-scm-supplied-with-companions.md ruling 6). Never matched on provisional_ref,
    -- autocount_doc_no or item code (plan 4).
    SELECT sol.product_id,
           CASE WHEN oir.verb = 'ORDER_BACK'
                THEN COALESCE(donor.id, sol.warehouse_id)
                ELSE sol.warehouse_id END AS warehouse_id,
           GREATEST(oir.qty - COALESCE(lk.linked, 0) - oir.bundled_qty, 0) AS project_qty,
           GREATEST(oir.qty - COALESCE(lk.linked, 0) - oir.bundled_qty, 0)
               AS project_confirmed_qty,
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
      AND oir.ack_state <> 'rejected'
      AND oir.qty > 0
      AND oir.qty > COALESCE(lk.linked, 0) + oir.bundled_qty
    UNION ALL
    -- The FORM leg: an instruction the CS Order Inquiry Form raised that no supply decision
    -- points at (`PLAN-scm-cs-planning-uat.md` section 3.I; the fixture sheet's `[NL]`
    -- rows). Same bundled-quantity subtraction as the confirmed leg above.
    SELECT fp.id AS product_id,
           fw.id AS warehouse_id,
           GREATEST(oir.qty - COALESCE(flk.linked, 0) - oir.bundled_qty, 0) AS project_qty,
           GREATEST(oir.qty - COALESCE(flk.linked, 0) - oir.bundled_qty, 0)
               AS project_confirmed_qty,
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
      AND oir.ack_state <> 'rejected'
      AND oir.qty > 0
      AND oir.qty > COALESCE(flk.linked, 0) + oir.bundled_qty
)
SELECT product_id,
       warehouse_id,
       SUM(project_qty + retail_qty + unclassified_qty) AS committed,
       SUM(project_qty) AS project_committed,
       SUM(retail_qty) AS retail_committed,
       SUM(unclassified_qty) AS unclassified_committed,
       SUM(project_confirmed_qty) AS project_confirmed_committed
FROM legs
GROUP BY product_id, warehouse_id;
"""


_AS_OF_428 = """
CREATE OR REPLACE VIEW scm.committed_v AS
WITH legs AS (
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
      AND oir.ack_state <> 'rejected'
      AND oir.qty > 0
      AND oir.qty > COALESCE(lk.linked, 0)
    UNION ALL
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
      AND oir.ack_state <> 'rejected'
      AND oir.qty > 0
      AND oir.qty > COALESCE(flk.linked, 0)
)
SELECT product_id,
       warehouse_id,
       SUM(project_qty + retail_qty + unclassified_qty) AS committed,
       SUM(project_qty) AS project_committed,
       SUM(retail_qty) AS retail_committed,
       SUM(unclassified_qty) AS unclassified_committed,
       SUM(project_confirmed_qty) AS project_confirmed_committed
FROM legs
GROUP BY product_id, warehouse_id;
"""


def upgrade() -> None:
    op.execute(_AS_OF_496)


def downgrade() -> None:
    op.execute(_AS_OF_428)
