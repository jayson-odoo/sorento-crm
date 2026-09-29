# PLAN: the planning-change Confirm records the intent, purchasing moves the PO link

Status: in review, small fix track (owner ruling 29 Sep 2026), on
`crew/redeal-closed-po` (PR #1369). Lane REDEAL-CLOSED-PO. Move to `_archive/scm/` once
merged.
UAC: `redeal-closed-po-line-acceptance-criteria.md` (beside this file).

## The defect, measured

SO396347, prod (54c3b4047), 29 Sep 2026: Fulfilment planning Confirm answers
"SO396347: That purchase order line is no longer open." and "0 of 1 orders confirmed".

- 22 Sep: planning-change batch 7a9d08aa uploaded. Its rows for SO396347 carry `reallocate`
  components: 202607-S0083 SRTWT162 220 and SRTWT165 165 to the dealer pool; 202607-S0081
  SRTSA-SS 67 to SO399381 and SRTSH22712 22 to SO394121.
- Between the upload and the Confirm, both purchase orders were received line by line; the
  sync marks a fully received line `line_status = 'closed'`.
- `planning_change_service._document_links_by_row` snapshots the order's PO links before
  the confirm without reading whether each line is still open.
- `_redeal_document` drew the freed quantity off those shares and re-linked it through
  `ProjectOrderInquiryService.place_on_po_allocations` (a pool row, or a waiting row of
  another order). `_refuse_absent_target` (`project_order_inquiry_service.py:8862`) refuses
  any line whose `line_status != 'open'` with `order_inquiry_po_line_closed`.
- `apply` runs each order under a savepoint; the refusal rolls the whole order back and
  `failed_orders` names it.

## Ruling

Owner, 29 Sep 2026 (same theme as #1363): the fulfilment confirm is too restrictive. One
line's stale or conflicting source must not refuse the whole order.

Options put to the owner (crew-ask on PR #1369): (a) skip the closed share with a notice,
still re-deal the open ones; (b) gate the whole reallocate on `_redirect_row_if_received`;
(c) stop re-linking PO places from the planning side altogether. The owner chose (c),
verbatim: "yes you are right, confirm only records the intent, and purchasing makes every
link change in AutoCount, then synced back to order inquiries". Process note the same day:
"from fulfilment planning, [it] is kind of requesting it to be delayed while the link is
intact, then only purchasing will do the adjustment in the linkage".

## The change

Backend, `app/services/planning_change_service.py`:

- `_redeal_document`, `_pool_row_for`, `_take_document_shares`, `_unclaim_shares` and
  `_share_words` are deleted. No planning-change apply path calls
  `place_on_po_allocations` any more.
- `_record_redeal_intent` replaces them. For a `reallocate` of purchase-order quantity it
  touches no link and writes one notice per document on
  `result_json["released_documents"]`, walked off the row's shares in linked order:
  - an open line: `<SO> line <n>: <qty> of <PO> is for purchasing to move in AutoCount
    (<composed label>); nothing was re-linked here, the next sync brings the new link to
    Order Inquiries`;
  - a line the sync closed since compose: `<SO> line <n>: <qty> of <PO> received in full,
    goods are stock now, nothing to move; purchasing adjusts the link at Order Inquiries`
    (a line closed with no receipt reads `is <status> without a receipt` instead);
  - quantity no longer on the line: AC-S1-1's `nothing to move` sentence when nothing is
    left, `<qty> of <PO> is no longer on the line, nothing to move` when part is. The 409
    `planning_change_reallocation_no_document` (AC-S1-2) is retired.
- `_document_links_by_row` outer-joins `PurchaseOrderLine` so every share carries the live
  `line_status` and `qty_received` the wording needs.
- `_execute_reallocations` still executes a reserve move (`_move_reserve`, AC-D4, a stock
  hold) and an SPO give-back (`_release_spo_share`, D7, a CRM-side allocation); its
  `pool_cache` parameter and the hot-selling read are gone with the re-deal.
- The link on the giving line stays exactly as the confirm's own settle left it. The
  same-order survivor shift (`_shift_links_off_retired_lines`, AC-P3-6) and the confirm's
  settle (AC-P3-8 over-cover trim, a zeroed row's unlink) are unchanged: they are the
  order's own placement, not a re-deal to a stranger. Raised to the owner as a follow-up
  question on the PR, not decided in this lane.

Frontend, `project-sales/_shared/lib/boardChangeAnnotations.ts`: `whereItWentFrom` prints a
released entry that is already a sentence verbatim; a bare document number (an SPO given
back) keeps its `Released <doc> for purchasing` wrapper. Both the board's change column and
the sales-order detail read through this one function.

## Tests

Red first, then green:

- `tests/scm/test_planning_change_reallocation.py`: every Slice D test that asserted a pool
  row, a waiting-row link or an unclaim now asserts the intact link, no pool row, the
  untouched waiting row and the notice; `test_the_planning_side_never_calls_place_on_po_allocations_at_apply`
  plants the SO396347 refusal at that seam and proves it is never reached.
- `tests/scm/test_board_received_stock_s1_apply.py`: AC-S1-2 records what is left instead
  of failing.
- `tests/test_planning_changes.py`: the SO397450 advance shape records two notices and
  writes no pool row.
- `tests/scm/test_planning_change_redeal_closed_po_line.py`: the SO396347 shape (whole
  share received and closed) and a mixed open/closed shape.
- `boardChangeAnnotations.test.ts`: a bare document is wrapped, a sentence prints verbatim.

## Out of scope

Whether the confirm's own settle trim (AC-P3-8), the zeroed row's unlink and the same-order
survivor shift (AC-P3-6) should also become intent-only under the same ruling; and the
confirm-time cascade (`auto_place_for_confirmed_products`), which drafts links for rows
this confirm raised. Asked on the PR; a separate lane if the owner says yes.
