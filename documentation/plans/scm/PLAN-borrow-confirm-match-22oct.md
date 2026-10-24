# PLAN: Confirm accepts every Borrow the list offers (BORROW-CONFIRM-MATCH)

Status: in review, PR #1830, small fix track (S, no migration, no RBAC change), lane crew/borrow-confirm-match.
UAC: `borrow-confirm-match-22oct-acceptance-criteria.md`.

## Journey

Owner, 22 Oct 2026 ~16:45, prod SO401624: Confirm refused "Line 304, SRTSA-SS: Later-order stock
at BRW-BB is held for an order ranked ahead of this line, so it cannot be borrowed." The planner
had picked that Borrow off the list. Owner ruling (b): "confirm should be lenient also, confirm
should match the dropdown". Whatever the Borrow list / Decide dropdown offers, Confirm accepts.

The same press then printed "was confirmed, but its staged rejection could not ride along ..." beside
the server's "Nothing was written": the held-back note is worded before the server answers.

## Facts (origin/main 552858f168)

- The refusal is `_check_group_borrow` (`sorento_crm_backend/app/services/project_supply_service.py:7140-7149`),
  branch B1: a location borrow (`_names_its_order` False, so the switch is OFF or no donor SO was
  posted) whose donor `_needs_authorisation` (:7038, same agent and not `lower_ranked` in
  `_group_borrow_donors` :4560) is refused.
- The step-2 list judges a later order by date only (`_eligible_donor` :4012,
  `later_order_can_wait`); rank enters only through the B1 filter (:4151-4160 and :10710).
- Dev copy (`sorento_cagent_stack`, read-only probe): SO401624 line 304 has no step-2 donor there
  (offered 0, unfiltered 0), so the exact prod path that offered the TERA donor ranked ahead is
  UNVERIFIED. Removing the confirm-side rank refusal fixes it whatever path offered it.
- Donor fate, existing path, no new code: the borrow writes one `SOLineAllocation` on the ASKER's
  line carrying `donor_core_line_id` (:8843-8901, :9008-9024); `StockDebtService._holds` pins it
  first in `assign()` (`scm/supply_assignment.py:705-731`), so the donor queues against a smaller
  bin and reads short on the board and Stock Debt (:827-828). Under OFF the order-back hangs on the
  asker's line (:8193-8194, :8293-8308). The writer has no rank branch.

## Change

1. BE: `_check_group_borrow` drops the B1 refusal for a location borrow. An order borrow (donor SO
   named, switch ON) keeps the "say who authorised it" rule. Every other check stays: product,
   location, ownership group, still open demand, the per-donor-line ledger.
2. BE: the list's B1 filter comments no longer say "confirm refuses it". The filters themselves
   stay (crew, 22 Oct: confirm-only; dropping them would make the list offer more).
3. FE: the held-back note is settled after the server answers: "was confirmed, but ..." only when
   the same order has an ok result; otherwise the not-confirmed wording.

## Tests (red first)

- pytest `tests/scm/test_borrow_location_only.py`: a same-agent donor ranked ahead confirms as a
  location borrow and then reads short (group-borrow and SO401624-shaped step-2 worlds); both list
  filters still leave it off the list.
- vitest: held-back wording when the server refused the order vs confirmed it.

## Trigger for more

If the owner wants the list widened too (same-agent ahead-ranked stock offered), drop the two list
filters in a follow-up.
