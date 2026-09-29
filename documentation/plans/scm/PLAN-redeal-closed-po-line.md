# PLAN: a closed purchase-order line in a re-deal share never fails the order's Confirm

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
- `planning_change_service._document_links_by_row` (:3081) snapshots the order's PO links
  before the confirm without reading whether each line is still open.
- `_redeal_document` (:3364) draws the freed quantity off those shares and re-links it through
  `ProjectOrderInquiryService.place_on_po_allocations` (:3356 pool row, :3457 waiting row).
  `_refuse_absent_target` (`project_order_inquiry_service.py:8862`) refuses any line whose
  `line_status != 'open'` with `order_inquiry_po_line_closed`.
- `apply` runs each order under a savepoint (:5043); the refusal rolls the whole order back
  and `failed_orders` names it.

## Ruling

Owner, 29 Sep 2026 (same theme as #1363): the fulfilment confirm is too restrictive. One
line's stale or conflicting source must not refuse the whole order: the order confirms, the
affected line is skipped with a clear notice naming the AutoCount line. Process note, same
day: from fulfilment planning the confirm records the intent while the link stays intact;
purchasing does the adjustment in the linkage.

Options put to the owner (crew-ask on PR #1369): (a) skip the closed share inside
`_redeal_document` with a notice; (b) gate the whole reallocate on
`_redirect_row_if_received`, which would also stop the open shares moving; (c) stop
re-linking PO places from the planning side altogether, a lane of its own. Built (a); it
is a strict subset of (c) for the closed-line case.

## The change

Backend, `app/services/planning_change_service.py`:

- `_document_links_by_row` outer-joins `PurchaseOrderLine` and carries `line_status` and
  `qty_received` on every share.
- `_split_closed_shares` takes every share on a non-open line out of the row's share list
  in place (the one list every component of the row consumes), so it is never drawn on,
  never unclaimed and never re-linked.
- `_redeal_document`: when the open shares cannot carry the freed quantity, the shortfall
  is recorded through `_closed_share_notices` on `result_json.released_documents` and the
  freed quantity is capped to what the open shares hold. Zero left means the row returns
  its notices and moves nothing. The `cancelled` / AC-S1-1 / AC-S1-2 branches are unchanged
  for a row with no closed share.
- Notice wording: `<SO> line <n>: <qty> of <PO> received in full, goods are stock now,
  nothing to move; purchasing adjusts the link at Order Inquiries` (a line closed with no
  receipt reads `<status> without a receipt` instead of the received clause).
- The link on the received line stays where it is: the confirm's own settle already treats
  a received link as history (AC-RL-10), and purchasing adjusts it at Order Inquiries.

Frontend, `project-sales/_shared/lib/boardChangeAnnotations.ts`: `whereItWentFrom` prints a
released entry that is already a sentence verbatim; a bare document number keeps its
`Released <doc> for purchasing` wrapper. Both the board's change column and the sales-order
detail read through this one function.

## Tests

`tests/scm/test_planning_change_redeal_closed_po_line.py` (red first, then green):

- the SO396347 shape: the whole placed share on one line, received and closed after the
  batch was built;
- an open sibling too small to carry the freed quantity, so the closed line is genuinely
  reached: the open share still moves to the pool, the closed one is skipped with its notice.

`boardChangeAnnotations.test.ts`: a bare document is wrapped, a sentence prints verbatim.

## Out of scope

Retiring the planning side's PO re-link altogether (option (c)) and the cancelled-row link
shift (`_shift_links_off_retired_lines`) on a closed line, which repoints a link directly
rather than through `place_on_po_allocations` and was not part of the reported failure.
