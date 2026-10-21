# PLAN: OI email ORDER BACK row shows the refill (donor) location

Status: Plan - behaviour card filed as crew-ask, waiting on the owner. Track: small fix (no migration, no auth, no UI).

## Owner ruling 21 Oct (option B)

In the Order Inquiry handover email an ORDER BACK row prints the location the stock is ordered
back to (the donor, the OI row's own `stock_location`), as the OI Excel already does
(`order_inquiry_worklist_service.py:733`). This reverses the 13/14 Oct "line's own location" rule
for ORDER BACK only. REMARK stays as it is (no donor words in it).

## Where the email reads the line's own location today

- Row path: `ProjectOrderInquiryService._handover_line` swaps an `ORDER_BACK` row's donor for the
  SO line location (`project_order_inquiry_service.py:4482-4493`).
- Saved-line path (Confirm): `saved_line_remark` returns the SO line location for every part
  (`project_order_inquiry_service.py:550-575`, `_saved_line_parts` :677-696); `_queue_saved_line`
  prints it in LOCATION and the subject (`stock_location` on the queued item).
- `_borrow_donors` (:745) and `record_saved_lines` (:4590-4597) treat a donor move as "same
  line, own location".
- Subject: `_build_handover_context` (:14052-14060) - one named location -> `<loc> @ <SO>`,
  otherwise the bare SO list.
- Resend (`oi_handover_resend`) rebuilds open rows through `_handover_line`, so it follows the
  row path.

## Open questions

Filed on the PR as `crew-ask` (behaviour card). Implementation starts once answered.

## Tests (red first)

To be listed once the card is answered: email rows + subject + resend for the SO426913 shape
(ORDER at IR cancelled, ORDER BACK from BB raised), a same-location borrow, a two-donor borrow.
