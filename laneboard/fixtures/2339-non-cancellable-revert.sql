-- Revert of laneboard/fixtures/2339-non-cancellable.sql (PR #2339 hand-test fixture). TEST COPY ONLY.
-- Removes the fixture rows by their fixed ids, children first, plus what the hand test wrote against
-- them (proposal draft and its History cascade with the proposal; activity rows are deleted here).
-- audit_logs is append-only (a trigger refuses DELETE), so the hand test's audit rows stay; they
-- name only the deleted ZZT ids.
-- Idempotent: re-running deletes nothing further.
BEGIN;

DELETE FROM projects.sales_order_lines
 WHERE project_sales_order_id = 'f1c70000-0000-4000-8000-00000000000b';
DELETE FROM projects.sales_orders WHERE id = 'f1c70000-0000-4000-8000-00000000000b';
DELETE FROM projects.quotation_lines WHERE version_id IN (
  SELECT v.id FROM projects.quotation_versions v
    JOIN projects.quotations q ON q.id = v.quotation_id
   WHERE q.project_id = 'f1c70000-0000-4000-8000-000000000006');
DELETE FROM projects.quotation_versions WHERE quotation_id IN (
  SELECT id FROM projects.quotations WHERE project_id = 'f1c70000-0000-4000-8000-000000000006');
DELETE FROM projects.quotations WHERE project_id = 'f1c70000-0000-4000-8000-000000000006';
DELETE FROM projects.quotation_documents WHERE project_id = 'f1c70000-0000-4000-8000-000000000006';
DELETE FROM activity_events WHERE entity_id::text LIKE 'f1c70000-0000-4000-8000-%';
DELETE FROM projects.projects WHERE id = 'f1c70000-0000-4000-8000-000000000006';
DELETE FROM projects.series_products WHERE series_id = 'f1c70000-0000-4000-8000-000000000005';
DELETE FROM projects.series_categories WHERE series_id = 'f1c70000-0000-4000-8000-000000000005';
DELETE FROM projects.series WHERE id = 'f1c70000-0000-4000-8000-000000000005';
DELETE FROM products WHERE id = 'f1c70000-0000-4000-8000-000000000004';
DELETE FROM product_categories WHERE id = 'f1c70000-0000-4000-8000-000000000003';
DELETE FROM units_of_measure WHERE id = 'f1c70000-0000-4000-8000-000000000002';
DELETE FROM users WHERE id = 'f1c70000-0000-4000-8000-000000000001';

COMMIT;
