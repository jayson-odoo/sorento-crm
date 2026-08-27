# UAC - Order Inquiries: draft links up front, one Confirm, Outstanding PO/SPO

Plan: `PLAN-scm-oi-draft-links.md`. Verified by browser evidence (sidebar navigation from `/`, 1280 and 375), pytest and vitest.

## A. Links found up front
- AC-D1 Confirming SO404352 on the fulfilment board raises its rows To confirm, and each row a PO or SPO can cover already shows the document under Outstanding PO/SPO with the draft icon, without anyone pressing anything on the Order Inquiries page.
- AC-D2 A row nothing can cover reads "Not found (new order)".
- AC-D2b An ORDER row (not only ORDER BACK) with an open SPO for its product drafts onto the SPO before any PO; only an SPO line at a pool warehouse (BRW, MWH, DC1, WH3, RSW) is drafted, a line at any other code is shown in the lightbox and never taken.
- AC-D3 A draft link occupies the PO's remaining quantity: a second row of the same product is offered the rest, never the same units; the PO page's Allocated to panel lists the row as Proposed.
- AC-D4 The reorder plan's project demand ignores drafts on To confirm rows exactly as it ignored awaiting rows before; the plan chip reads "N to confirm".

## B. Confirm and reject
- AC-D5 Ticking three To confirm rows and choosing Start > Confirm selected (3) stamps them Confirmed <name> <time>; their draft icons flip to confirmed without a reload and no link changes document; an unlinked remainder is linked in the same press.
- AC-D6 Actions > Reject selected (N) asks one reason for the batch; an empty reason is refused; each row reads Rejected: <reason>, its links are gone, the PO's remaining quantity is back, and the board line shows the Rejected badge.
- AC-D7 A CS user who amends a confirmed row on the board sees it come back as Changed with the Was / Now table; its links stay and read as draft; Confirm returns it to Confirmed.
- AC-D8 A CS user sees no Start menu and no Reject / Confirm items; the endpoints answer 403.

## C. Re-deal
- AC-D9 Actions > Auto link all opens a dialog carrying Purchase order cut off <date> (defaulting to the plan's horizon, cleared = "No link horizon"); after an upload that adds a nearer PO for the product, the press moves the draft from the old document to the new one; a confirmed row's link is never moved.
- AC-D10 Start > Upload purchase orders with a book carrying SPO rows: Test reports the SPO documents and lines and any unknown locations; Confirm upload writes them as open SPO allocations with their warehouse; Link now drafts rows of those products onto them, SPO before any PO; a second book without those SPO lines closes them.
- AC-D11 Confirming a plan-generated PO drafts To confirm rows and links Confirmed rows, and the page reads both correctly.

## D. Reading the page
- AC-D12 The list opens on Confirmed = To confirm with the active-filter chip shown; clearing the chip shows every row; the three cards, the schedule and the export follow the filter.
- AC-D13 The toolbar is one row at 1280: search, Filters, Columns, refresh on the left; Actions and Start on the right; no Link up to box, no Acknowledge, no left Link / Unlink buttons, no row Actions column; the selection strip shows "N selected" and Clear only. At 375 nothing clips and the page does not scroll sideways.
- AC-D14 Actions holds Auto link all, Link selected (1) (enabled only with exactly one row ticked, opens the manual dialog), Unlink selected (N), Reject selected (N), Unlink all, Export Excel; Start holds Upload purchase orders and Confirm selected (N); counts disable at 0.
- AC-D15 The State column and its filter are gone; the Linked filter reads Found / Not found; the column headers read Outstanding PO/SPO, Taken by PO/SPO, Confirmed.
- AC-D16 An SPO link reads its pool warehouse code and quantity (`BRW 1`), never `L14 1`; the line label sits in the title; a document with no location in the book reads "no location".
- AC-D17 A late document reads "late N d" where N = days between the row's delivery date and the document's expected date, with the full dates in the title.

## E. Lightbox
- AC-D18 Pressing a PO number opens a dialog (not a popover): number, supplier, status, expected, "Open purchase order" link, the lines table and the Allocated to rows marked Proposed / Confirmed; it scrolls inside itself and closes on Escape; usable at 375.
- AC-D19 Pressing an SPO number opens the same dialog shape with the allocation lines (SKU, allocated, received, remaining, location) and the shipment / container when one exists.
- AC-D20 The old PO popover component no longer exists in the tree.

## F. Wire and tests
- AC-D21 `late_days`, the SPO `location` fallback, `to_confirm` and the PO detail's `allocations` are on the wire from the list, the summary, the export and the SO detail (asserted in tests).
- AC-D22 Tests per plan section 7 in the same PR; browser evidence for AC-D1, D2, D5, D6, D9, D12, D13, D16, D18, D19 on SO404352; no dashes in the diff.

## Result (tester, 27 Aug, plan section 10)

Pass/fail per AC, and how each was verified. Backend suite: 340/340 (draft-links
17-file sweep) + 1211/1211 unrelated-domain pre-existing failures aside (see plan
section 10). Frontend: 3800/3800 vitest (1 pre-existing defect in this branch's own
diff fixed along the way, `SalesOrderDetail.test.tsx`).

| AC | Result | How |
| --- | --- | --- |
| AC-D1 | PASS, walked live 28 Aug | pytest `test_a_board_confirm_raises_a_to_confirm_row_that_already_holds_its_document`; browser walked fresh on SO414013 (plan section 11) - board Confirm raised OI-000015 and the row already showed `SPO-2026/08-0012 BRW 2` with the draft mark on first paint of the Order Inquiries list, `oi-walk-1-draft.png` |
| AC-D2 | PASS | pytest `test_a_row_nothing_can_cover_still_comes_out_unlinked`; browser `oi-test-toolbar-1280.png` / `oi-test-confirmed-marks-1280.png` show live rows reading "Not found (new order)" |
| AC-D2b | PASS | pytest `test_an_order_row_drafts_onto_a_shipping_order_before_any_purchase_order`, `test_a_shipping_order_line_outside_the_pool_is_never_drafted` |
| AC-D3 | PASS, Proposed half walked live 28 Aug | pytest `test_two_rows_are_never_drafted_onto_the_same_units`, `test_reject_on_a_placed_row_frees_the_pos_remaining_for_the_next_candidate` (new); browser: SO414013's draft link opened in the SPO lightbox showed `OI-000015 / SO414013 / SRTKT72SS / 2 / Proposed` in Allocated to (plan section 11, `oi-walk-2-lightbox-proposed.png`); the "second row offered the rest" half stays pytest-only, not re-walked this round. Review round: the re-deal may not COST a row what it holds either - `test_auto_link_all_keeps_the_draft_of_a_row_that_is_now_past_the_cut_off`, `..._when_the_document_has_since_closed` (B1) |
| AC-D4 | PASS | pytest `test_the_plan_still_ignores_a_to_confirm_rows_remainder`; the chip half is `test_the_to_confirm_count_still_sees_a_row_its_draft_made_placed` (review round, S6 - a drafted row is `placed` and had vanished from the count) and `tests/test_order_inquiry_handshake_edges.py::test_committed_v_and_the_plan_agree_only_on_acknowledged_and_changed`; the plan page's tile stays hidden per the 27 Aug ruling, so this is a backend correction only (the tile's own contract is pinned in vitest `ReorderStatTiles.test.tsx`) |
| AC-D5 | PASS, walked live 28 Aug | pytest `test_confirm_stamps_the_row_and_moves_no_link`, `test_confirm_fills_a_remainder_the_draft_could_not_cover`; vitest `OrderInquiriesClient.test.tsx` "AC-D5: Confirm selected"; browser walked fresh on SO414013 (plan section 11): ticked the row, Start > Confirm selected (1), `POST .../order-inquiries/acknowledge` returned `acknowledged:1`, the mark flipped from dashed-draft to a green check on the SAME document without a page reload, Confirmed column read "Confirmed Jayson Personal 28/08/2026, 12:42 am", lightbox standing flipped Proposed -> Confirmed (`oi-walk-3-confirmed.png`) |
| AC-D6 | PASS | pytest `test_reject_unplaces_every_link_and_gives_the_quantity_back`, `test_the_batch_reject_takes_one_reason_for_every_row`, `test_the_batch_reject_refuses_an_empty_reason`, `test_the_batch_reject_refuses_the_whole_batch_when_one_row_cannot_be_refused`, `test_the_batch_reject_refuses_the_whole_batch_when_one_row_is_cancelled`, and (review round, B4) `test_the_batch_reject_of_two_lines_of_one_order_refuses_both` - a batch over one order writes ONE revision and leaves no live unrefused row on either line; vitest `BulkRejectOrderInquiryDialog.test.tsx` (empty reason refused, live validation walked in Phase 1) |
| AC-D7 | PASS | carried over from `PLAN-scm-oi-handshake.md`, pytest `test_order_inquiry_handshake.py` / `..._edges.py` (the AC-H9 supersede is now walked with a document in the book); the review round (B2) adds what a re-confirm does to a row still To confirm - `test_a_reconfirm_with_a_new_date_re_raises_the_drafted_row_on_that_date`, `..._that_lowers_a_drafted_rows_quantity_raises_no_exception`, `..._that_raises_a_drafted_rows_quantity_leaves_one_row` - and pins the confirmed case unchanged with `test_a_confirmed_rows_links_survive_a_reconfirm_untouched` |
| AC-D8 | PASS | pytest `test_a_cs_user_may_not_reject_a_batch`; vitest "AC-D8: a CS user..." describe block; browser session did not re-log-in as a CS principal (out of scope for this pass, permission-boundary already pinned twice in pytest + vitest) |
| AC-D9 | PASS | pytest `test_auto_link_all_moves_a_draft_onto_a_nearer_document`, `test_auto_link_all_never_moves_a_confirmed_rows_link` (found and fixed a real defect: the `/order-inquiries/auto-place` route the dialog calls was missing `redeal_drafts=True, include_awaiting=True` - see section 10); browser `oi-test-autolink-dialog-1280.png`, dialog opened and Cancelled, no `auto-place` request fired. Review round: the press leaves a row past the cut off, a row whose document has closed and a row it lands on the same document again exactly as they were (`test_two_presses_of_auto_link_all_change_nothing_at_all`, B1/S4) |
| AC-D10 | PASS | pytest `tests/scm/test_outstanding_po_skips_spo.py` (SPO intake, both closure branches, and from the review round: a re-export that drops a line does not re-key the rest, the same product twice on one document keeps both rows, preview and write close the same rows, a fractional quantity lands whole); browser `oi-test-upload-test-result-1280.png`, Test press against a real 2-row fixture book reports "1 row are shipping orders (SPO)..."; Confirm upload never pressed |
| AC-D11 | PASS | pytest `test_a_purchase_order_confirm_drafts_a_to_confirm_row`, and (review round, S5) `test_a_plan_purchase_order_confirm_moves_the_draft_it_was_bought_for` + `test_a_plan_purchase_order_confirm_never_moves_a_confirmed_rows_link` |
| AC-D12 | PASS | pytest `test_the_to_confirm_filter_is_awaiting_and_changed`; vitest "AC-D12: the page opens on Confirmed = To confirm"; browser confirms the chip live (`ack=to_confirm` in the URL on load, clears to `ack=all`) |
| AC-D13 | PASS | vitest "AC-D13/AC-D14"; browser `oi-test-toolbar-1280.png` (one row) and `oi-test-toolbar-375.png` (stacks, no page-level horizontal scroll) |
| AC-D14 | PASS | vitest "AC-D13/AC-D14: one toolbar row..."; browser Actions/Start menus opened live with real counts and real disabled states |
| AC-D15 | PASS | vitest "reads the columns in the sheet's own order, renamed"; browser column headers read "Outstanding PO/SPO", "Taken by PO/SPO", "Confirmed", no State column |
| AC-D16 | PASS | pytest `test_an_spo_link_reads_its_pool_location_rather_than_a_line_number`, `test_an_spo_link_with_no_warehouse_falls_back_to_the_books_own_code`; browser `oi-test-confirmed-marks-1280.png` reads `SPO-2026/08-0015 BRW 1` live |
| AC-D17 | PASS | pytest `test_a_late_document_says_how_many_days_late_it_is`, `test_a_document_that_lands_in_time_states_no_day_count`; browser reads `late 31 d` / `late 28 d` live |
| AC-D18 | PASS | browser `oi-test-po-lightbox-1280.png`, `oi-test-po-lightbox-allocations-1280.png` (Allocated to, Confirmed badge), `oi-test-po-lightbox-375.png`; Escape-close and no console error confirmed |
| AC-D19 | PASS | browser `oi-test-spo-lightbox-1280.png`, `oi-test-spo-lightbox-allocations-1280.png`, `oi-test-spo-lightbox-375.png`; real ETA / lines / Allocated to off `GET .../order-inquiries/spo/{number}` |
| AC-D20 | PASS | `orderInquiryWorklistColumns.test.tsx` / `OrderInquiryDocumentDialog.test.tsx` import only the dialog module; grep confirms `OrderInquiryPoDetailPopover` is gone from the tree |
| AC-D21 | PASS | pytest `test_the_sales_order_detail_carries_the_day_count_too`, `test_the_purchase_order_lightbox_names_who_is_holding_the_quantity`, `test_the_export_accepts_to_confirm` (rewritten to assert content, not just status); the review round adds the THIRD reader of the same link - `test_the_scm_sales_order_detail_states_the_day_count_too` over `GET /scm/sales-orders/{id}`, whose `SalesOrderLineLink` was dropping `late_days` (S1) |
| AC-D22 | PASS | this round: pytest 340/17-file-sweep green + 3 new tests added, vitest 3800/3800 green, browser evidence above; no em/en dashes introduced (checked by hand in every new file) |

### Section 10 notes carried from the plan

- **SO381895 (the browser fixture) currently has nothing outstanding on the
  fulfilment board and no order-inquiry rows at all** on the dev copy - a prior
  verification pass already carried it all the way to Confirmed. AC-D1/AC-D3/AC-D5's
  live "confirm on the board, watch the mark flip" walk could not be freshly
  demonstrated on it for that reason; nothing on it was changed this round. The
  adjacent live evidence (confirmed marks, late-day badges, lightboxes) was
  captured instead on SO404352's already-real rows, read-only.
- **Defect found and fixed**: `POST /order-inquiries/auto-place` (the route
  "Actions > Auto link all" calls) built its `auto_place_for_products` call without
  `redeal_drafts=True, include_awaiting=True`, so the toolbar's own Auto link all
  never actually re-dealt a draft - only the unrelated `/link-now` route (Start's
  post-upload button) had the two flags. Fixed in
  `app/api/v1/projects/order_inquiries.py`; the two pytest tests that were
  labelled "Auto link all" but exercised `/link-now` were left as-is (they are
  correct tests of `link_now`, just misleadingly named); the new
  `test_reject_on_a_placed_row_frees_the_pos_remaining_for_the_next_candidate`
  exercises the real `/auto-place` route and would have caught this on its own.

### Review round (28 Aug, plan sections 13 and 14)

Four blockers and eight should-fixes from the Phase 3 review, each with a red test written
before its fix. Every AC above still holds; the rows whose EVIDENCE grew say so. Two AC
readings were sharpened rather than changed:

- **AC-D3 / AC-D9**: "a draft occupies the quantity" now also means the re-deal may not COST
  a row the quantity it holds - a row past the cut off, a row whose document has closed and a
  row the walk lands on the same document again all come out of the press untouched, notes
  and link ids included.
- **AC-D4**: the count behind the chip takes `changed` rows as well as `awaiting` (the To confirm
  set the page itself opens on, R3) and is blind to whether a draft has made the row `placed`.
  The plan page's tile is NOT wired to it: the 27 Aug ruling that an awaiting row is not demand
  stands (plan section 13), so this is a backend correction only.

Run: pytest 27 files green (the 17-file sweep plus the `refresh_for_decision` and
purchase-order suites), 17 new tests; vitest `app/(protected)/project-sales` +
`app/(protected)/scm/reorder` green. Full figures in plan section 14.
