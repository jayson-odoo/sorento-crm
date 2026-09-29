# UAC: a closed purchase-order line in a re-deal share never fails the order's Confirm

Plan: `PLAN-redeal-closed-po-line.md`. Lane REDEAL-CLOSED-PO, PR #1369. Owner ruling
29 Sep 2026.

Vocabulary: a SHARE is one `{po_line_id, document, qty}` entry `_document_links_by_row`
reads off a planning row's line before the confirm; a CLOSED share is one whose
purchase-order line has `line_status != 'open'` at apply time.

- AC-RC-1 [BE][T] Given a pending batch row with a `reallocate` component whose whole placed
  share sits on one purchase-order line, and that line is received in full and closed
  after the batch was built, when the batch is applied, then `failed_orders` is empty,
  `applied_orders` names the order, and the row's `applied_state` is `applied`.
- AC-RC-2 [BE][T] Same as AC-RC-1: the row's `result_json.released_documents` carries a
  notice that names the sales order and line number, the purchase order, the quantity, says
  the quantity was received and that nothing was moved.
- AC-RC-3 [BE][T] Same as AC-RC-1: no link is written onto the closed line by the apply.
  Every link it carries afterwards belongs to the line's own row.
- AC-RC-4 [BE][T] Given a row placed on two lines, one open and too small to carry the whole
  freed quantity and one received and closed, when the batch is applied, then the open
  share is re-dealt exactly as before (a pool row linked to the open line only, the open
  line never over-linked), the closed share is skipped with its notice, and
  `executed_reallocations` never names the closed document.
- AC-RC-5 [BE] A row with no closed share behaves exactly as today: AC-S1-1 (placement
  vanished, "nothing to move") and AC-S1-2 (partial placement, 409
  `planning_change_reallocation_no_document`) are unchanged.
- AC-RC-6 [FE][T] `whereItWentFrom` prints a released entry that already is a sentence
  verbatim, and still wraps a bare document number as `Released <doc> for purchasing`.
- AC-RC-7 [UI] On the fulfilment planning board, after Confirm on such an order, the
  toast reads "1 of 1 orders confirmed" and the row's "Where it went" list shows the notice
  beside the moves that did happen.
