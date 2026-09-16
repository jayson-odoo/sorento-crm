# PLAN - OI replan with received links

Status: IN PROGRESS, 17 Sep 2026 (lane worktree branch `worktree-agent-a094ed68b05447f09`, issues #957-#961; Phase 1 FE eeea4ff4c, S1-S3 green 676d0e71c, S1b + S5 + matrix addendum implemented this round - 7 of the round's BE reds stay red, blocked on two test-fixture gaps in `_mirror_row`/`_seed_so_line`/`_purchase_order`/`_early_link` reported to the captain rather than fixed by the coder; matrix addendum and all FE (Vitest) green). UAC: `oi-replan-received-links-acceptance-criteria.md`.
Domain: SCM, order inquiries / fulfilment planning. Owner ruling 16 Sep 2026: "so far I am
okay with your proposal and we shall proceed".

## The problem, measured

SO314593 (PTL Supplies, BRW-IR) was delayed by the SO book from 01/06/2026 to 01/03/2027 and
line 1 (B2154-NL) went 182 to 220. OI-000477 line 1 is `partly_linked`: 158 on
SPO-2026/01-0143, a line closed and fully received on 19 Jan 2026 into BRW-IR. The board
proposes Buy 220 ("the delivery date is beyond the lead time window, so this line takes no
stock at all"). Confirming today runs settle-in-place, which keeps every link across the
replan: the row becomes 220 with 158 still "covered" by goods that other BRW-IR orders will
consume long before 2027. Purchasing reads 62 to buy; stock debt is short by 158.

On the 15 Sep 19:00 prod copy (`sorento_ai_automation_0915_1900`):

| linked rows | count |
| --- | --- |
| every document fully received | 4924 |
| mixed | 35 |
| every document open | 831 |

So a blanket "received means no coverage" rule would flip the whole book. The rule has to
live where the replan happens.

## Facts that shape the design (verified 16 Sep)

- The only writer of `OrderInquiryLink` is `_write_link`
  (`app/services/project_order_inquiry_service.py:4454`), reached by
  `place_on_po_allocations` (:4735, the cascade and every manual place) and by the OI sheet
  importer (`project_order_inquiry_import_service.py:1632`). Claims never create links.
- Cascade capacity per target is `qty_ordered - qty_received - already linked`
  (`_candidates_for_row` :3820 PO, :3881 SPO). A fully received document has zero capacity:
  the cascade can never link it again, to any row.
- The sheet importer skips a core line that already carries an OI row (`already_raised`,
  `project_order_inquiry_import_service.py:494/597`).
- Therefore the received link survives only through `_settle_row_in_place` (:890), which keeps
  links on the row it settles. One seam.
- `OrderInquiryRow.redirected_to_pool` (`app/models/project_so.py:986`, migration 409) means
  "real placed quantity, just not this line's any more". Readers already honour it:
  `refresh_for_decision` :653 and :685 (skips the row for settle and for `placed` netting),
  `_settle_row_in_place` :938, `planning_change_service.py:1429`,
  `order_inquiry_worklist_service.py:1216` (`taken_from_po` / `remaining_open`). It has **no
  writer** in `app/` and is true on 0 rows in prod. This plan is its first writer.
- `committed_v` in `app/services/scm/demand.py` (lateral joins at :509, :573, :691, :761,
  :841, :862) sums links per row and filters rows by `state IN ('raised','partly_linked')`.
  It does not read `redirected_to_pool`.
- "Fully received" has one copy for SPO lines: the negation of
  `app.services.scm.spo_supply.open_incoming_clauses()` (line closed, receipt status in
  `RECEIVED_RECEIPT_STATUSES`, or shipment landed). PO lines: `line_status = 'closed'` or
  `qty_received >= qty_ordered` (the same test `_candidates_for_row` :3805-3826 applies).
- Link dict (`links_for_rows` :2177-2260) and `OrderInquiryLinkOut`
  (`app/schemas/project_order_inquiry.py:37-98`) carry `late` / `late_days` but no receipt
  figure. FE readers: `documentsOf` and `DocumentsCell`
  (`orderInquiryWorklistColumns.tsx:87-180`), `OrderInquiryBackingDocumentsDialog.tsx:98-140`.
- `shortDay` (`_shared/lib/boardChangeAnnotations.ts:127`) prints no year; the sibling
  Was/Now table prints `dd/mm/yyyy`.

## Facts for S1b and S5 (verified 16 Sep, second pass)

- `from_so_line_ref` has exactly two writers, both AutoCount ESB ingest, both in place:
  PO lines in `document_ingest_service._sync_lines` (`:1339-1341`, `setattr` loop over the
  matched row, so the previous value is readable right before it) and SPO allocations in
  `shipping_order_ingest_service._write_row` (`:963-964`), plus the delete-and-recreate path
  `_supersede_xlsx_rows` (`:985`, `:1053`, `:1126`) whose new rows take the payload's ref.
  The xlsx PO book upload never writes refs. Nothing captures a before/after ref today:
  hooks receive header ids only (`ingest.py:354` `relink_to_matching_lines(written_header_ids)`,
  `:365` forward match on `spo_numbers_touched`).
- Ref resolves to `sales_order_lines.id` by exact `source_ref` match (three segments), the
  pattern in `order_link_service.write_line_ref_claims` (`:582-593`).
- Lead time per product: `ProjectSupplyService.lead_times(product_ids)`
  (`project_supply_service.py:1255`, two grouped queries, memoized; `None` means nobody
  says, callers fall back to `DEFAULT_LEAD_TIME_DAYS`). Module-level import into the
  worklist service is safe (precedent `scm/stock_debt_service.py:46`).
- Worklist page assembly (`order_inquiry_worklist_service.list_rows` `:1093-1105`): one row
  query, then five bulk maps handed to a query-free `_serialize`. A suggestion map keyed by
  product is a sixth, same pattern.
- The cascade's linkable-row predicate (`auto_place_for_products` `:5253-5271`: state in
  raised / partly_linked, verb in `_LINKABLE_VERBS`, ack in `ACK_LINKABLE`, then
  `_narrow_to_products`) is the one query a "sooner rows for this item" lookup reuses.

## The rule

**A fully received document does not carry an OI row through a replan.** At settle-in-place,
when the row's links include one whose document is fully received:

1. the row is redirected: `redirected_to_pool = True`, note appended, `qty` /
   `delivery_date` / `state` / links untouched (history purchasing was told);
2. links to still-open documents are removed from it (`_remove_links`), so their capacity
   returns and the raise-time cascade may draft them onto the replacement;
3. `_settle_row_in_place` returns False; the existing netting skips the redirected row
   (:685) and raises a fresh `ORDER` row for the full need through the existing raise path
   (:700-735), which the raise cascade links only where capacity exists (none on a received
   document).

No composition test: whether the board reserved stock, borrowed, or bought, goods that have
landed are location stock and the board's rungs are the only truth about them. No new
column, no tombstone, no AutoCount change.

## Slices

### S0 - year in "What changed" (FE, one function)

`shortDay` returns `D Mon YYYY`. Existing Vitest for `boardChangeAnnotations` updated.
Covers AC-RL-01.

### S1 - received figure on links (BE + FE)

- `links_for_rows` selects `PurchaseOrderLine.qty_received`, `SPOAllocation.quantity_received`,
  `SPOAllocation.receipt_status`, `SPOAllocation.line_status`, `InboundShipment.actual_arrival_date`
  (the join it already has for `expected_date` extends), emits `received_qty` and `received`.
- `OrderInquiryLinkOut` gains both fields. Frontend type `OrderInquiryLink` gains both.
- `DocumentsCell` prints the `received` mark and title; the dialog prints `received N`.
- Covers AC-RL-02, AC-RL-03, AC-RL-17.

### S2 - the rule at settle (BE)

- In `_settle_row_in_place`, before the over-cover step: load the row's links with their
  documents (one grouped query, reuse the select from S1's `links_for_rows` or
  `_links_by_row` plus a receipt lookup). If any link is fully received: redirect per the
  rule above, return False. Note text per AC-RL-10.
- The raise path already produces the replacement row. Assert `previous_*` null on it.
- Covers AC-RL-10, AC-RL-11, AC-RL-12, AC-RL-13, AC-RL-14, AC-RL-18.

### S3 - readers honour the redirect (BE + FE)

- `demand.py`: every `committed_v` leg over `order_inquiry_rows` adds
  `AND NOT oir.redirected_to_pool` (six places; one helper string, not six spellings).
- `order_inquiry_worklist_service.py`: stage totals (`_incoming_qty`, `_purchased_qty`, the
  Buy total) and `_serialize` exclude / flag the redirected row; `redirected_to_pool` reaches
  the FE row (add to `_serialize` and to the FE row type).
- The Order Inquiries schedule matrix (#951) also reads `_stage_rows`; its Purchased / Incoming
  cards exclude the redirected row the same way.
- FE: `redirected` mark on the Qty cell; card totals ignore the row.
- Covers AC-RL-04, AC-RL-15, AC-RL-16, AC-RL-16b.

### S1b - repoint suggestion on an open link (BE + FE)

Owner ruling 16 Sep: a concrete instruction, never a reason. "Early" is not shown.

- Trigger per open link: `expected_date <= row.delivery_date - lead_time_days(product)`
  (fallback `DEFAULT_LEAD_TIME_DAYS`); received links and links inside the window get no
  suggestion.
- Candidate rows: same product, cascade predicate above, on a different SO line, with
  `_unlinked_need > 0`, `delivery_date < row.delivery_date`. Pick earliest `delivery_date`,
  tie by larger open need. One grouped query per page keyed by product.
- Link dict gains `suggestion`: `{"kind": "repoint", "inquiry_no", "item_code",
  "so_number", "delivery_date", "open_qty"}` or `{"kind": "unlink"}` or null.
  `OrderInquiryLinkOut` declares it.
- FE: chip carries a muted `repoint` / `unlink` word; hover or tap opens a popover with the
  instruction, e.g. `Repoint to OI-000539 · CB2805A-DIY · needed 01/12/2026 · open 90` or
  `Unlink · no sooner inquiry needs this item`. Nothing is written from the popover:
  purchasing acts in AutoCount, S5 follows.
- Covers AC-RL-20 to AC-RL-24.

### S5 - our link follows the book pairing (BE + FE)

Owner ruling 16 Sep: `from_so_line_ref` is the source of truth; whenever it changes, our
link on a row reflects it. Manual links follow too.

- Capture: `document_ingest_service._sync_lines` and `shipping_order_ingest_service.
  _write_row` record `(target_kind, target_id, old_ref, new_ref)` whenever the ref changes
  (including to null); `_supersede_xlsx_rows` records the superseded row's ref against the
  new row. One list on the service, exposed like `written_header_ids`.
- Hook: `ingest.py` runs `ProjectOrderInquiryService.follow_book_repairing(moves,
  trigger="autocount_ingest")` after the relink hook for POs and beside the forward-match
  hook for SPOs.
- Rule, per move, skipping a fully received document: every link on that target whose row's
  core SO line is the OLD line is removed through `_remove_links` with the note
  `AutoCount moved <document> to <SO new> on <date>`; if the NEW line resolves to a linkable
  row (cascade predicate) with `_unlinked_need > 0`, the same document is placed on it through
  `place_on_po_allocations` for `min(freed qty, need)`, `auto=True`. A new ref of null only
  removes.
- FE: the old row's note reaches the existing Qty-cell annotation dialog
  (`OrderInquiryQtyAnnotationDialog`), which already shows settled / rejected notes; no new
  trigger on an empty documents cell (ruling 16 Sep).
- Covers AC-RL-40 to AC-RL-46, AC-RL-32.

### S4 - E2E on the 15 Sep copy

AC-RL-30, AC-RL-31, AC-RL-32 as a recorded agent-browser run.

## Testing seams (agree before Phase 2)

- Settle: `tests/test_order_inquiry_draft_links.py` (owns the settle harness) - new
  `test_settle_redirects_row_with_received_link_and_raises_fresh_buy`,
  `test_settle_keeps_row_with_open_links`, `test_settle_mixed_links_frees_open_link`.
- Cascade guard: same file, `test_cascade_writes_nothing_onto_redirected_row`.
- Importer guard: `tests/test_oi_sheet_pairing_repair.py` beside `test_ac_r_16`,
  `test_reupload_skips_redirected_row_and_its_replacement`.
- Demand: `tests/scm/` where `committed_v` is already exercised (grep `committed_v`), new
  `test_committed_v_ignores_redirected_row`.
- Worklist: `tests/test_order_inquiry_worklist.py`, `test_stage_totals_ignore_redirected_row`,
  `test_link_dict_carries_received_qty_and_received`.
- FE Vitest: `boardChangeAnnotations.test.ts` (year), `orderInquiryWorklistColumns` render
  test for the `received` and `redirected` marks.
- S1b: `tests/test_order_inquiry_worklist.py`, `test_link_suggests_repoint_to_soonest_open_row`,
  `test_link_suggests_unlink_when_no_sooner_row`, `test_no_suggestion_inside_lead_time_or_received`.
- S5: `tests/test_ingest_documents_v5_so_po_links.py` (reuse `_po_line(env, from_so_line_ref=)`,
  `_seed_so_line`, the repush template at `:550-565` and its SPO twin `:567-581`),
  `test_po_line_ref_moved_follows_to_new_line_row`, `test_po_line_ref_moved_no_row_unlinks_only`,
  `test_spo_ref_moved_follows`, `test_received_document_ref_move_changes_nothing`,
  `test_ref_cleared_unlinks`, `test_manual_link_follows_book`.

## Migration

One: `512_committed_v_redirect_exclude` re-freezes the `scm.committed_v` view body with the
redirected-row exclusion (the view lives in a migration; 511's body is kept for the downgrade).
No new column: `redirected_to_pool` exists since 409. Re-parent onto main's head before merge.

## Rollout

Rule fires only inside a board confirmation on a line whose row carries a received link.
Existing 4924 rows are untouched until their own line is replanned. `committed_v` change
affects only redirected rows, zero today.

## Backlog (not this plan)

- One-step undo of a confirmation: cancel the newest supply decision revision, restore
  `previous_qty` / `previous_delivery_date` on settled rows, cancel rows that revision raised,
  flip its batch rows back to `pending`. Data exists; needs its own journey.
- (BL-064 `early_days` superseded by S1b: the suggestion replaces the label.)
