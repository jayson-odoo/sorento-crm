# PLAN: CONSIGN-OWN-BIN-EMAIL (own-bin consignment Borrow never emails purchasing)

Status: in progress (small fix track: < 300 lines, no migration, no auth/RBAC, no new ingest)
UAC: `consign-own-bin-email-acceptance-criteria.md` (this folder)
Parent: `PLAN-consign-plan-15oct.md` (owner ruling Q1: a consignment's Borrow at its own bin
sends nothing to purchasing).

## Problem

Measured at 5ac2eb7fa6 through real Confirms on a scratch DB:

- A consignment line's Borrow at its OWN bin raises no order inquiry row
  (`project_supply_service.py:8716`, `_location_order_backs`), yet the purchasing email says
  `ORDER BACK 10`.
- Buy 4 + own-bin Borrow 6 raises one `ORDER 4` row, yet the email says
  `ORDER BACK 6 & ORDER 4`.

Cause: the email (`ProjectOrderInquiryService.record_saved_lines`, called from
`ProjectSupplyService._tell_saved_lines`) reads the frozen snapshot through
`_saved_line_parts`, where every non-incoming Borrow is `ORDER BACK` (a purchasing key). Only the
row code knows the own-bin exemption. `test_uac06` counts rows, never the email.

## Architecture

- Layer: backend service, the Confirm's email hand-off (`_tell_saved_lines`). No FE, no schema.
- One rule, two readers: the own-bin exemption becomes one predicate on `ProjectSupplyService`
  (`_owes_nothing_at_own_bin(fact, warehouse_id)`), used by the row code
  (`_location_order_backs`) and by `_tell_saved_lines`.
- `_tell_saved_lines` already marks both snapshots alike before the email reads them (a local
  Buy reads LOCAL BUY, `_marked`). The own-bin Borrow is marked the same way: it reads as what
  it is, the line's own stock (`USE <own bin>`, key `USE_OWN`), which is not purchasing's
  (`_PURCHASING_KEYS`). Marking BOTH sides keeps a re-Confirm of an already confirmed
  consignment from reading as a change.
- Exactly the row rule: a Borrow that names its order with the switch ON still raises its row
  at the donor line (`project_supply_service.py` named-order section), so it keeps
  `ORDER BACK`.
- Nothing else moves: a Borrow from another bin keeps ORDER BACK, a Buy keeps ORDER, a sales
  order line at its own bin keeps today's row and email.

## Out of scope (reported, not widened)

Switch ON, a Borrow with no donor line from a source whose `group_of` is None or the line's own
group (`project_supply_service.py:8655-8656`), or from the line's own warehouse
(`project_supply_service.py` ON loop `own_id` skip): no row, email still ORDER BACK. That rule
covers sales order lines too, so matching the email to it changes non-consignment behaviour,
which this lane must not do. Owner ruling needed.

## Tests (red first, on the handover email itself)

`tests/scm/test_consign_own_bin_email.py`:

1. own-bin Borrow 10 on a consignment: no purchasing email line (red today).
2. Buy 4 + own-bin Borrow 6: one line, remark `ORDER 4` (red today).
3. pin: consignment Borrow from another bin: email `ORDER BACK <bin>`.
4. pin: consignment, planner-keyed Buy 10: email `ORDER`.
5. pin: sales order line, Borrow at its own bin: email unchanged (`ORDER BACK`).
6. pin: re-Confirm of the same own-bin Borrow sends nothing.

Kill test: revert the `_tell_saved_lines` marking, tests 1-2 fail again.
