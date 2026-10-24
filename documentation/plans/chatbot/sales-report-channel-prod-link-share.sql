-- SALES-REPORT-CHANNEL, owner question Q1: how much of 2026's delivered DO-line qty can reach a sales order?
-- READ ONLY. Run on the CRM database (psql). Changes nothing: the whole run is one read-only transaction,
-- rolled back at the end. Prints no names: one row per month of 2026, quantities only, all companies together.
--
-- Rows counted = the chatbot sales report's own rows (app/services/reports/datasets/delivery_order_lines.py:65-68):
-- DO not cancelled, not deleted, dated, number not starting with REP.
--
-- Tables and columns read (model file:line, sorento_crm_backend/app/models/order.py):
--   orders              (:419)  id (:422), order_number (:427), order_date (:428), is_cancelled (:442),
--                               deleted_at (:465), source_book (:472, NULL = old-system DO), sales_order_id (:487)
--   order_lines         (:535)  order_id (:541), quantity (:556), sales_order_line_id (:567),
--                               from_doc_type (:590), from_doc_no (:591),
--                               company_id (CompanyScopedMixin, app/models/base.py:141)
--   sales_order_lines   (:751)  id (:755), sales_order_id (:756)
--   sales_orders        (:631)  id (:634), so_number (:640), demand_class (:668),
--                               company_id (CompanyScopedMixin, app/models/base.py:141)
--
-- The three link paths, each line counted under the FIRST one that finds a sales order:
--   1 line link    order_lines.sales_order_line_id -> sales_order_lines.sales_order_id -> sales_orders
--   2 header link  orders.sales_order_id -> sales_orders
--   3 doc number   order_lines.from_doc_type = 'SO' and from_doc_no = sales_orders.so_number, same company
-- qty_no_so = none of the three finds one (split: old-system DOs vs AutoCount DOs).
-- qty_so_no_type = found a sales order, but that order carries no demand_class (Dealer / Project).

BEGIN TRANSACTION READ ONLY;

WITH do_line AS (
    SELECT
        to_char(o.order_date, 'YYYY-MM') AS month,
        o.source_book IS NULL AS old_system_do,
        ol.quantity AS qty,
        so_line.id AS so_by_line,
        so_head.id AS so_by_header,
        so_doc.id AS so_by_doc,
        COALESCE(so_line.demand_class, so_head.demand_class, so_doc.demand_class) AS so_type
    FROM order_lines ol
    JOIN orders o ON o.id = ol.order_id
    LEFT JOIN sales_order_lines sl ON sl.id = ol.sales_order_line_id
    LEFT JOIN sales_orders so_line ON so_line.id = sl.sales_order_id
    LEFT JOIN sales_orders so_head ON so_head.id = o.sales_order_id
    LEFT JOIN LATERAL (
        SELECT s.id, s.demand_class
        FROM sales_orders s
        WHERE ol.from_doc_type = 'SO'
          AND s.so_number = ol.from_doc_no
          AND s.company_id = ol.company_id
        ORDER BY s.id
        LIMIT 1
    ) so_doc ON TRUE
    WHERE o.is_cancelled IS FALSE
      AND o.deleted_at IS NULL
      AND o.order_date IS NOT NULL
      AND o.order_number NOT LIKE 'REP%'
      AND o.order_date >= DATE '2026-01-01'
      AND o.order_date < DATE '2027-01-01'
)
SELECT
    month,
    SUM(qty)::bigint AS do_line_qty_total,
    COALESCE(SUM(qty) FILTER (WHERE so_by_line IS NOT NULL), 0)::bigint AS qty_by_line_link,
    COALESCE(SUM(qty) FILTER (WHERE so_by_line IS NULL AND so_by_header IS NOT NULL), 0)::bigint AS qty_by_header_link,
    COALESCE(SUM(qty) FILTER (WHERE so_by_line IS NULL AND so_by_header IS NULL AND so_by_doc IS NOT NULL), 0)::bigint
        AS qty_by_doc_number,
    COALESCE(SUM(qty) FILTER (WHERE COALESCE(so_by_line, so_by_header, so_by_doc) IS NULL), 0)::bigint AS qty_no_so,
    COALESCE(SUM(qty) FILTER (WHERE COALESCE(so_by_line, so_by_header, so_by_doc) IS NULL AND old_system_do), 0)::bigint
        AS qty_no_so_old_system_do,
    COALESCE(SUM(qty) FILTER (WHERE COALESCE(so_by_line, so_by_header, so_by_doc) IS NULL AND NOT old_system_do), 0)::bigint
        AS qty_no_so_autocount_do,
    COALESCE(SUM(qty) FILTER (WHERE COALESCE(so_by_line, so_by_header, so_by_doc) IS NOT NULL AND so_type IS NULL), 0)::bigint
        AS qty_so_no_type,
    ROUND(100.0 * COALESCE(SUM(qty) FILTER (WHERE COALESCE(so_by_line, so_by_header, so_by_doc) IS NULL), 0)
          / NULLIF(SUM(qty), 0), 1) AS pct_no_so
FROM do_line
GROUP BY month
ORDER BY month;

ROLLBACK;
