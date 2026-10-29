# PLAN: OI rows auto-confirm, OI auto-complete, no manual Confirm (OI-AUTO-CONFIRM)

Status: Plan - behaviour card filed to the owner, no code until answered. Track: full (size L:
changes reorder-plan demand, retires a purchasing press, possible migration/backfill).

## Owner ruling (29 Oct 2026, ~21:55)

"in the future, I don't want the user to go and confirm or unconfirm the order inquiry. I want
the system to automatically mark the rows as confirm or unconfirm by this definition. If the rows
have PO or rejected or reserved, then it's considered confirmed. And if all the rows in the order
inquiry is confirmed, then the order inquiry is automatically completed. So in the outstanding,
the user will only see from a purchasing perspective, what have I not ordered or reserved or
rejected."

## Today (measured, file:line)

- Row "confirmed" = `order_inquiry_rows.ack_state` in (`acknowledged`, `rejected`);
  `awaiting` / `changed` = To confirm (`app/models/project_so.py:767-782`).
- OI header Outstanding = at least one non-cancelled line with a row in awaiting/changed, else
  Completed (`app/services/order_inquiry_header_service.py:291`, `_rows_agg` 186-241).
- Purchasing's Confirm press = `acknowledge_rows` (`app/services/project_order_inquiry_service.py:9232`).
- Reorder plan counts project demand ONLY on acknowledged/changed rows
  (`app/services/scm/demand.py:383-393`, `:764`, `:848`); awaiting rows are a chip
  (`app/services/scm/reorder_run_service.py:1265-1290`).
- Cascades already link awaiting rows (`include_awaiting=True` on every cascade door,
  `project_order_inquiry_service.py:3863`, `:9251`).
- Links: one target each - PO line, SPO allocation, or confirmed CS reserve
  (`app/models/project_so.py` `OrderInquiryLink`, CHECK at ~1239).

(Confirm/Unconfirm UI paths, purchasing email + Excel triggers: filled from the code map.)

## Proposed rule (pending owner answers)

- Row confirmed = has a PO/SPO link OR has a reserve link OR rejected (plus the answers below).
- OI Completed = every live row confirmed; Outstanding otherwise. Derived at read time.
- Manual Confirm / Unconfirm presses retired.

## Open questions

See the behaviour card (`crew report --ask`, 29 Oct).

## Slices

To be written after the owner answers.
