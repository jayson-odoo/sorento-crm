-- PLAN-BATCH-HELD-CANCEL: READ ONLY. For the OWNER to run on prod (crew never reads prod).
-- How many orders the "held Cancel SO" dead end reaches today, before and after the deploy.
BEGIN TRANSACTION READ ONLY;

-- 1. Open planning-change batches (applied_at NULL) that still have pending rows, per source.
SELECT b.source_kind,
       count(DISTINCT b.id)                      AS open_batches,
       count(DISTINCT r.project_sales_order_id)  AS orders,
       count(r.id)                               AS pending_rows,
       count(r.id) FILTER (WHERE r.kind = 'added' AND r.project_line_id IS NULL) AS unlinked_added_rows
FROM projects.planning_change_batches b
JOIN projects.planning_change_rows r
  ON r.batch_id = b.id AND r.applied_state = 'pending'
WHERE b.applied_at IS NULL
GROUP BY b.source_kind
ORDER BY open_batches DESC;

-- 2. Saved Cancel SO drafts on a line a pending row of an open batch names (the board held these).
SELECT count(DISTINCT d.id)                                                         AS held_cancel_drafts,
       count(DISTINCT d.id) FILTER (WHERE d.decision->>'source' = 'autocount_cancel') AS autocount_cancel_drafts,
       count(DISTINCT r.project_sales_order_id)                                     AS orders
FROM projects.so_supply_decision_drafts d
JOIN projects.planning_change_rows r
  ON r.core_line_id = d.core_line_id AND r.applied_state = 'pending'
JOIN projects.planning_change_batches b
  ON b.id = r.batch_id AND b.applied_at IS NULL
WHERE d.decision->>'verdict' = 'cancelled';

-- 3. The same, per order (largest first).
SELECT r.project_sales_order_id,
       count(DISTINCT d.id) AS held_cancel_drafts,
       min(d.decision->>'reason') AS a_reason
FROM projects.so_supply_decision_drafts d
JOIN projects.planning_change_rows r
  ON r.core_line_id = d.core_line_id AND r.applied_state = 'pending'
JOIN projects.planning_change_batches b
  ON b.id = r.batch_id AND b.applied_at IS NULL
WHERE d.decision->>'verdict' = 'cancelled'
GROUP BY r.project_sales_order_id
ORDER BY held_cancel_drafts DESC
LIMIT 50;

ROLLBACK;
