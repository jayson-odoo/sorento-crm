# PLAN: CONSIGN-OWN-BIN-EMAIL (own-bin consignment Borrow: row and email agree)

Status: implemented on PR #2084, waiting on CI (small fix track: < 300 lines, no migration, no
auth/RBAC, no new ingest)
UAC: `consign-own-bin-email-acceptance-criteria.md` (this folder)
Parent: `PLAN-consign-plan-15oct.md` (amended 2 Nov 2026 by this lane).

## Ruling

Owner, 2 Nov 2026: "if order own bin also need to send email to purchasing for order back".
A consignment's Borrow at its own bin raises the ORDER_BACK row AND the purchasing email, the
same as a sales order line's own-bin Borrow. This reverses CONSIGN-PLAN Q1 ("nothing to
purchasing") for the own-bin Borrow. The board's proposal for a consignment stays a Borrow of
the whole plan quantity at its own bin, never a Buy.

Owner, 2 Nov 2026: "we don't need the borrow from another order for now". The switch stays OFF
(its default); its ON path is untouched by this lane.

## Problem (measured at 5ac2eb7fa6)

The row and the email disagreed. `_location_order_backs` exempted a consignment's own-bin Borrow
(no row), while the email reads the frozen snapshot, where every non-incoming Borrow is
`ORDER BACK`: own-bin Borrow 10 gave no row and an `ORDER BACK` email; Buy 4 + own-bin Borrow 6
gave one `ORDER 4` row and an `ORDER BACK 6 & ORDER 4` email.

## Architecture

- Layer: backend service, the Confirm's order-back rows (`ProjectSupplyService.
  _location_order_backs`). No FE, no schema, no email change.
- The fix is a deletion: the own-bin exemption goes, so a consignment line's own-bin Borrow
  takes the same path as a sales order line's (OFF: every location Borrow is owed back at its
  location, the line's own included, Q3). The email already said ORDER BACK; now the row exists.
- A first round (3f35257407) implemented the reversed ruling by suppressing the email; it is
  replaced, not layered on.

## Tests (red first)

`tests/scm/test_consign_own_bin_email.py`, on the row and on the captured email:

1. own-bin Borrow 10 on a consignment: row ORDER_BACK 10 at the bin, email `ORDER BACK`.
2. Buy 4 + own-bin Borrow 6: rows ORDER 4 + ORDER_BACK 6, email `ORDER BACK 6 & ORDER 4`.
3. pin: consignment Borrow from another bin: row there, email `ORDER BACK <bin>`.
4. pin: consignment, planner-keyed Buy 10: row ORDER 10, email `ORDER`.
5. pins: sales order line own-bin Borrow at a planned bin (project class) and at an active
   flagged-off dealer bin (retail class, the Retail automation row): row + `ORDER BACK` at the
   line's own bin; and a consignment's own-bin Borrow reads exactly as a sales order line's.
6. re-Confirm unchanged (own-bin alone, and Buy + own-bin): no new row, no email line.

`tests/scm/test_consign_plan.py`: the five pins that said "nothing goes to purchasing" now
assert the ORDER_BACK row.

Kill test: put the exemption back, the consignment tests fail again.

## Browser-pass fix (crew, 2 Nov 2026), superseded 3 Nov by #2107

The guided Confirm review said "Delivered in full: nothing goes to purchasing" beside REMARK
ORDER BACK on a consignment line. This lane first fixed it for consignments only (db57c92116).
Main's #2107 (CONFIRM-PREVIEW-STALE item 4) then fixed it for every order class: the note shows
only when the guide's email dry run holds no line for the delivered line, and a delivered
line's saved decision prints its words. With this lane's backend change a consignment's
own-bin Borrow has its ORDER BACK email line, so #2107 already reads it right; the lane's
frontend changes were dropped in the 3 Nov merge of main (frontend now identical to main).
