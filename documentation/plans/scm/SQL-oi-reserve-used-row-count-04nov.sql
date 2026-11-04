-- OI-RESERVE-USED-ROW: open (unanswered) reserve request rows sitting on a used or cancelled OI row.
-- Read-only. Run on prod by the owner. One row per request row, plus the live sibling count on the
-- same SO line in the same OI (1 = the repair can move it; 0 or 2+ = hold for a person).
BEGIN READ ONLY;

WITH open_rr AS (
    SELECT rr.id AS rr_id, rr.row_id, rr.qty_requested, req.order_inquiry_id, req.ordinal,
           req.requested_at, req.parked_at
    FROM projects.order_inquiry_reserve_request_rows rr
    JOIN projects.order_inquiry_reserve_requests req ON req.id = rr.request_id
    WHERE rr.qty_reserved IS NULL
      AND req.state = 'requested'
),
bad AS (
    SELECT o.*, r.item_code, r.qty, r.delivery_date, r.state, r.redirected_to_pool, r.so_line_id,
           psl.core_sales_order_line_id AS core_line_id
    FROM open_rr o
    JOIN projects.order_inquiry_rows r ON r.id = o.row_id
    LEFT JOIN projects.sales_order_lines psl ON psl.id = r.so_line_id
    WHERE r.redirected_to_pool OR r.state = 'cancelled'
)
SELECT oi.inquiry_no, so.so_number, b.item_code, b.qty AS row_qty, b.delivery_date AS told_date,
       b.qty_requested, b.state, b.redirected_to_pool AS used, b.ordinal AS request_no,
       (b.parked_at IS NOT NULL) AS parked,
       (SELECT count(*)
          FROM projects.order_inquiry_rows l
          JOIN projects.sales_order_lines lpsl ON lpsl.id = l.so_line_id
         WHERE l.order_inquiry_id = b.order_inquiry_id
           AND lpsl.core_sales_order_line_id = b.core_line_id
           AND NOT l.redirected_to_pool
           AND l.state <> 'cancelled') AS live_siblings
FROM bad b
JOIN projects.order_inquiries oi ON oi.id = b.order_inquiry_id
LEFT JOIN public.sales_order_lines col ON col.id = b.core_line_id
LEFT JOIN public.sales_orders so ON so.id = col.sales_order_id
ORDER BY oi.inquiry_no, b.item_code;

-- Summary.
SELECT count(*) AS open_request_rows_on_used_or_cancelled,
       count(*) FILTER (WHERE r.redirected_to_pool) AS on_used,
       count(*) FILTER (WHERE r.state = 'cancelled') AS on_cancelled,
       count(DISTINCT req.order_inquiry_id) AS ois
FROM projects.order_inquiry_reserve_request_rows rr
JOIN projects.order_inquiry_reserve_requests req ON req.id = rr.request_id
JOIN projects.order_inquiry_rows r ON r.id = rr.row_id
WHERE rr.qty_reserved IS NULL AND req.state = 'requested'
  AND (r.redirected_to_pool OR r.state = 'cancelled');

ROLLBACK;
