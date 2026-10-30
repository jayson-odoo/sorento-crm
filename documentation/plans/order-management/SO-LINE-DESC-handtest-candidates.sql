-- SO-LINE-DESC: read-only pick of real hand-test lines (crew runs; the lane cannot read rows).
-- Wants RPACC / RPAC lines on PROJECT sales orders (so they show on Fulfilment Planning and can go
-- out in an OI email) whose AutoCount text is already in the CRM on a linked delivery order line
-- (the hand-test seed in crew/state/migrations/SO-LINE-DESC.sql block 3 copies exactly that text).
-- No customer columns.
BEGIN READ ONLY;

-- 1. Project SO lines with a DO-borne description, with their latest OI row if any.
SELECT so.so_number,
       psol.line_no                       AS project_line_no,
       p.product_code,
       left(btrim(d.description), 80)     AS do_description,
       oi.inquiry_no,
       oir.state                          AS oi_row_state,
       oir.verb                           AS oi_row_verb,
       so.order_date
FROM projects.sales_order_lines psol
JOIN sales_order_lines sol ON sol.id = psol.core_sales_order_line_id
JOIN sales_orders so       ON so.id = sol.sales_order_id
JOIN products p            ON p.id = sol.product_id
JOIN LATERAL (
  SELECT ol.description FROM order_lines ol
  WHERE ol.sales_order_line_id = sol.id AND btrim(coalesce(ol.description, '')) <> ''
  ORDER BY ol.created_at DESC LIMIT 1
) d ON true
LEFT JOIN LATERAL (
  SELECT r.* FROM projects.order_inquiry_rows r
  WHERE r.so_line_id = psol.id ORDER BY r.created_at DESC NULLS LAST LIMIT 1
) oir ON true
LEFT JOIN projects.order_inquiries oi ON oi.id = oir.order_inquiry_id
WHERE p.product_code IN ('RPACC', 'RPAC')
ORDER BY (oir.state = 'raised') DESC NULLS LAST, so.order_date DESC
LIMIT 15;

-- 2. Open RPACC project lines with NO description anywhere (the bare-code case), latest 5.
SELECT so.so_number, psol.line_no AS project_line_no, oir.state AS oi_row_state, so.order_date
FROM projects.sales_order_lines psol
JOIN sales_order_lines sol ON sol.id = psol.core_sales_order_line_id
JOIN sales_orders so       ON so.id = sol.sales_order_id
JOIN products p            ON p.id = sol.product_id
LEFT JOIN LATERAL (
  SELECT r.state FROM projects.order_inquiry_rows r
  WHERE r.so_line_id = psol.id ORDER BY r.created_at DESC NULLS LAST LIMIT 1
) oir ON true
WHERE p.product_code = 'RPACC'
  AND NOT EXISTS (SELECT 1 FROM order_lines ol WHERE ol.sales_order_line_id = sol.id
                  AND btrim(coalesce(ol.description, '')) <> '')
  AND coalesce(sol.qty_delivered, 0) < sol.qty_ordered
ORDER BY so.order_date DESC
LIMIT 5;

ROLLBACK;
