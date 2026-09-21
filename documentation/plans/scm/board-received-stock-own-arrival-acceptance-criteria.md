# UAC - Fulfilment board: received goods are stock, bought-for-this-line first

Plan: `PLAN-board-received-stock-own-arrival.md`. Fixture shape for every AC: one sales order with
lines L1..L6 of one product; PO lines bought for L1..L6 (`from_so_line_ref` = each line's
`source_ref`), closed, `qty_received = qty_ordered`; SPO allocations `fully_received` with
`from_po_number` = that PO; on hand at the line's location >= the received total; a second sales
order of the same product with earlier and later lines. Postgres only (`tests/_pg_fixture.py`), every
FK seeded, never a borrowed row.

## S1 Apply never fails over a vanished placement
- AC-S1-1 A pending batch row (kind delayed, undecided) whose line has no OI row and no link at apply
  time: Confirm succeeds; `result_json["released_documents"]` for that row contains "nothing to move";
  no `planning_change_reallocation_no_document`.
- AC-S1-2 Same row but the line still holds part of the frozen quantity (0 < available < freed):
  Confirm still raises 409 `planning_change_reallocation_no_document` (unchanged).
- AC-S1-3 A pending batch row whose core line `line_status` is `closed`: at apply it is marked
  superseded with reason "the sales-order line is closed" and the rest of the order applies.

## S2 Compose never re-deals a received document
- AC-S2-1 `_placed_links` on a line whose only links are received SPO allocations returns
  `po_qty = 0`, `received_qty = linked total`, `qty = linked total`.
- AC-S2-2 `compose_suggestion` for an undecided delayed line with `received_qty = 40`, `po_qty = 0`
  and a fresh answer that buys 2: no `reallocate` component; a `keep` component labelled
  "Received {document} 40".
- AC-S2-3 A line with an open (unreceived) PO link of 30 and a received link of 40, delayed beyond the
  window: the reallocate component is for 30 (the open part) only.
- AC-S2-4 (Phase 3 fix round, 21 Sep) A line with one link of 30 to an OPEN (not received) SPO
  allocation (`po_line_id` NULL, `receipt_status` not fully_received) and one link of 20 to an open
  purchase-order line with `po_line_id` set: `_placed_links` returns `po_qty = 20` (only what
  `_document_links_by_row` can re-deal), `received_qty = 0`, `qty = 50`.
- AC-S2-5 (Phase 3 fix round, 21 Sep) With AC-S2-4's shape, `compose_suggestion` for an undecided
  delayed line composes a reallocate for 20 only, never naming the SPO.

## S3 Own-arrival credit and the path picker
- AC-S3-1 Ladder for L2 (needs 20; 40 received on its own PO line; group net negative because of the
  other order): step "Can we use our locations?" answers yes with `took = 20`, the component is
  `RESERVE` on `RUNG_GROUP_TAKE` with `source = own_arrival`, and the trail `why` names the PO
  ("20 landed for this line on PO ...").
- AC-S3-2 Tier 2: L3 needs 50, its own PO line received 40, L2's PO line has 20 spare (40 received,
  L2 needs 20): L3's composition is Reserve 50 (40 own + 10 from the order's spare), Buy 0.
- AC-S3-3 The credit is capped by on hand: on hand at the location 30, own PO line received 40, line
  needs 40: Reserve 30, remainder follows today's ladder (Buy 10 or pool).
- AC-S3-4 Credit is never double counted: after L2 takes 20 and L3 takes 50, the location's free
  figure offered to the other order is reduced by 70.
- AC-S3-5 Delivered lines do not count: a closed line's PO receipt is net of that line's
  `qty_ordered` before it becomes tier-2 spare (L1: 39 received, 9 delivered -> 30 spare).
- AC-S3-6 `set_row_decision` / amend that turns an own-arrival Reserve into a Buy is refused with
  `planning_change_buy_over_own_arrival` and a message naming N and the PO; amending the remainder
  (the 10 of AC-S3-2 when no spare exists) to Buy is allowed.
- AC-S3-7 Path B: a replanned row linked 40 to a received SPO allocation, own landed 40 on hand:
  the row is settled in place, link kept, note gains "Was {qty} on {date}", `redirected_to_pool`
  stays false, no fresh row is raised.
- AC-S3-8 Path A: same row, on hand at the location 10: today's behaviour, `redirected_to_pool`
  true, fresh row raised, note carries "released at revision N".
- AC-S3-9 The board reads Received for a Path B row (line summary carries the received link qty)
  and never shows a Reallocate sentence for it.
- AC-S3-10 (added 21 Sep after the S3 coder flagged the gap) Full round trip: a batch built for
  the fixture order carries an own-arrival Reserve for L2; Confirm (`apply` -> confirm-time recheck
  `_check_line`) succeeds and the Reserve is applied, even when the group net is negative because
  of the other order. The recheck must know the credit the same way the ladder does.
- AC-S3-11 (security review, 21 Sep) The credit is drawn through the same capacity ledger as the
  ordinary assignment: on hand 40 at the location, group net POSITIVE, order A's line needs 40
  and its own PO line received 40 (credit), order B's line needs 40 from the same pile: a confirm
  covering both cannot reserve 80 from 40; the second line is refused or reduced, in both the
  ladder (compose) and the confirm-time recheck. (measured: the line served first by the
  ordinary rung takes the bin; the credit finds nothing left)
  (seams guarded: single-line floor, confirm ledger)
- AC-S3-12 (second review round, 21 Sep) Owner ruling R2: a mixed row (a received link and a
  still-open purchase-order link) that settles in place because its own-arrival credit covers the
  row's whole linked total keeps BOTH links - the received link as history, and the still-open PO
  link because shifting it off the row is purchasing's own decision at Order Inquiries, not
  something a replan makes for them. `_redirect_row_if_received` must not release the open link
  as a side effect of a credit-covered settle.
- AC-S3-13 (round-4 fix round, 21 Sep) The confirm-time credit is a second reading of the bin,
  intersected with the ordinary one, never summed: ordinary reading 40 + credit 40 on 100 on hand
  with an earlier 60-unit competitor -> Reserve 80 refused, Reserve 40 accepted.
- AC-S3-14 (round-4 fix round, 21 Sep) The replan path picker charges the own-arrival ledger with
  the linked quantity each row was measured against, not the row's qty; a second row of the same
  line keeps its share; asking the same row twice gives the same answer. (probes: row qty 30 with
  one fully-received link of 40 on a line whose own PO received 40, 40 on hand -> retained, not
  redirected off a false 30-unit cap; one line whose PO received 70 with row 1 qty 70 but only 10
  linked and row 2 qty 10 fully linked, both received -> both retained and the instance's ledger
  for that bin reads 70 - 10 - 10 = 50, not 70 - 70 - 0 = 0)
- AC-S3-15 (round-4 fix round, browser-pass finding, 21 Sep) R7's Buy-over-credit refusal is wired
  only into `set_row_decision` (the planning-changes batch amend path, AC-S3-6's own seam) - the
  ordinary board Confirm (`POST .../fulfilment-planning/confirm-all` -> `ProjectSupplyService.
  confirm` -> `_check_line`) has no equivalent check, so CS can confirm a Buy on a line whose own
  PO already landed the same units. A draft save stays lenient by design (a draft claims no
  stock, so there is nothing to refuse there). Line needs 20, its own PO line received 40, 40 on
  hand, no competing demand: a confirm naming `buy_qty=20` and no Reserve at the credited bin is
  refused 409 `planning_change_buy_over_own_arrival` (the same code `_refuse_buy_over_own_arrival`
  raises), the message naming 20 and the PO. Control: `buy_qty=5` beside `Reserve 15` when the
  credit is only 15 (on hand 15) is accepted - the refusal only bites the part that would drop
  Reserve below what is credited, never a Buy beside a credit already fully covered. (round-5,
  S-1) The message names the CREDITED quantity, the same figure `_refuse_buy_over_own_arrival`
  states for its own seam - not whatever a partial Reserve happened to leave uncovered of it:
  credit 20, Reserve 8 posted at the credited bin plus Buy 12, the refusal reads "20 landed for
  this line on PO ...", never "12 landed".
- AC-S3-16 (round-5, B-2, merge-blocking, browser-pass finding, 22 Sep) The confirm-time refusal
  follows the SAME reserve-window verdict the composer already reads (`outside_reserve_window`) -
  a line due beyond the reserve window is never credited at all, composed or confirmed, so its Buy
  is never "over" a credit that was never on offer. Line needs 20 due 400 days out (outside the
  window), its own PO line received 40, 40 on hand: `proposal_for` composes a pure Buy 20, reason
  naming the lead-time window; a confirm naming `buy_qty=20` and no Reserve is ACCEPTED,
  `lines_decided` 1 - never refused `planning_change_buy_over_own_arrival`.

## S4 Importer pairing by date order, never drop
- AC-S4-1 Sales order with open lines dated d1 < d2 < d3 < d4 and a 2026 book with two rows (dates
  between d1 and d2) plus a 2027 book with two rows (dates near d3, d4): after both imports there are
  exactly 4 OI rows, on lines 1, 2, 3, 4 in that order, each with a "Migrated from order inquiry sheet
  <book>" note and, where the line's date or qty differs from the sheet, "Was {qty} on {date}".
- AC-S4-2 Five sheet rows, four open lines: the fifth row lands on line 4 as a second row; nothing
  is dropped; the import preview counts 5 raisable.
- AC-S4-3 A closed or cancelled core line is never paired, even when it is the only qty fit.
- AC-S4-4 Re-uploading the same book restates existing rows in place (no duplicate, no skip) and the
  row count stays equal to the sheet row count for that sales order.
- AC-S4-5 SO372176 replay on the 0921 copy (manual, in the PR body): 8 rows on L2..L9 by date.
- AC-S4-7 (R10, added 21 Sep) Open lines d1 (qty 20) < d2 (qty 60); sheet rows 70 @ d1 and 40 @
  d2: the 70 lands on line 1 (raisable, note "Was 20 on d1" style qty difference, fired because
  the row exceeds the line's own ordered qty), the 40 on line 2; nothing refused as
  `qty_exceeds_ordered`. A single sheet row larger than the order's total open qty is still
  refused as `qty_exceeds_ordered`.
- AC-S4-6 (R9, added 21 Sep) A sheet row for an order whose lines are all closed or cancelled:
  preview and apply refuse it with reason `order_fully_delivered` under `line_not_found`,
  `rows_raised` 0, order not adopted, no OI row written; an order with an open line of another
  item and no open line for this item still reports `no_line_for_item`.
- AC-S4-8 (Phase 3 follow-up, 21 Sep, PASS 2 finding on the AC-S4-5 replay) A line whose sheet
  row was raised and then settled to an ACTIVE `so_supply_decisions` buy_qty/required_date
  (`_apply_settle_recovery`, AC-RB-11) still restates in place on a re-upload of the same book:
  the row count stays equal to the sheet row count, the settled row is not duplicated, and no
  new row is raised onto an open line the first upload never touched, even though the row's own
  live qty/date no longer literally matches what the sheet states for it.

## S5 Board and OI read the credit (FE, vitest)
- AC-S5-1 Board line with a composition component `source: own_arrival` renders a "Received N" chip
  with the PO number in its title; no chip when absent.
- AC-S5-2 OI worklist row retained under Path B renders the same Received state as a received link
  today (no new component).

## Browser evidence (agent-browser, once per lane, from `/` via the sidebar)
- E1 Fulfilment planning for the fixture order: Confirm succeeds; L2 shows Received 20; a Buy amend
  on it is refused with the message; the OI worklist shows the retained row not grey.
- E2 Order inquiries import preview for the two fixture books: row count equals sheet row count.

Evidence (`documentation/plans/scm/evidence/board-received-stock-own-arrival/`):
- E1a-1280.png, E1a-375.png - fulfilment planning at 1280px and 375px.
- E1a-breakdown-L2.png - L2's Received 20 breakdown.
- E1a-backing-docs-PO202510-S0101.png - the backing-documents popover naming the PO.
- E1b-refusal.png - the Buy amend refused with the R7 message.
- E1c-confirm.png - Confirm succeeding on the fixture order.
- E1d-worklist.png - the OI worklist showing the retained row not grey.
- E2-2026-preview.png, E2-2027-preview.png - the two fixture books' import preview.
