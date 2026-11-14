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
DELETE FROM sales_order_lines WHERE sales_order_id = 'f1c70000-0000-4000-8000-000000000104';
DELETE FROM sales_orders WHERE id = 'f1c70000-0000-4000-8000-000000000104';
DELETE FROM warehouses WHERE id = 'f1c70000-0000-4000-8000-000000000103';
DELETE FROM projects.quotation_issue_scopes WHERE issue_id IN (
  SELECT i.id FROM projects.quotation_issues i JOIN projects.quotation_documents d ON d.id = i.document_id
   WHERE d.project_id = 'f1c70000-0000-4000-8000-000000000006');
DELETE FROM projects.quotation_issues WHERE document_id IN (
  SELECT id FROM projects.quotation_documents WHERE project_id = 'f1c70000-0000-4000-8000-000000000006');
DELETE FROM projects.quotation_lines WHERE version_id IN (
  SELECT v.id FROM projects.quotation_versions v
    JOIN projects.quotations q ON q.id = v.quotation_id
   WHERE q.project_id = 'f1c70000-0000-4000-8000-000000000006');
DELETE FROM projects.quotation_versions WHERE quotation_id IN (
  SELECT id FROM projects.quotations WHERE project_id = 'f1c70000-0000-4000-8000-000000000006');
DELETE FROM projects.quotations WHERE project_id = 'f1c70000-0000-4000-8000-000000000006';
DELETE FROM projects.quotation_documents WHERE project_id = 'f1c70000-0000-4000-8000-000000000006';
DELETE FROM projects.quotation_signatures WHERE id = 'f1c70000-0000-4000-8000-000000000116'
   OR user_id = 'f1c70000-0000-4000-8000-000000000001';
DELETE FROM activity_events WHERE entity_id::text LIKE 'f1c70000-0000-4000-8000-%';
DELETE FROM projects.projects WHERE id = 'f1c70000-0000-4000-8000-000000000006';
DELETE FROM projects.series_products WHERE series_id = 'f1c70000-0000-4000-8000-000000000005';
DELETE FROM projects.series_categories WHERE series_id = 'f1c70000-0000-4000-8000-000000000005';
DELETE FROM projects.series WHERE id = 'f1c70000-0000-4000-8000-000000000005';
DELETE FROM products WHERE id IN ('f1c70000-0000-4000-8000-000000000004',
                                  'f1c70000-0000-4000-8000-000000000102');
DELETE FROM product_categories WHERE id IN ('f1c70000-0000-4000-8000-000000000003',
                                            'f1c70000-0000-4000-8000-000000000101');
DELETE FROM units_of_measure WHERE id = 'f1c70000-0000-4000-8000-000000000002';
DELETE FROM users WHERE id = 'f1c70000-0000-4000-8000-000000000001';

COMMIT;
