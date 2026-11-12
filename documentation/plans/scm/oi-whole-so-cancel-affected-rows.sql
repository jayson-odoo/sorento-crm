-- OI-WHOLE-SO-CANCEL Q3 (a): READ-ONLY list of order inquiry rows the hole left behind since 30 Oct 2026.
-- A live OI row on an AutoCount SO line that ended cancelled with NO board item for CS:
--   * header cancelled or SO deleted (rows auto-done at sync: acknowledged, acknowledged_by NULL), or
--   * the SO's last open line removed (rows still live, nobody told).
-- Excludes the paths that already wait on the board: Cancel SO document (cancelled_by_cancel_doc),
-- CS board Cancel SO (cancelled_at set), and any line that has a planning-change `cancelled` row.
-- SELECT only. Run on the dev prod-copy first; nothing here writes.
SELECT
    oi.inquiry_no,
    so.so_number,
    so.status                                  AS so_status,
    sol.updated_at                             AS line_cancelled_around,
    oir.item_code,
    oir.qty,
    oir.verb,
    oir.state                                  AS oi_row_state,
    oir.ack_state,
    (oir.ack_state = 'acknowledged' AND oir.acknowledged_by IS NULL) AS auto_done_at_sync
FROM projects.order_inquiry_rows oir
JOIN projects.order_inquiries oi       ON oi.id = oir.order_inquiry_id
JOIN projects.sales_order_lines psl    ON psl.id = oir.so_line_id
JOIN public.sales_order_lines sol      ON sol.id = psl.core_sales_order_line_id
JOIN public.sales_orders so            ON so.id = sol.sales_order_id
WHERE sol.line_status = 'cancelled'
  AND sol.updated_at >= DATE '2026-10-30'
  AND sol.cancelled_by_cancel_doc = false
  AND sol.cancelled_at IS NULL
  AND oir.state <> 'cancelled'
  AND oir.ack_state <> 'rejected'
  AND NOT EXISTS (
        SELECT 1 FROM projects.planning_change_rows pcr
        WHERE pcr.core_line_id = sol.id AND pcr.kind = 'cancelled'
  )
ORDER BY so.so_number, oi.inquiry_no, oir.item_code;
