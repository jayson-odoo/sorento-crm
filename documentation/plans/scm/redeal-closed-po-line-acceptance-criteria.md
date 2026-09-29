# UAC: the planning-change Confirm records the intent, purchasing moves the PO link

Plan: `PLAN-redeal-closed-po-line.md`. Lane REDEAL-CLOSED-PO, PR #1369. Owner ruling
29 Sep 2026, option (c): "confirm only records the intent, and purchasing makes every link
change in AutoCount, then synced back to order inquiries".

Vocabulary: a SHARE is one `{po_line_id, document, qty, line_status, qty_received}` entry
`_document_links_by_row` reads off a planning row's line before the confirm; a CLOSED share
is one whose purchase-order line has `line_status != 'open'` at apply time; the NOTICE is a
sentence on `result_json["released_documents"]`.

- AC-RC-1 [BE][T] Given a pending batch row with a `reallocate` component whose whole placed
  share sits on one purchase-order line, and that line is received in full and closed
  after the batch was built, when the batch is applied, then `failed_orders` is empty,
  `applied_orders` names the order, and the row's `applied_state` is `applied`.
- AC-RC-2 [BE][T] Same as AC-RC-1: the notice names the sales order and line number, the
  purchase order and the quantity, says the quantity was received in full, goods are stock
  now, nothing to move, and that purchasing adjusts the link at Order Inquiries.
- AC-RC-3 [BE][T] Same as AC-RC-1: no link is written onto the closed line by the apply.
  Every link it carries afterwards belongs to the line's own row.
- AC-RC-4 [BE][T] Given a `reallocate` component whose share sits on an OPEN purchase-order
  line, when the batch is applied, then no pool-location row is written, no waiting row of
  any order is linked or annotated, the giving line's link stays as the confirm's own settle
  left it, `executed_reallocations` is empty for that component, and the notice names the
  sales order and line number, the purchase order, the quantity, quotes the composed label
  and says AutoCount is where purchasing moves the link.
- AC-RC-5 [BE][T] `place_on_po_allocations` is never called by a planning-change apply: with
  a refusal planted there, the order still applies.
- AC-RC-6 [BE][T] Given a row placed on an open line and a closed line, when the batch is
  applied, then the open part is recorded as intent (AC-RC-4) and the closed part is named
  received (AC-RC-2), and neither line gains a link.
- AC-RC-7 [BE][T] Given a `cancelled` row whose placement a same-order survivor can only
  partly take, when the batch is applied, then the survivor shift still moves what it can
  (AC-P3-6), the rest stays on the cancelled row, no pool row is written, no other order's
  row is linked, and one notice records the intent for the rest.
- AC-RC-8 [BE][T] AC-S1-1 stands: a placement gone entirely by apply time records
  `nothing to move, the placement this suggestion named is no longer on the line`. AC-S1-2
  is superseded: a partial placement records the intent for what is left and
  `<qty> of <PO> is no longer on the line, nothing to move` for the rest, never a 409.
- AC-RC-9 [BE] A reserve move (AC-D4) and an SPO give-back (D7) are unchanged.
- AC-RC-10 [FE][T] `whereItWentFrom` prints a released entry that already is a sentence
  verbatim, and still wraps a bare document number as `Released <doc> for purchasing`.
- AC-RC-11 [UI] On the fulfilment planning board, after Confirm on SO396347, the toast reads
  "1 of 1 orders confirmed" and the row's "Where it went" list shows one notice per
  purchase order; no Order Inquiry row of any other order changes.
