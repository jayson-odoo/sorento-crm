# PLAN: a repeat board Confirm never changes what the first one held (CONFIRM-DOUBLE-ROWS)

Status: built, in review (PR #1934). Track: small fix (under 300 lines, no migration, no auth change).
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

## Tests

`tests/scm/test_confirm_double_rows.py` (red on main for the two repeat-press cases):

1. Three identical Reserve presses behind an earlier order: no allocation, short 36 on every press.
2. Free stock: a repeat press keeps exactly one `own 36` under the active revision.
3. Changed decision Reserve, Buy, Reserve: each press's rows are that press's decision alone.
4. Reserve 36, then Reserve 20 + Buy 16: the active revision holds 20, not 56.
5. Partly short (50 on hand, 36 to SO-A): every press holds 14 and records 22 short.
