-- Removes the six seeded demo suppliers SCM-SRC-01..06 (created 18 Jul 2026) and their
-- product_suppliers price rows (captain, 28 Aug 2026: "all these SCM-xxx suppliers are fake").
-- Every other reference is nulled explicitly rather than trusting the FK rule, so the same
-- file runs the same way on the dev copy and on prod. Idempotent: a second run touches 0 rows.
BEGIN;
CREATE TEMP TABLE fake_supplier ON COMMIT DROP AS
  SELECT id, supplier_code FROM suppliers WHERE supplier_code LIKE 'SCM-SRC-%';
SELECT supplier_code FROM fake_supplier ORDER BY 1;
DELETE FROM product_suppliers WHERE supplier_id IN (SELECT id FROM fake_supplier);
UPDATE purchase_orders SET supplier_id = NULL WHERE supplier_id IN (SELECT id FROM fake_supplier);
UPDATE scm.order_summary_row SET chosen_supplier_id = NULL WHERE chosen_supplier_id IN (SELECT id FROM fake_supplier);
UPDATE scm.reorder_recommendation SET supplier_id = NULL WHERE supplier_id IN (SELECT id FROM fake_supplier);
UPDATE scm.recommendation_override SET override_supplier_id = NULL WHERE override_supplier_id IN (SELECT id FROM fake_supplier);
UPDATE scm.plan_row_decision SET supplier_id = NULL WHERE supplier_id IN (SELECT id FROM fake_supplier);
DELETE FROM suppliers WHERE id IN (SELECT id FROM fake_supplier);
COMMIT;
