-- OI-PRODUCT-FOLLOW: PROPOSED one-off correction. FOR THE OWNER TO APPROVE.
-- Crew never runs this on prod. It needs this lane's migration (previous_item_code) first.
-- Default is ROLLBACK: read the counts, then change the last line to COMMIT only if they
-- match what Q5 of oi-product-follow-prod-readonly.sql reported.
--
-- Scope (card Q3, recommended (a)): live OI rows whose item_code differs from their
-- AutoCount line's product, and which
--   * hold NO order_inquiry_links row (a linked row has old-product sourcing on it; that
--     stays with the planning board's product_changed flow, no silent re-point), and
--   * have NO pending product_changed planning row (the planner's apply will do it).
-- Each corrected row keeps the old code in previous_item_code ("was X") and a note.

BEGIN;

CREATE TEMP TABLE _oi_product_fix ON COMMIT DROP AS
SELECT r.id AS row_id, r.item_code AS old_code, cp.product_code AS new_code
FROM projects.order_inquiry_rows r
JOIN projects.sales_order_lines pl ON pl.id = r.so_line_id
JOIN public.sales_order_lines sol  ON sol.id = pl.core_sales_order_line_id
JOIN public.products cp            ON cp.id = sol.product_id
WHERE r.state <> 'cancelled'
  AND r.item_code IS DISTINCT FROM cp.product_code
  AND NOT EXISTS (SELECT 1 FROM projects.order_inquiry_links l WHERE l.row_id = r.id)
  AND NOT EXISTS (SELECT 1 FROM projects.planning_change_rows cr
                  WHERE cr.core_line_id = sol.id
                    AND cr.kind = 'product_changed'
                    AND cr.applied_state = 'pending');

SELECT count(*) AS rows_to_fix FROM _oi_product_fix;
SELECT * FROM _oi_product_fix ORDER BY new_code LIMIT 200;

-- Mirror lines follow the AutoCount line's product (what _sync_mirror_line does from now on).
UPDATE projects.sales_order_lines pl
SET product_id = sol.product_id
FROM public.sales_order_lines sol
WHERE sol.id = pl.core_sales_order_line_id
  AND pl.product_id IS DISTINCT FROM sol.product_id;

UPDATE projects.order_inquiry_rows r
SET previous_item_code = f.old_code,
    item_code          = f.new_code,
    note = CASE WHEN r.note IS NULL OR r.note = ''
                THEN 'Was ' || coalesce(f.old_code, '-') || ' (AutoCount product change, corrected 2026-10)'
                ELSE r.note || '; Was ' || coalesce(f.old_code, '-') || ' (AutoCount product change, corrected 2026-10)'
           END,
    -- A row purchasing already confirmed comes back to To confirm, the same handshake
    -- every other in-place amendment uses (_settle_row_in_place).
    ack_state  = CASE WHEN r.ack_state IN ('acknowledged', 'changed') THEN 'changed' ELSE r.ack_state END,
    changed_at = CASE WHEN r.ack_state IN ('acknowledged', 'changed') THEN now() ELSE r.changed_at END
FROM _oi_product_fix f
WHERE r.id = f.row_id;

-- Left for the board (listed, not touched): mismatched rows that hold a link.
SELECT r.id, r.item_code, cp.product_code AS so_product
FROM projects.order_inquiry_rows r
JOIN projects.sales_order_lines pl ON pl.id = r.so_line_id
JOIN public.sales_order_lines sol  ON sol.id = pl.core_sales_order_line_id
JOIN public.products cp            ON cp.id = sol.product_id
WHERE r.state <> 'cancelled'
  AND r.item_code IS DISTINCT FROM cp.product_code;

ROLLBACK;  -- owner: change to COMMIT once the counts above are right
