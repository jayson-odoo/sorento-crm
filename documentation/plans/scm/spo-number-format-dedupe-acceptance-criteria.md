# UAC: SPO number format reconcile + twin merge

1. After a full, unfiltered `--apply`, `SELECT count(*) FROM spo_allocations WHERE spo_number !~ '^SPO-\d{4}/\d{2}-\d{4}$' AND spo_number LIKE 'SPO-%'` = 0, same for `purchase_orders.po_number` - **checked by hand** after that run (a `--spo`-scoped run, and every automated test, leaves the rest of the real database exactly as found, so this is a whole-database invariant the script itself does not assert - see the plan's own note).
2. No SPO number appears under two spellings in any of the three tables (group by `_spo_match_key`, count distinct spelling = 1) - except a typo doc whose corrected target already exists, which is reported and left untouched on purpose (a manual decision, not a merge).
3. For every merged twin, the surviving allocation rows carry the CRM row's `inbound_shipment_id` and `created_by` where the book row had none.
4. No `picking_lines`, `order_inquiry_links`, `scm.order_link_claim`, or any other FK row that referenced a deleted id is NULL or missing afterwards; each points at the survivor (verified per-FK by counting rows against the P id before the merge and against the S id after, not merely "no row still names a P id" - a `SET NULL`/`CASCADE` FK passes the weaker check while silently losing the link).
5. Sum of `allocated_quantity` per SPO after merge = the book's sum (survivor), and every CRM line whose product the book lacked is present under the survivor number.
6. `--dry-run` (default) changes no row and prints the per-doc plan + JSON path. `--dry-run` together with `--apply` is a hard CLI error, not a silent pick-one.
7. Rerunning `--apply` reports zero work.
8. A failure mid-run rolls back everything, including work already done earlier in the same run (verified by test with real prior writes before the forced crash).
9. `scm.on_order_v` no longer double-counts the merged SPOs (spot check 3 numbers before/after on the local prod copy).
10. The typo shape (`SPO-20254/12-0074`) renames to the year its own rows' `issue_date` names (`SPO-2024/12-0074`), never to the `\1` year read off the malformed string (`SPO-2025/12-0074`) - the two are different, unrelated documents.
11. No survivor's `quantity_received` / `receipt_status` changes as a side effect of any run of this script - `sync_received_for_spo_number` is never called (see B1 in the review record / the plan's step 4).
12. Two companies carrying the same malformed number never merge into each other's document.
