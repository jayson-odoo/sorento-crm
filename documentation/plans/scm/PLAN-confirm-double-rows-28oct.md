# PLAN: a repeat board Confirm never changes what the first one held (CONFIRM-DOUBLE-ROWS)

Status: built, reviewed (2 rounds), browser pass done; awaiting owner hand test (PR #1934). Track: small fix (under 300 lines, no migration, no auth change).
UAC: `confirm-double-rows-acceptance-criteria.md` (alongside).

## The defect

Found by BOARD-NO-HOLD (#1919), and identical on main. The setup: a fresh SO-B, an earlier undecided SO-A at the
same bin, 36 on hand, three identical "Reserve own 36" confirms on SO-B.

- Press 1: no allocation, revision 1, the Reserve recorded short 36.
- Press 2: `own 36` written, revision 2.
- Press 3: another `own 36` row, revision 3.

Cause: `ProjectSupplyService._carried_component_qty` credits the active revision's frozen component as "already
held". It read the component's ASKED quantity. Under OI-CLOSED-LINE only what exists is held: the short part is
recorded in the snapshot's `stock_short` and gets no allocation. So on press 2 the credit was 36, and `_check_line`
skipped the recheck (`ask = qty - carried` = 0). It then wrote the full 36 that press 1 had found short.

The press 3 row is the per-revision copy. `_write_allocations` keeps a superseded revision's rows as history, and
only rows under the ACTIVE revision count (`_decision_allocation_query`). It is not a second hold. Its quantity was
wrong for the same reason as press 2.

## Press 1 is correct

The rule comes from `CARD-board-no-hold-27oct.md:22`: "who actually gets a pile is decided by date, earliest need
first". SO-A needs the 36 first, so the recheck's date-aware capacity (`use_candidates_for` in `_check_line`) leaves
SO-B nothing at its own date. OI-CLOSED-LINE then confirms the Reserve as decided and records it short. Stock Debt
reads SO-B short 36 for the same reason.

This is not the cap by other orders' decisions that the card retires at :35. SO-A has no decision.

## Fix

The credit is what the revision HELD: the frozen component quantity, less the `stock_short` the same revision
recorded for that kind at that location. `confirm` copies each active line's `stock_short` into `carried_holds`.
`_frozen_by_line` itself is unchanged, because the board and planning-change readers use it as it is.

What the fix does on each kind of confirm:

- A repeat press is judged exactly as the first press was.
- A changed decision already replaced the previous allocation; that is unchanged.
- A first confirm has no carried credit, so it is unchanged.

## Review round 1 (folded in)

- **Delivered credit (B1).** The frozen component includes the line's delivered part, and so does the delivered
  credit. A repeat press credited those units twice, so the hold grew by the delivered qty on every press. The
  delivered credit now comes off the carried credit too, on Reserve and on every Borrow path (`delivered=`).
- **Shortfall keys (S1).** A recorded shortfall now carries its component's `warehouse_id` (plus `donor_project_id`
  for a Borrow), so it nets only that component's credit. Older snapshots fall back to the location code.
- **Stricter only where it should be.** An increase on a line with deliveries is exempt only for what was held.

## Where the board UI stands

- The board will not re-save an unchanged decision on a confirmed line ("Save decision" stays disabled). So identical
  presses arrive only from a replayed or retried request.
- A planner reaches the defect by confirming, changing the decision and confirming again, when that decision was
  recorded short. On main, Reserve 36 short followed by Reserve 35 + Buy 1 held 35.
- Within one Confirm two lines are netted. Across separate Confirms two plans may name the same stock (#1919), so a
  Reserve shorted only by a sibling line in the same Confirm legitimately holds on its next Confirm.

## Evidence run (agent-browser, sandbox DB, 28 Oct)

Setup: fresh bootstrapped DB, all modules installed, a seeded superadmin, and orders seeded at bins `ZZTBRW-IR` and
`ZZTMWH-BB`. Every page was reached by sidebar clicks from `/`.

1. ZZT-SOB line 2 (50 on hand, SO-A due earlier for 36): Change decision, Own 36 with a reason, Save, Confirm,
   Confirm 1 order. Result: revision 1 holds `own 36`.
2. The board would not save the same decision again. Presses 2 and 3 replayed the board's own `confirm-all` payload.
   - Active revision after each press: one `own 36`.
   - The Stock Debt cell for the product was byte-identical after press 1 and press 3: SO-A covered 36; SO-B
     assigned 14, short 22.
3. ZZT-SOD: Reserve 36 with a reason from `ZZTMWH-BB`, another group's bin that an earlier order needs. Three
   presses via `confirm-all`.
   - Every press reported "36 short" and wrote no allocation row. Stock Debt was identical across the presses.
   - The board reads Confirmed rev 3, "BRW 36 (ZZTMWH-BB)", with one transfer proposal.

## Tests

`tests/scm/test_confirm_double_rows.py`, 12 tests (6 fail on main):

1. Three identical Reserve presses behind an earlier order: no allocation, short 36 on every press.
2. Free stock: a repeat press keeps exactly one `own 36` under the active revision.
3. Changed decision Reserve, Buy, Reserve: each press's rows are that press's decision alone.
4. Reserve 36, then Reserve 20 + Buy 16: the active revision holds 20, not 56.
5. Partly short (50 on hand, 36 to SO-A): every press holds 14 and records 22 short.
6. Partly delivered (10 of 36): every press holds what press 1 held (Reserve, and a Borrow at a sibling bin).
7. One bin short and one held, two components: repeats are unchanged, and the short is frozen with its bin's id.
8. A shortfall only R14's on-hand floor finds is keyed to its bin too.
9. Cross-group Reserve with a reason, pressed three times: short 36 each time (on main press 2 wrote `brw 36`).
10. Changing the decision and back (36, then 35 + Buy 1, then 36): nothing is held at the short bin.
11. A pure unit test of `_carried_component_qty` matching (warehouse, donor, legacy location, floor at zero).
