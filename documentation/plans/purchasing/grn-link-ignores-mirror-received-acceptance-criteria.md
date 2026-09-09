# UAC: GRN import links its lines even when the AutoCount mirror already stated the receipt

Issue #780. Plan: `PLAN-grn-link-ignores-mirror-received.md`.

| ID | Criterion | Verified by |
| --- | --- | --- |
| AC-MR-1 | An allocation whose `stated_received` equals its `quantity_received` and has no picking line offers its FULL `allocated_quantity` to the pool. | pytest 1 |
| AC-MR-2 | Once a GRN line links to that allocation, another GRN sees no capacity on it, and the same GRN re-imported (excluded) sees all of it. | pytest 2 |
| AC-MR-3 | A stored receipt larger than the statement plus linked lines still consumes the unexplained difference (AC-FM-28 kept). | pytest 3 |
| AC-MR-4 | A GRN imported AFTER the mirror statement draws one linked chunk per covering allocation and no trailing unlinked draw when quantities tally; the allocation's `quantity_received` does not regress. | pytest 4 |
| AC-MR-5 | After a GRN import whose lines could not link at all, every container under the header's SPO number has its line statuses and header status refreshed (container reads Fully Received when the orphan lines cover it). | pytest 5 |
| AC-MR-6 | `test_a_receipt_no_picking_line_explains_still_consumes` and `test_a_stored_receipt_its_own_lines_explain_is_not_counted_twice` unchanged and green. | pytest file |
| AC-MR-7 | No migration, no FE change, no change to `_sync_received_for_allocations`. | diff review |
| AC-MR-8 | Prod: after deploy, `backfill_grn_spo_allocation_links.py --dry-run --grn GR-2026/09-0027` plans 17 relinks and 0 unlinked remainder; container CMAU4932912 and GR-2026/09-0027 lines show linked. | owner, post-deploy |
