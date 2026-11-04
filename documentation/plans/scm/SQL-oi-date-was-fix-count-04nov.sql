-- OI-DATE-WAS-FIX: READ-ONLY counts of order inquiry rows whose DELAY/ADVANCE email the
-- oiod_0001 backfill swallowed (deployed with #2145, 4 Nov 2026 14:30 MYT).
--
-- Plain SQL for DBeaver: SELECT only, writes nothing, no psql meta commands, no variables.
-- Run each statement on its own (put the cursor in it and Ctrl+Enter).
--
-- Statements 1 and 2 (still fixable by migration oiod_0002_pending_restore) count a row when:
--   * oiod_0001 changed it (it is in projects.oi_delivery_date_backfill);
--   * it is a live buy row (ORDER / ORDER_BACK, not cancelled, not redirected to the pool);
--   * it still sits on the date the backfill gave it (no Confirm has moved it since:
--     its Was is still the old told date and its told date is not the old one);
--   * its SO line has a planning change still PENDING (waiting for CS Confirm) that moves
--     the date (from and to required_date both set and different). At that Confirm the row
--     already carries the new date, so no DELAY / ADVANCE email goes to purchasing.
--
-- Statement 3 lists rows whose date move was ALREADY CONFIRMED after the backfill, with no
-- email. The migration cannot help those (nothing is pending any more); they are listed so
-- the owner can decide whether purchasing needs a resend.

-- 1) The count still fixable before Confirm.
SELECT COUNT(*) AS affected_rows,
       COUNT(DISTINCT r.so_line_id) AS affected_so_lines
FROM projects.oi_delivery_date_backfill b
JOIN projects.order_inquiry_rows r ON r.id = b.row_id
WHERE r.state <> 'cancelled'
  AND r.verb IN ('ORDER', 'ORDER_BACK')
  AND NOT COALESCE(r.redirected_to_pool, false)
  AND r.delivery_date IS DISTINCT FROM b.old_delivery_date
  AND r.previous_delivery_date IS NOT DISTINCT FROM b.old_delivery_date
  AND EXISTS (
        SELECT 1
        FROM projects.planning_change_rows pc
        WHERE pc.project_line_id = r.so_line_id
          AND pc.applied_state = 'pending'
          AND pc.from_json ->> 'required_date' IS NOT NULL
          AND pc.to_json ->> 'required_date' IS NOT NULL
          AND pc.from_json ->> 'required_date' <> pc.to_json ->> 'required_date'
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
          AND pc.from_json ->> 'required_date' IS NOT NULL
          AND pc.to_json ->> 'required_date' IS NOT NULL
          AND pc.from_json ->> 'required_date' <> pc.to_json ->> 'required_date'
        GROUP BY pc.project_line_id
     ) pend ON pend.project_line_id = r.so_line_id
WHERE r.state <> 'cancelled'
  AND r.verb IN ('ORDER', 'ORDER_BACK')
  AND NOT COALESCE(r.redirected_to_pool, false)
  AND r.delivery_date IS DISTINCT FROM b.old_delivery_date
  AND r.previous_delivery_date IS NOT DISTINCT FROM b.old_delivery_date
ORDER BY so_no, so_line_no, oi_no;

-- 3) Already confirmed since the backfill with no email (needs a resend decision, not the
--    migration): the row still holds the backfilled values and its line's date move to that
--    very date was applied on or after 4 Nov 2026. confirmed_at is shown so rows applied
--    before 14:30 MYT that day can be told apart by eye. Only right BEFORE oiod_0002 deploys:
--    after it, a row oiod_0002 restored and whose Confirm then did email reads the same way.
SELECT oi.inquiry_no                                         AS oi_no,
       COALESCE(cso.so_number, pso.autocount_doc_no, pso.provisional_ref) AS so_no,
       COALESCE(c.line_no, m.line_no)                        AS so_line_no,
       r.item_code                                           AS product_code,
       r.qty                                                 AS oi_qty,
       b.old_delivery_date                                   AS old_told_date,
       r.delivery_date                                       AS confirmed_date,
       ap.kinds                                              AS change_kind,
       ap.confirmed_at                                       AS confirmed_at
FROM projects.oi_delivery_date_backfill b
JOIN projects.order_inquiry_rows r ON r.id = b.row_id
JOIN projects.order_inquiries oi ON oi.id = r.order_inquiry_id
JOIN projects.sales_order_lines m ON m.id = r.so_line_id
JOIN projects.sales_orders pso ON pso.id = m.project_sales_order_id
LEFT JOIN public.sales_orders cso ON cso.id = pso.so_id
LEFT JOIN public.sales_order_lines c ON c.id = m.core_sales_order_line_id
JOIN (
        SELECT pc.project_line_id,
               CAST(pc.to_json ->> 'required_date' AS date) AS to_date,
               string_agg(DISTINCT pc.kind, ', ') AS kinds,
               MAX(pcb.applied_at) AS confirmed_at
        FROM projects.planning_change_rows pc
        JOIN projects.planning_change_batches pcb ON pcb.id = pc.batch_id
        WHERE pc.applied_state = 'applied'
          AND pcb.applied_at >= TIMESTAMP '2026-11-04 00:00:00'
          AND pc.from_json ->> 'required_date' IS NOT NULL
          AND pc.to_json ->> 'required_date' IS NOT NULL
          AND pc.from_json ->> 'required_date' <> pc.to_json ->> 'required_date'
        GROUP BY pc.project_line_id, CAST(pc.to_json ->> 'required_date' AS date)
     ) ap ON ap.project_line_id = r.so_line_id AND ap.to_date = r.delivery_date
WHERE r.state <> 'cancelled'
  AND r.verb IN ('ORDER', 'ORDER_BACK')
  AND NOT COALESCE(r.redirected_to_pool, false)
  AND r.delivery_date IS DISTINCT FROM b.old_delivery_date
  AND r.previous_delivery_date IS NOT DISTINCT FROM b.old_delivery_date
ORDER BY so_no, so_line_no, oi_no;
