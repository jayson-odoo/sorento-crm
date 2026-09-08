# UAC: hide retired SPO allocation lines

Status: DRAFT 2026-09-08. Plan: `PLAN-hide-retired-spo-lines.md`. Depends on PR #740.

Tags: [BE] backend, [T] tester writes it red first, [S] backfill script. Postgres only, seed every
row under a marker.

- **AC-H1 [BE][T]** (R1) A document holding one open line and one line with `retired_at` set
  (received 0) returns only the open line from `get_document`; `total_allocated` counts the open line
  only; Balance is unchanged.

- **AC-H2 [BE][T]** (R1) A line closed with `receipt_status = 'fully_received'` and `retired_at` NULL
  is still returned, and still counts in `total_allocated` and `total_received`.

- **AC-H3 [BE][T]** (R2) A line with `retired_at` set AND `quantity_received > 0` is still returned,
  counts in `total_received`, and reads balance 0.

- **AC-H4 [BE][T]** (R5) Every returned line that is not outstanding reads `balance 0`; the sum of
  the returned lines' balances equals the document's Balance.

- **AC-H5 [BE][T]** (R3) A GRN whose picking line points at a hidden allocation still renders that
  allocation in the GRN detail response; the allocation is reachable by id.

- **AC-H6 [BE][T]** (R6) The grid (`list_allocations`, `list_documents`) and the detail builder all
  read one clause from `spo_supply`; a test asserts the three agree on the same seeded document.

- **AC-H7 [S][T]** (backfill) Given an autocount row closed with receipt 0 and `retired_at` NULL, a
  fully-received closed row, and a closed row with a partial receipt: `--dry-run` writes nothing and
  names one document; `--apply` stamps only the first row; a second `--apply` reports zero.

- **AC-H8 [BE]** SPO-2026/09-0036 after the backfill: 33 lines' worth of open supply, Total qty
  38,777, no C-FHSS14 line of 4412.

## Round 2 (security review, 2026-09-08)

The plan's premise that a line closes for two reasons only is wrong. Four writers close an
`autocount` line without retiring it: the SCM outstanding book's absence sweep
(`outstanding_import_service`, which means the goods ARRIVED and deliberately writes no receipt),
a cancelled document (`force_closed`), the deletion service keeping a referenced row, and a
receipt. So "closed, never received" is not evidence of retirement.

- **AC-H9 [S][T]** (B1, backfill evidence) The backfill stamps a row only when it also carries a
  `source_ref` AND its `(company, spo_number, product_id, upper(location_code))` group holds an OPEN
  row created strictly later. That is the replacement AutoCount wrote when it edited the line.
  Negative cases, none of them stamped: a line closed by the outstanding book's absence sweep (no
  later sibling), every line of a cancelled document (no OPEN sibling exists), a closed line whose
  group has no later row at all, and a row with `source_ref` NULL.

- **AC-H10 [BE][T]** (B2, receipt after retirement) Given a retired allocation (received 0) and a
  goods-received note approved AFTER the retirement whose picking line draws 5 against it: the
  allocation reads `quantity_received 5`, stays visible on the document, and counts in
  `total_received`. It takes no share of its group's receipt and is never reopened. A retired line
  whose stated receipt is 29 and whose goods-received note is then deleted still reads 29 (the D28c
  floor, AC-X40 unchanged).

## Round 3 (reviewer, 2026-09-08)

- **AC-H11 [BE][T]** (ghost document) A document whose every line is hidden does not appear in
  `list_documents` under any state, and `get_document` still answers 404 for it. Today the group
  forms with the aggregates gated but not the membership, so it lists as a 0-line row that errors
  when opened. Reachable without the backfill: a push naming zero lines retires every row.

- **AC-H12 [BE][T]** (header agrees with the page) `list_documents`' Balance, status, worst overdue
  and earliest ETA count only visible lines, the same set `get_document` returns. Seed a document
  with one open visible line and one hidden line that is `open` with zero receipt (the shape that
  breaks the "retired implies closed" convention) and assert the list header's Balance equals the
  detail's. The supplier rollup counts the same visible set on both sides, so the majority supplier
  name cannot differ between the list and the page it opens.

- **AC-H13 [BE][T]** (packing list) The per-product related-SPO strip on the packing-list detail
  (`app/api/v1/procurement/packing_lists.py`) hides retired allocations and excludes their allocated
  quantity, the same rule as every other listing.

## Round 4 (security review of the delta, 2026-09-08)

Round 2 dropped the receipt predicate and round 2 also added a write to retired rows. Each is right
alone; together a backfill-stamped row carrying a receipt but no frozen floor can be zeroed by the
next recompute and then hidden, which is the D28 defect class on the one row shape that is invisible
afterwards.

- **AC-H14 [BE][T]** (ownership gate) The retired branch of `_sync_received_for_allocations` skips a
  row that is neither released nor picked against, exactly as the non-AutoCount branch does. Given a
  retired allocation with `quantity_received 25`, `stated_received` NULL and no picking line
  anywhere, running `sync_received_for_spo_number` for its document leaves it at 25 and visible. A
  retired allocation that IS picked against still takes its own approved total (AC-H10 unchanged).

- **AC-H15 [S][T]** (backfill freezes) The backfill sets `stated_received = max(stated, received)`
  when that is positive, before stamping `retired_at`, the same order the ingest's leftover sweep and
  the dedupe use. After `--apply` on a row carrying 25, a later `sync_received_for_spo_number` leaves
  it at 25.

- **AC-H16 [S][T]** (a live line is never stamped) The backfill never stamps a row whose
  `receipt_status` is `fully_received`. Given push 1 writing a line closed at 100 of 100 that
  AutoCount still names, and push 2 adding an open sibling for the same product and location, the
  fully received line is NOT stamped. Marking it would gain nothing, because a received line stays
  visible under R2 either way, and would wrongly take it out of its group's receipt sharing.

- **AC-H17 (revised, round 5) [BE][T]** (one payload, one rule, display only) The packing-list
  detail's `spo_allocated_quantity` AND the `line_status` it reports are both derived from the
  visible set, recomputed for the response. `refresh_shipment_line_statuses`' PERSISTED column and
  status are NOT changed: they feed the reorder engine, not the screen. So one payload carries one
  population, and no stored value moves.

- **AC-H19 [BE][T]** (the signal n8n actually reads) `incoming_stock_service._warehouse_allocations_for`
  counts retired allocations today, with no line-status or retirement test, so the incoming badge
  and its `unallocated_quantity` gap both credit supply that AutoCount deleted. It takes
  `visible_line_clauses()`. A retired allocation on a container stops counting as allocated, which
  widens the gap to what is genuinely uncovered.

- **AC-H17 (superseded) [BE][T]** (one payload, one rule) The packing-list detail's `spo_allocated_quantity` and
  the `line_status` derived from it count the same visible set. Today the endpoint overwrites the
  quantity with a filtered total while the status still derives from the unfiltered one, so one
  response can show allocated 3912 against a status computed from 8324.

- **AC-H18 [S][T]** (auditable dry run) The dry run prints one line per ROW, not per document,
  carrying the allocation id, `source_ref`, `source_doc_ref`, `created_at`, `quantity_received` and
  `receipt_status`, plus the `created_at` and `source_ref` of the OPEN sibling that justified the
  stamp. Nothing can pre-measure this set, so the dry run is the only artifact anyone reviews before
  an irreversible write, and the sibling evidence has to be spot-checkable against AutoCount.
