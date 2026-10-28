# PLAN: product swap as Was/Now, and email = confirm preview = attachment

Status: built, in review (small fix track: no migration, no auth/RBAC change, no new ingest surface)
Lane: PRODUCT-CHANGE-TALLY

## Owner report (28 Oct)

SO426847 line 48: AutoCount edited the line's product in place (same line key), SPSRT61-CR to
SRT61-CR. The Order Inquiry EMAIL shows ITEM CODE (old) and NEW ITEM CODE (new). The confirm
popup preview did not show the old and new product columns, and the board / SO page show the
product swap only as a sentence, not as a row in the yellow Was/Now table next to Qty and Date.
Owner, mid-lane: "we just need to fix the change of product code, don't overextend".

## Where each surface reads the line

- Board and SO page: `BoardChangeTable` / `BoardChangeWasNowTable`, rows from `changedFieldsOf`
  (`project-sales/_shared/lib/boardChangeAnnotations.ts`). The SO page builds its annotation in
  `scm/sales-orders/[id]/components/salesOrderLineChange.ts`.
- Email: the `order_inquiry_handover_default` template prints ITEM CODE = `was.item_code` else
  `item_code`, NEW ITEM CODE = `item_code` when `was.item_code` (migrations `oihr_0006`..`0010`).
- Attachment: `handover_xlsx` (`order_inquiry_worklist_service.py`), written from the email's own
  `handover.lines`, so it already printed the email's columns.
- Confirm preview: `ConfirmGuideDialog` draws `LineSplitEditor` / `SplitLinesSheet`
  (`LineSplitSheet.tsx`) off the split read (`LineSplitService.read`, rows from `line_plans`).
  It had no NEW ITEM CODE and the read never sent the old code (only used it for REMARK).

## Done

1. Product is the first row of the yellow Was/Now table on board and SO page; the loose
   sentence is gone. The SO page reads the old product off `planning_change.from.item_code`.
2. `line_plans` works out `was_item_code` once (`LinePlan`): REMARK as before, the split read
   (`was_item_code`), and a split line's email rows (`_queue_plan_rows`). The preview sheet adds
   NEW ITEM CODE beside ITEM CODE when a line on it was swapped, and an unsplit covered line
   takes the old code and the read's REMARK words off the read.
3. One fixture (`sorento_crm_backend/tests/fixtures/product_change_tally.json`) is rendered as
   email + attachment (`tests/test_product_change_tally.py`) and as preview
   (`productChangeTally.test.tsx`) against one `expected`.

## Out of scope

- Suggestion lines on the SO page (owner).
- The guide's read-only fallback rows for an order that could not be adopted carry no
  NEW ITEM CODE (they have no split read); the normal path always has one.
