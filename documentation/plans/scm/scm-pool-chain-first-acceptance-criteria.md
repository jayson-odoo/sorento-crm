# UAC - Pool step walks every site pool first (R-N)

All goldens are `_v8_inputs` fixtures in `tests/scm/front_planning_golden.py`, fed to
`walk_line`; none reads the database.

- AC-N.1 (SRTWC8840-SC shape). Line 8 due inside the window at BRW-BB. Own pool BRW free 4
  (allowance 355), WH3 pool free 687 (allowance 343), WH3-BB group 94 free, net 1605.
  Composition = reserve BRW 4 + reserve WH3 4, step 0, whole. Step 1 `use` row still reports
  what the group could give but is not chosen. Sentence names both pools.
- AC-N.2 (SRTWCX8840-S-RL shape). Own pool free 1, WH3 pool free 682, group 140.
  Composition = BRW 1 + WH3 7 at step 0.
- AC-N.3 (SRTWCY8840 shape, the old spill case). Own pool free 3, WH3 pool free 684, own group
  1 free. Composition BRW 3 + WH3 5 at step 0. Identical quantities to today; the option row is
  chosen at step 0 rather than via the spill.
- AC-N.4 (own pool covers). Own pool free 240, allowance 120, line 10. Composition BRW 10.
  No other pool is drawn even though WH3 holds stock.
- AC-N.5 (beyond the window, whole or nothing across the chain). Line 300 due 60 days out.
  BRW allowance 100, WH3 allowance 250, net 1000. Combined 350 >= 300: composition BRW 100 +
  WH3 200. Same inputs with WH3 allowance 150 (combined 250 < 300): step 0 gives NOTHING, the
  walk falls to step 1.
- AC-N.6 (five-pool net bounds the chain). BRW allowance 100, WH3 allowance 100, net 120, line
  150 inside the window. Step 0 gives BRW 100 + WH3 20, remainder 30 to step 1.
- AC-N.7 (share ledger across units). Two units of one walk on the same product; the second
  sees each pool's allowance reduced by the first's take (`share_left`), per pool.
- AC-N.8 (R-L golden re-blessed). DC1-IB line 300, DC1 pool empty, own group 110, BRW sparing
  400: composition BRW 300, now at step 0. The `use` row reports 110, not chosen.
- AC-N.9 (confirm). Confirming AC-N.1's composition writes two Reserve components at two pool
  warehouses; the confirm-time recheck admits each against its own pool's free floor.
- AC-N.10 (board). On SO419417 on :3080, SRTWC8840-SC's cell reads BRW 4 + WH3 4, both pills
  "Use BRW stock" / "Use WH3 stock" (or the existing multi-pool label), Taken column on the
  pool rows 4 and 4, group rows untouched. Browser evidence recorded.
- AC-N.11 (sheet). The planning sheet's `lineBlockers` accepts a two-pool step 0 composition
  without a blocker (vitest).
- AC-N.12 (every pool's free floor is one ledger). Two lines of ONE walk at BRW-BB, with
  MWH's site pool holding 5 on the floor and 600 on the water (allowance 302, floor 5). The
  first line composes Reserve 5 at MWH; the second is offered nothing by the pool chain and
  buys. `compose_lines` carried a running balance for the asking bin's OWN pool only, and
  R-N made the other pools' path the common one.

## R-O overdue grace (supersedes R31)

- AC-O.1 (alive late document counts at the assumed date). Today 3 Sep 2026, grace 14. SPO of
  100 into BRW-BB dated 24 Jul, nothing received. A line of 50 due 20 Sep at BRW-BB with 0 on
  hand composes incoming 50, arrival 17 Sep, sentence "SPO <no> is 41 days late, assumed by
  17 Sep 2026".
- AC-O.2 (line due inside the grace gets nothing from it). Same document, line due 10 Sep:
  the document is not offered; the walk continues (borrow / buy).
- AC-O.3 (dead document counts as nothing). Same document dated 1 May 2026 (125 days late,
  dead > 90): not supply, exactly as R31, and its row on the Stock tab reads "not counted".
- AC-O.4 (group book, R-M). `group_book_positions` counts a late-alive document as supply and
  a dead one as nothing; two goldens.
- AC-O.5 (policy). `priority_policy.overdue_grace_days` and `overdue_dead_days` exist with
  defaults 14 / 90; the policy form edits and persists them; the engine reads the active row.
  Response schema declares both (response_model trap).
- AC-O.6 (board on SO419417). BRW-BB 8840-SC cell: the own-bin incoming (412 dated Jul/Aug)
  now offers up to the line's need at step 1 water with the assumed date; the Stock tab row
  shows assumed 17 Sep beside the stated 24 Jul. Browser evidence recorded.
