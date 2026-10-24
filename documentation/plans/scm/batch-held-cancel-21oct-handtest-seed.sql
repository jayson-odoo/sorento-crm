-- PLAN-BATCH-HELD-CANCEL hand-test seed (crew ruling 21 Oct 2026): LOCAL dev copy
-- sorento_prod_1020 ONLY. Never run on production.
-- SO394881 already carries pending batch a0df3624 (10 cancelled + 30 added rows). This adds the
-- 12 Cancel SO drafts the board held, in propose_autocount_cancel's draft shape
-- (project_line_draft_service.py:316-336). On this copy the 12 core lines are still open and have
-- no live order inquiry row, so the AutoCount ingest itself would not have written them; the board
-- holds a saved Cancel SO the same way whatever its source (fulfilmentBoard.ts pressRoleFor).
-- Idempotent: rerun replaces the same 12 drafts. Undo: batch-held-cancel-21oct-handtest-cleanup.sql.
BEGIN;
INSERT INTO projects.so_supply_decision_drafts
    (id, company_id, sales_order_id, core_line_id, line_no, item_code, bucket_key,
     decision, line_snapshot, saved_by, saved_at, created_at)
SELECT gen_random_uuid(), c.company_id, c.sales_order_id, c.id, m.line_no,
       coalesce(p.product_code, 'UNKNOWN'), 'no_date',
       jsonb_build_object(
           'verdict', 'cancelled',
           'reason', 'AutoCount Cancel SO ZZT-HANDTEST-1817',
           'source', 'autocount_cancel'
       ),
       jsonb_build_object('open_qty', '0', 'required_date', c.required_date::text),
       NULL, now(), now()
FROM projects.sales_order_lines m
JOIN public.sales_order_lines c ON c.id = m.core_sales_order_line_id
JOIN public.sales_orders so ON so.id = c.sales_order_id AND so.so_number = 'SO394881'
LEFT JOIN public.products p ON p.id = c.product_id
WHERE m.line_no IN (82, 96, 112, 256, 272, 296, 480, 496, 512, 640, 656, 672)
  AND NOT EXISTS (
      SELECT 1 FROM projects.so_supply_decision_drafts d WHERE d.core_line_id = c.id
  );
SELECT count(*) AS seeded_drafts
FROM projects.so_supply_decision_drafts
WHERE decision->>'reason' = 'AutoCount Cancel SO ZZT-HANDTEST-1817';
COMMIT;
