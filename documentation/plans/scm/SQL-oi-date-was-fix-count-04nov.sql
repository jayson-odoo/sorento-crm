-- OI-DATE-WAS-FIX: READ-ONLY count of order inquiry rows whose DELAY/ADVANCE email the
-- oiod_0001 backfill swallowed (deployed with #2145, 4 Nov 2026 14:30 MYT).
--
-- Plain SQL for DBeaver: SELECT only, writes nothing, no psql meta commands, no variables.
-- Run each statement on its own (put the cursor in it and Ctrl+Enter).
--
-- A row is affected when ALL of these hold:
--   * oiod_0001 changed it (it is in projects.oi_delivery_date_backfill);
--   * it is not cancelled;
--   * it still sits on the date the backfill gave it (no Confirm has moved it since:
--     its Was is still the old told date and its told date is not the old one);
--   * its SO line has a planning change of kind delayed or advanced that is still
--     PENDING (waiting for CS Confirm). At that Confirm the row already carries the new
--     date, so no DELAY / ADVANCE email goes to purchasing.

-- 1) The count.
SELECT COUNT(*) AS affected_rows,
       COUNT(DISTINCT r.so_line_id) AS affected_so_lines
FROM projects.oi_delivery_date_backfill b
JOIN projects.order_inquiry_rows r ON r.id = b.row_id
WHERE r.state <> 'cancelled'
  AND r.delivery_date IS DISTINCT FROM b.old_delivery_date
  AND r.previous_delivery_date IS NOT DISTINCT FROM b.old_delivery_date
  AND EXISTS (
        SELECT 1
        FROM projects.planning_change_rows pc
        WHERE pc.project_line_id = r.so_line_id
          AND pc.applied_state = 'pending'
          AND pc.kind IN ('delayed', 'advanced')
      );

-- 2) The list, one line per affected OI row.
SELECT oi.inquiry_no                                         AS oi_no,
       COALESCE(cso.so_number, pso.autocount_doc_no, pso.provisional_ref) AS so_no,
       COALESCE(c.line_no, m.line_no)                        AS so_line_no,
       r.item_code                                           AS product_code,
       r.qty                                                 AS oi_qty,
       r.state                                               AS oi_state,
       b.old_delivery_date                                   AS old_told_date,
       r.delivery_date                                       AS told_date_now,
       COALESCE(c.required_date, m.delivery_date)            AS so_line_date_now,
       pend.kinds                                            AS pending_change_kind,
       pend.raised_at                                        AS pending_change_raised_at
FROM projects.oi_delivery_date_backfill b
JOIN projects.order_inquiry_rows r ON r.id = b.row_id
JOIN projects.order_inquiries oi ON oi.id = r.order_inquiry_id
JOIN projects.sales_order_lines m ON m.id = r.so_line_id
JOIN projects.sales_orders pso ON pso.id = m.project_sales_order_id
LEFT JOIN public.sales_orders cso ON cso.id = pso.so_id
LEFT JOIN public.sales_order_lines c ON c.id = m.core_sales_order_line_id
JOIN (
        SELECT pc.project_line_id,
               string_agg(DISTINCT pc.kind, ', ') AS kinds,
               MIN(pc.created_at) AS raised_at
        FROM projects.planning_change_rows pc
        WHERE pc.applied_state = 'pending'
          AND pc.kind IN ('delayed', 'advanced')
        GROUP BY pc.project_line_id
     ) pend ON pend.project_line_id = r.so_line_id
WHERE r.state <> 'cancelled'
  AND r.delivery_date IS DISTINCT FROM b.old_delivery_date
  AND r.previous_delivery_date IS NOT DISTINCT FROM b.old_delivery_date
ORDER BY so_no, so_line_no, oi_no;
