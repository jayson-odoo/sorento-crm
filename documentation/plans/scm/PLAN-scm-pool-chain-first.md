# PLAN - Pool step walks every site pool before another site's group bin (R-N)

Status: S1 to S3 DONE + AC-N.12 floor ledger + review fix round + B1 ruled + golden (PR #607,
merged on `origin/main`), and S4 to S6 (R-O, overdue grace, #586) on `feat/scm-pool-chain-ro`,
stacked on #607, 3 Sep 2026. Engine, board proof and docs landed;
`walk_line` step 0 walks the whole pool chain, R-L's spill block and `_draw_other_pools` are
deleted, and the step 0 row is written from the pools that answered. Goldens AC-N.1 to AC-N.8
are `_v8_inputs` cases in `tests/scm/front_planning_golden.py`, AC-N.9 is two confirm tests in
`tests/test_so_supply_confirmation.py`, the board's multi-pool proof is
`tests/test_fulfilment_board.py::test_a_cell_whose_pool_step_answered_from_two_pools_shows_both_taken_figures`
and AC-N.11 is two vitest cases in `supplyComposition.test.ts`. AC-N.10 (browser evidence on
SO419417) recorded 3 Sep. B1 (own-bin order) ruled by the captain 3 Sep and pinned by AC-N.13,
a `_v8_inputs` case in `V8_WALK_CASES` - no engine change, the coded behaviour already matched
the ruling. AC-N.12 (every pool's free floor is one ledger, reported by the R-N coder) is
`tests/scm/test_project_supply_service_ladder.py::test_another_sites_pool_free_floor_is_spent_once_across_the_whole_walk`.

R-O (S4 to S6, overdue grace, #586) DONE: migration `464_overdue_grace`, the policy pair on
`scm.priority_policy` with its form fields, `supply_assignment.counted_event` as the one
place the rule lives, the lateness clause on every incoming rung's sentence
(`front_planning_engine.late_document_reason`), and the assumed/stated dates on both stock
ledgers. Tests: `tests/scm/test_overdue_grace_setting.py` (AC-O.5),
`tests/scm/test_supply_assignment.py`'s R-O block (AC-O.1 to AC-O.4),
`tests/scm/test_overdue_grace_ladder.py` (the compositions and the sentences),
`tests/scm/test_stock_debt_routes.py` and `tests/test_fulfilment_board.py` (the ledger
rows), plus vitest on the policy form and `StockDocumentsPanel`. AC-O.6 (browser evidence on
SO419417) is still owed.
RULED 3 Sep 2026 (R-N + R-O, Q1 by on hand, grace 14 / dead 90). Supersedes R-L's trigger.

## Why

Captain, 3 Sep 2026, on SO419417 SRTWC8840-SC (8 due 29 Sep at BRW-BB): the board proposed
BRW pool 4 + WH3-BB 4 while WH3's site pool held 687 on hand (343 Available for Project) and
the five-pool subtotal read 905. "The pool got a lot though." Ruling: the pool step takes from
ANY site pool before falling to another site's group bin.

Measured cause (`front_planning_engine.py:1093-1097`): step 0 draws the asking bin's OWN pool
only (`pools[:1]`). The other site pools are asked only by the R-L spill (`:1147-1168`), and
only after own locations and both borrows failed to cover the remainder whole. Here WH3-BB
covered the remainder, so WH3 pool was never asked. On SRTWCY8840 the own group had 1 free,
the spill fired, and the composition read BRW 3 + WH3 5. Same rule, two different answers,
decided by whether a group bin happened to have stock.

## Ruling R-N (the contract)

- **Step 0 walks the WHOLE pool chain**, in the existing draw order: the asking bin's own site
  pool first, then every other active site pool by on hand (`_pool_chain`). Each pool lends
  under its own allowance (`available_for_project`: Available less the kept share, less what
  this walk already took from it via `share_left`), never more than its free floor, and the
  one five-pool net bounds the total (`pool_share_capacity` already computes exactly this per
  chain).
- **Inside the immediate window** (30 days, `priority_policy.immediate_window_days`): the
  line takes up to the chain's combined capacity, split across pools as the chain is walked
  (BRW 3 + WH3 5 is a valid step 0 answer).
- **Beyond the window**: whole or nothing against the chain's combined capacity (R-B's
  intention, now stated of the chain rather than of one pool).
- **Steps 1 to 3 unchanged**: own bin, group bins, other groups' free (R-M cap), order borrow,
  supply borrow answer for the remainder, first whole cover wins.
- **R-L's spill block is removed.** After step 0 has walked the chain there is nothing left
  for it to find; the pool's own later orders (pool borrow, R34) stay where they are, after the
  borrows and before Buy.
- **Sentences**: the step 0 option row is written from the pools that answered (existing
  `spilled_components` path becomes the only path): "Pool BRW spares 4 of the 355 it may lend
  a project Pool WH3 spares 4 of the 343 it may lend a project". Label stays
  `_pool_share_label` (names the pools that answered).
- **The pool chain outranks the line's own bin, not only every group bin** (B1, captain 3
  Sep): step 0 (the whole site-pool chain, own pool first then by on hand) is asked before the
  asking line's OWN bin's free stock, exactly as it is asked before every group bin. Own free
  stock is step 1 (`STEP_USE`), unchanged in position, only later in the order than the pool
  chain. This is R-A/R-B (2 Sep) stated of the own bin as well as the group, not a change to
  the walk order already coded.

## What this changes on SO419417

| Line | Today | Under R-N |
|---|---|---|
| SRTWC8840-SC 8 | BRW 4 + WH3-BB 4 (group) | BRW 4 + WH3 4 (pool) |
| SRTWCX8840-S-RL 8 | BRW 1 + WH3-BB 7 (group) | BRW 1 + WH3 7 (pool) |
| SRTWCY8840 8 | BRW 3 + WH3 5 (spill) | BRW 3 + WH3 5 (step 0, same numbers) |
| SRTWT5880-CR 10 | BRW 10 | BRW 10 (own pool covers) |

Group bins (WH3-BB 94 / 140 / 79) are left for the BB group's own later lines.

## Slices (one lane, one PR)

S1. Engine. `walk_line`: `_draw_pool(step_share, pools, ...)` over the chain via
`pool_share_capacity`; `wanted` computed against the chain's combined capacity; beyond-window
whole-or-nothing against the same figure; delete the R-L spill block; `pool_share_reason_text`
always from `step_share.components`. Goldens: the four SO419417 rows above as `_v8_inputs`
cases (AC-N.1 to AC-N.4), R-L's existing DC1-IB 300 golden re-blessed to the same answer
(BRW 300 now arrives at step 0). `LADDER_VERSION` stays v8 (rule refinement, not a new order).
S2. Board proof + trail: the pool question's `offered` reads the chain (already does per
review round 2 S5); trail step 1 text "checked BRW, WH3, DC1, MWH, RSW" unchanged. Sheet
`lineBlockers` / `poolShareLimitsFromLine` accept multi-pool step 0 (they accept the spill's
today, verify with a vitest).
S3. PLAN + UAC + LESSONS entry: R-L trigger retired.

No schema, no migration, no permission, no new UI. Frontend Phase 1 is n/a (no new surface);
Phase 2 test-first on the goldens.

## Ruling R-O (captain 3 Sep, "overdue yeah we can have a grace period") - supersedes R31

R31 (2 Sep) counted an overdue document as nothing. Captain on SO419417: "Available for
Project" at BRW reads 355 off 725 SPO units dated 24 Jul and 6 Aug 2026 (unreceived on 3 Sep)
while the ladder lends 4 off the 11 on the floor. Ruling: the display is right, the engine
should not ignore a late document.

- An overdue document (arrival date < today, nothing received) counts as supply landing on
  `today + overdue_grace_days`. New column on `priority_policy` beside
  `immediate_window_days`: `overdue_grace_days` INT NOT NULL DEFAULT 14, and
  `overdue_dead_days` INT NOT NULL DEFAULT 90 (migration, one head, chained onto main's head
  at PR time via `scripts/alembic-reparent.sh`).
- A document later than `overdue_dead_days` counts as nothing (R31 stays for the dead).
- The assumed date is what the walk plans against, on every incoming rung (own bin water,
  group water, pool water, supply borrow): a line due before `today + grace` does not get it.
- Composition kind stays incoming (`TIMELY_SPO`), never Reserve. The component sentence
  names the lateness: "SPO 1234 is 41 days late, assumed by 17 Sep 2026". Stock tab / ledger
  rows for such documents show the assumed date, not the stated one, with the stated date
  beside it.
- `supply_assignment` `uncounted` splits: late-but-alive documents move into `counted` at
  the assumed date; dead ones stay uncounted. `group_book_positions` (R-M) therefore counts
  them too, consistently.
- Policy editor (System settings, priority policy form) gains the two integer fields, same
  row as the window and share.

Slices for R-O (same lane, after S1 to S3): S4 migration + policy schema/form; S5 assignment
`counted` rule + goldens (AC-O.1 to AC-O.6); S6 sentences + Stock tab date.

## Rulings taken

- Q1 (captain 3 Sep): other pools by on hand, fullest first, as today.
- B1 (captain 3 Sep): all pools before own bin.
