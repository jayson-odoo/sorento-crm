# PLAN: a retired SPO line is invisible everywhere, not only on the five readers we measured

Status: IN PROGRESS 2026-09-08. UAC: `hide-retired-everywhere-acceptance-criteria.md`.
Follows #753, which shipped `spo_supply.visible_line_clauses()` and applied it to five readers.

## 1. Why this exists

#753's plan listed "the display read sites" after measuring ONE service. The user opened the
order-inquiry document dialog on SPO-2026/09-0036 and the retired C-FHSS14 line of 4412 was still
there. The enumeration was the defect, not the rule.

A full sweep of all thirty backend files that query `spo_allocations` puts nineteen call sites in
the user-facing bucket. Eight already carry the clause. Eleven do not, plus the embedding pipeline.

Retirement always sets a non-open line status as well (the leftover sweep sets both; the DocKey
path runs only after the guard proved no other DocKey row is open, and `line_status` is NOT NULL
with an `open` default). So every reader that requires an open line already excludes retired lines
transitively. The exposed readers are exactly those with no open-status test.

## 2. Rules

- **R7 One predicate.** Every user-facing read of `spo_allocations` applies
  `spo_supply.visible_line_clauses()`. R2 rides inside it, so a retired line carrying a receipt
  stays visible at every new site automatically.
- **R8 A retired line is not a fact the chatbot may state.** The MCP tools and the reference
  resolver take the clause. A number whose every line is retired does not resolve as a live entity.
- **R9 A retired line leaves the vector store.** Retirement fires `after_update`, so the worker
  currently re-embeds the row and re-activates its document, leaving text with no retirement marker
  quotable in any answer. A hidden row's document is deactivated instead, and the backfill skips it.
- **R10 Planning arithmetic with no open test is a defect, not a carve-out.** Two purchasing reads
  have no line-status test at all, so they credit cover that AutoCount deleted. They take the
  clause. For a retired-only allocation the correction removes phantom cover and grows the shortfall. It is
  NOT a universal guarantee: the pro-rate means removing a hidden claim can raise another pool's
  share, which is the honest answer since a deleted claim should stop competing for the same water.
- **Unchanged from #753:** id-resolved reads, writers, the ingest, the deletion service and the
  receipt recompute stay unfiltered (R3), and `refresh_shipment_line_statuses`' persisted column
  stays unfiltered because the reorder engine nets it (AC-H17 as narrowed).

## 3. The sites, worst first

| # | file:line | function | why it matters |
| --- | --- | --- | --- |
| 1 | `order_inquiry_worklist_service.py:994` | `get_spo_detail` | the reported bug; retired lines also feed the header's ETA, supplier and container |
| 2 | `purchase_order_service.py:193` | `_unshipped_spo_query` | MCP tool `crm_procurement_po_placed_list`; no open test at all, so the chatbot states a retired quantity as fact |
| 3 | `embedding_worker.py:377`, `embedding_backfill_service.py:225`, `embedding_change_listener.py:194` | the embedding trio | R9; the only site where the stale text persists after the query is fixed |
| 4 | `entity_resolver.py:1395`, `:2030` | `_probe_spo`, `_prefix_probe_spo` | a retired-only number resolves as a live entity |
| 5 | `scm/spo_supply.py:116` | `spo_history_for_product` | the plan row's popover, in the module that defines the clause |
| 6 | `scm/purchase_order_service.py:309` | `_spo_takes_of` | tells a buyer their goods are on a container, off a deleted line |
| 7 | `scm/coverage_service.py:495` (`ship_rows`, :650) | `_supply_events_many` | R10; credits a pool with cover that does not exist and suppresses the purchase that should follow |
| 8 | `procurement_service.py:945` (:961) | `list_shipments` `spo_counts` | the count disagrees with the filtered grid beside it |
| 9 | `project_order_inquiry_service.py:2010`, `scm/spo_conversion_service.py:1117` | `links_for_rows`, `_project_coverage` | the "Linked to" column prints a retired number |
| 10 | `scm/spo_conversion_service.py:857`, `:2522` | `coverage_for_so_lines`, `_own_state` | SO-line cover strip and received rollup |
| 11 | `spo_last_receipt_service.py:41` | `last_receipt_rows` | MCP tool; narrow, needs a retired row marked fully received with a zeroed receipt |
| 12 | `scm/stock_debt_service.py:637` | `_holds` | prints a retired number on a hold row |

## 4. Decisions still open, listed not guessed

- `scm/order_link_service.py:152` `_purchase_side` resolves a claim's TARGET, so filtering changes
  linking behaviour rather than a display. Ruling: filter it, because pointing a person's claim at a
  line AutoCount deleted is worse than refusing to.
- `procurement_service.py:1013` `get_received_quantities_by_product` collects SPO numbers from every
  allocation on a shipment to find receipts. Filtering could drop a REAL receipt rather than hide a
  phantom. Ruling: leave it, and record why: it looks up receipts by number, and a receipt found
  through a retired line is still a receipt.
- `entity_resolver`'s `DISTINCT` can hand back a retired row's id even when a live sibling exists.
  Ruling: prefer a visible row's id; resolve to nothing only when every line is retired.

## 5. Slices

- S1 the nine display readers (1, 5, 6, 8, 9, 10, 12 above) plus `_purchase_side`.
- S2 the chatbot surfaces (2, 4, 11).
- S3 the embedding trio (3), including deactivation on retirement.
- S4 the purchasing arithmetic (7), with the direction of the change stated in the PR.

## 6. Round 2 rulings (security review, 2026-09-08)

- **The deactivation was one-way.** Retiring a line deactivates its document, but the un-retire is a
  restatement of identical values, so the worker's `source_hash` is unchanged and it returns
  `skipped` before ever reaching `is_active = True`. The line stays out of retrieval permanently,
  with no repair path, since a backfill enqueue hits the same skip. Fix: the skip branch re-activates
  an inactive document before returning. The reviewer's alternative, adding `retired_at` to the
  canonical body, does not work in either direction and is recorded in AC-E15 so nobody tries it.
- **`_own_state` is a writer's view, so it is not filtered.** It feeds the SPO edit save as well as
  the planner display. A save that cannot see a hidden allocation would neither update nor delete it
  and would insert a second row for the same (shipment line, warehouse). Unreachable on today's data
  (no allocation carries a `po_line_id`), which is exactly the reasoning that produced the defect
  this lane exists to fix, so it is corrected rather than named as a residual. The filter moves to
  the display consumer. R7 is amended: a user-facing READ takes the clause; a read that a WRITE
  depends on never does.

## 7. Round 3 (reviewer, 2026-09-08)

- The one-way deactivation has a second reachable path the round-2 ruling did not name: a retired
  line that later takes a receipt becomes visible under R2, and its document stays inactive for the
  same hash reason. The skip-branch repair covers both; both get a test.
- `_spo_cover_by_so_line` is filtered alongside `coverage_for_so_lines` (AC-E17), so the planner and
  the "Linked to" column cannot name different SPOs for one line.
- Deliberately left, now named so the next sweep does not re-open it:
  `incoming_stock_service.py:953-963` collects distinct SPO numbers off a shipment to find
  goods-received notes. It prints picking numbers rather than SPO numbers and falls under the
  AC-E14 rule, that a receipt found through a retired line is still a receipt.

## 8. Round 4 (security review, 2026-09-08)

The display/writer split has one asymmetry: what the display hides, the browser cannot send back,
and `revise` reads that absence as "delete it". So hiding a row could hard-delete it on the next
unrelated save. Unreachable on today's data, since no allocation carries a `po_line_id`, and the
safe side of the two failure modes. Fixed anyway (AC-E18): "unreachable today" is the reasoning
that produced the defect this lane exists to fix, and I rejected it once already in section 6.
R7 gains its third clause: a user-facing read takes the clause, a read a writer depends on never
does, and a WRITE never treats the absence of something we hid as an instruction.
