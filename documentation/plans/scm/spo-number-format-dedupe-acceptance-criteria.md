# UAC: SPO number format reconcile + twin merge

1. After `--apply`, `SELECT count(*) FROM spo_allocations WHERE spo_number !~ '^SPO-\d{4}/\d{2}-\d{4}$' AND spo_number LIKE 'SPO-%'` = 0, same for `purchase_orders.po_number`.
2. No SPO number appears under two spellings in any of the three tables (group by `_spo_match_key`, count distinct spelling = 1).
3. For every merged twin, the surviving allocation rows carry the CRM row's `inbound_shipment_id` and `created_by` where the book row had none.
4. No `picking_lines`, `order_inquiry_links`, `scm_order_link_claims`, or any other FK row that referenced a deleted id is NULL afterwards; each points at the survivor.
5. Sum of `allocated_quantity` per SPO after merge = the book's sum (survivor), and every CRM line whose product the book lacked is present under the survivor number.
6. `--dry-run` (default) changes no row and prints the per-doc plan + JSON path.
7. Rerunning `--apply` reports zero work.
8. A failure mid-run rolls back everything (verified by test).
9. `scm.on_order_v` no longer double-counts the merged SPOs (spot check 3 numbers before/after on the local prod copy).
