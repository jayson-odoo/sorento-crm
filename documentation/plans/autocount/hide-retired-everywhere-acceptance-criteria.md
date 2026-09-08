# UAC: a retired SPO line is invisible everywhere

Status: IN PROGRESS 2026-09-08. Plan: `PLAN-hide-retired-everywhere.md`.

Every test seeds one document holding a visible open line and a retired line (retired_at set,
received 0) for the same product, plus, where the reader supports it, a retired line WITH a receipt
that must stay visible (R2).

- **AC-E1 [BE][T]** `order_inquiry_worklist_service.get_spo_detail` returns only visible lines, and
  its header ETA, supplier and container are derived from those lines only. A retired line carrying
  a receipt is still returned.
- **AC-E2 [BE][T]** `purchase_order_service._unshipped_spo_query`, behind the MCP tool
  `crm_procurement_po_placed_list`, excludes retired lines from both the rows and the summed
  quantity.
- **AC-E3 [BE][T]** Retiring a line deactivates its embedding document rather than re-embedding it,
  and `embedding_backfill_service` skips hidden rows. A retired line's text is not returned by a
  retrieval over the store.
- **AC-E4 [BE][T]** `entity_resolver._probe_spo` and `_prefix_probe_spo` resolve a number to a
  VISIBLE row's id when one exists, and do not resolve a number whose every line is retired.
- **AC-E5 [BE][T]** `spo_supply.spo_history_for_product` omits retired lines from both its open and
  its history legs.
- **AC-E6 [BE][T]** `scm/purchase_order_service._spo_takes_of` omits retired lines.
- **AC-E7 [BE][T]** `coverage_service._supply_events_many`'s shipment leg omits retired lines, so a
  pool is not credited with cover from a deleted line. Assert the resulting shortfall grows rather
  than shrinks.
- **AC-E8 [BE][T]** `list_shipments`' `spo_allocations_count` counts visible lines only and equals
  the count the grouped allocation listing shows for the same shipment.
- **AC-E9 [BE][T]** The "Linked to" readers (`project_order_inquiry_service.links_for_rows`,
  `spo_conversion_service._project_coverage`) omit a retired line's number.
- **AC-E10 [BE][T]** `spo_conversion_service.coverage_for_so_lines` and `_own_state` omit retired
  lines from the cover strip and the received rollup.
- **AC-E11 [BE][T]** `spo_last_receipt_service.last_receipt_rows` omits a retired line even when it
  is marked fully received with a zeroed receipt.
- **AC-E12 [BE][T]** `stock_debt_service._holds` omits a retired line's number.
- **AC-E13 [BE][T]** `order_link_service._purchase_side` never resolves a claim target to a retired
  line; it picks a visible sibling or refuses.
- **AC-E14 [BE]** `get_received_quantities_by_product` is deliberately unchanged, with a comment
  saying why: a receipt found through a retired line is still a receipt.

## Round 2 (security review, 2026-09-08)

- **AC-E15 [BE][T]** (deactivation is reversible) A line retired and then named again by a later push
  has an ACTIVE embedding document afterwards and is retrievable again. The worker's hash-skip
  branch re-activates a document it finds inactive before returning `skipped`. Note for whoever
  implements it: adding `retired_at` to the canonical body does NOT solve this. A hidden row never
  reaches body building at all, and an un-retired row's body is identical to its original, so the
  hash is unchanged either way. The skip branch is the only place that can repair it.

- **AC-E16 [BE][T]** (a writer's view of state is never filtered) `spo_conversion_service._own_state`
  is read by the SPO edit SAVE as well as by the planner display. It stays UNFILTERED, so a save
  sees every allocation it must update or delete and cannot insert a duplicate for a
  (shipment line, warehouse) whose row is merely hidden. The filtering moves to the display
  consumer. Assert both halves: the planner display omits a retired line, and the save's held state
  still contains it. AC-E10's `_own_state` half is revised accordingly.

## Round 3 (reviewer, 2026-09-08)

- **AC-E15 (extended)** The re-activation must also cover R2's own path, not only the un-retire: a
  retired line whose `quantity_received` goes from 0 to 5 when a goods-received note lands becomes
  visible by the clause, and its document must be active again. The hash is unchanged there too, so
  the same skip-branch repair covers both. Both cases get a test.

- **AC-E17 [BE][T]** (one answer per line) `spo_conversion_service._spo_cover_by_so_line` shares the
  same scan as `coverage_for_so_lines` and was left unfiltered, so the planner's `taken_by` still
  names an SPO the "Linked to" column hides, contradicting its own docstring that the two can never
  name a different SPO for the same line. Filter both.

- **AC-E14 (unmet, restated)** The comment at `get_received_quantities_by_product` saying why it is
  deliberately unfiltered was never written. Write it.

- **R10 and AC-E7 narrowed.** "The engine buys more, never less" holds for the retired-only case but
  not universally: the pro-rate means removing a hidden claim can raise another pool's share and
  shrink its shortfall. That is the more honest answer, since a deleted claim should stop competing,
  but the guarantee as written is false and must be narrowed to the retired-only case rather than
  left for the next reader to trust.

- **AC-E18 [BE][T]** (round 4) A save never deletes a line the display hid. `planner_state` omits a
  retired-only allocation from the split editor, so the browser posts splits without that warehouse
  and `revise`'s delete branch would remove the row as a side effect of an unrelated save. Its
  absence from the submitted splits is not a user decision, it is our own filtering coming back at
  us. `revise` skips deleting an allocation that is not visible. Two inputs, both tested:
  (a) a retired-only landing at WH-A, so the display shows no split for it and an unrelated save
  would delete it; (b) a visible AND a hidden allocation at the SAME warehouse, where `wanted` is
  keyed by warehouse id and the entry is consumed by the first match, so whichever row the loop
  reaches second falls into the delete branch even though the operator DID submit a split for that
  warehouse. Assert in both that the hidden allocation survives with its quantities untouched.
  Deleting a retired row would also destroy the frozen `stated_received` and the `source_doc_ref`
  identity the ingest needs to un-retire it on the next push.
