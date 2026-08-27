# PLAN - Fulfilment planning: plan the order as a whole per delivery date (ladder v6, order units)

Status: **BACKEND BUILT 2026-08-28** (GO the same day; captain: "yeap correct" to the unit key). Built test-first on a worktree off `main` `e30507789` (#357); section 3.5 (the donor ledger) was added mid-build from a live confirmation failure and is in the same change. UAC: `scm-order-unit-ladder-v6-acceptance-criteria.md`, pinned by `tests/scm/test_ladder_v6_order_unit.py`. The frontend sentence (AC-F1) is separate and not in this change. Review round 28 Aug: one blocker and four smaller findings, all fixed in the same branch - section 5.

## 0. What the captain asked (28 Aug, reading WESERP10B on `/project-sales/fulfilment-planning`)

SO381895 lines 31 and 32, same item, same location BRW-IB, same delivery date 25/08/2026, 10 and 20. The board proposed **Borrow 10 from BRW-SYNT** for line 31 and **Buy 20** for line 32. "This is 1 order as a whole, so we should look at the order as a whole instead of line by line ... for the same delivery date." Fulfilment is buy ALL or use existing stock for ALL (own location, BRW pool, borrow); half now / half later has no point because the timing differs.

## 1. Why it happens today (verified in code)

- `front_planning_engine.propose_line` already applies the whole-LINE rule (`:591-601`): cover the line entirely in rung order or buy the whole of it.
- Every caller walks the ladder **per line** with a running pool ledger, in line order: the board `project_fulfilment_board_service._allocate` pass two (`:1800-1830`), the sheet `project_supply_service.proposal_for` (`:797-822`) and the freeze `_compose_for_freeze` (`:3240-3270`). Three copies of the same loop.
- Line 31 (10) walked first: own group -10795, pools net 4055 but BRW itself -6930 and the pool rung offered nothing here, cross-group BRW-SYNT had 12 -> Borrow 10, whole line. Line 32 (20) walked next: SYNT had 2 left, cannot cover 20 -> Buy 20, whole line. Each line obeys the rule; the order does not.

## 2. Rulings (captain, 28 Aug)

| # | Question | Ruling |
| --- | --- | --- |
| R1 | Planning unit | **(sales order, item, fulfilment location, required date)**. Lines of one order for the same item, location and delivery date are planned as ONE quantity |
| R2 | Different location on a line | its own unit |
| R3 | Different delivery date | its own unit |
| R4 | Decisions | stay per line (line_snapshots, Confirm, the row editor, transfers unchanged). Only the PROPOSAL changes |
| R5 | Whole-unit rule | the unit is covered entirely from stock in rung order, or the unit is bought whole. Never "line 31 borrows, line 32 buys" |

## 3. Design (simplest thing that works)

1. `ProjectSupplyService.compose_lines(entries, *, as_of=None) -> Dict[key, (components, pool_open, borrow_open)]` where `entries` = `[(key, fact, unit_key)]` in walk order. It owns both ledgers (the pool loop the three callers duplicate, and the donor one of section 3.5) and the units. `borrow_open` is the donor ledger as the unit found it, which the board's proof states beside `pool_open` (see Deviations, S1):
   - group consecutive-or-not entries by `unit_key`, first appearance decides the unit's position in the walk;
   - a unit of one line = today's `compose_line(fact, ...)` unchanged;
   - a unit of N lines: `unit_fact = dataclasses.replace(first_fact, open_qty=total, group_offer=max(group_net + total, 0))` (ladder v4's `_group_offer` rule, applied to the unit's own demand instead of one line's), `compose_line(unit_fact, ...)` once, then **split the components back onto the members in line_no order**: walk the unit's components, fill each member up to its `open_qty`, a component may straddle two lines (same kind, source, rung, reason, split qty). A whole-unit Buy becomes Buy `open_qty` on every member with the unit's reason.
   - pool ledger drawn once per unit.
2. Callers: the board's pass two, `proposal_for` and `_proposals_for` (the freeze; there is no `_compose_for_freeze`) call `compose_lines` and read their line's tuple; their per-line bookkeeping (trail, sources, donors, contested, warehouse_ids) is unchanged. `unit_key` = `(sales_order_id, product_id, warehouse_id, required_date)` on the board, `(product_id, warehouse_id, required_date)` on the sheet (one order). A line an active revision COVERS is out of every unit and out of both ledgers, on all three: a decided line is not re-planned, and its claim is already a hold in the facts.
3. Payload: each contribution / sheet line gains `unit_qty` (the unit's total) and `unit_line_count`. The FE source-info tooltip (`BoardCellBreakdownDialog` `sourceNoteOf`) appends one sentence when `unit_line_count > 1`: "Planned with N other line(s) of this order for {date}: {unit_qty} in all." No other UI change.
4. Trail: computed per line from the SPLIT components as today; the unit sentence lives in the payload fields above.

No new table, no flag, no config. The trigger for a per-tenant switch does not exist.

## 3.5 The donor ledger (added 28 Aug, live failure)

Confirming SO381895 answered "0 of 1 orders confirmed ... Line 51, SRTWT7445-LV: BRW-SYNT has 0 free, and 10 was asked for" on four lines that had each been proposed a Borrow of 10 from a location holding 10 in all.

Cause, read in the code: `_cross_group_borrow_candidates` (rung 5) reads the donor's free stock off `_by_product()` and caps it by a `group_left` built fresh **per call**, so there is no ledger ACROSS a walk. Only the own site pool had one (`pool_left`, kept separately by each of the three callers). Every delivery date was therefore offered the same 10, and `confirm` - which does hold a running ledger - refused all but the first. `_donors_for` caches by `(product, warehouse, need)`, so the board could not have noticed either.

Fix, inside the same `compose_lines`: a running donor ledger keyed by (product, donor warehouse), seeded from the donor's free stock the first time the walk borrows there and drawn down by every Borrow component the walk produces, per unit, in walk order. It reaches rung 5 the way `pool_free_left` reaches rung 3: `compose_line(..., borrow_left=<warehouse id -> remaining>)`, and `_cross_group_borrow_candidates` caps each donor's free balance by it when given. Under the whole-unit rule the later units then buy whole, which is the captain's own expectation: the donor is "occupied by the first borrow".

The donor guard inside `confirm` is unchanged. It was right; the proposal was wrong. (What the review DID have to change in `confirm` is a different rule, and it is Deviations item 2.)

## 4. Out of scope

Amend semantics (a person may still amend one line differently); the reorder engine; the whole-line rule itself. Confirm's own SEMANTICS are out of scope too - what a decision means, what it holds, what it carries - but its RECHECK had to learn about units, or nothing this plan proposes could be confirmed at all: Deviations item 2.

## 5. Deviations, and what they cost (review round, 28 Aug)

Recorded here rather than in a commit message, because the next person to read this plan is the one who needs them.

1. **`_compose_for_freeze` does not exist.** The freeze walk is `ProjectSupplyService._proposals_for`. Section 3 above is corrected; the name in the review brief and in the first build's report was wrong, the code was always right.
2. **The confirmation had to be made unit-aware (B1, blocker).** Section 3 said decisions were untouched, and that was not true of the RECHECK: `_check_line` re-derived the group's offer per LINE (`max(group net + that line's quantity, 0)`), while the proposal un-nets the whole unit. On a group whose net is negative the members' own offers sum to LESS than the unit's, so with 5 on the floor and 25 in the pool the proposal for lines 31 and 32 (10 and 20) was refused with "ZZTBRW-BB has nothing free for this line now" - no split of a unit was confirmable at all. Same root as the water case: a unit's timely SPO share can land wholly on one member. Fixed by seeding the recheck from the unit: `_unit_checks` groups the order's lines with the SAME `_unit_key` / `_unit_fact` `_proposals_for` uses, and one `_UnitCheck` per unit carries the unit fact (which the capacity ledger and the reserve rungs are seeded from) and the unit's remaining water, drawn down as its members are checked. `_split_unit` is untouched. Pinned end to end by `test_a_unit_split_across_two_lines_confirms_exactly_as_proposed` and `test_a_unit_met_from_the_floor_and_the_water_confirms_as_proposed`.
3. **`_unit_fact` recomputes `timely_qty`.** The first build deliberately did not, on the grounds that `compose_line` never reads it. The confirmation does (item 2), so it is recomputed exactly as `_apply_group_nets` does for a line.
4. **The frozen proposal is composed over the ORDER, not over the payload (S2).** `_proposals_for` walked only the named lines, so confirming one line of a unit froze the composition of a line planned alone - "Reserve 20 from the pool" beside a sheet that had shown a Buy. It now walks `lines_of(order)` minus the carried lines and reads the checked keys out, which needed `facts` and the carried set passed down from `confirm` through `_write_decision`.
5. **The proof reads the walk's donor ledger (S1).** The board's question 3 rebuilt its candidate list with no `borrow_left`, so on four dates sharing one donor it said "free stock at DC1-NT, within the cross-group borrow limit" beside a Buy the ledger had just forced, and the Buy's own sentence offered a donor with nothing left. `compose_lines` now returns `borrow_open` beside `pool_open` and `_trail` passes it to `cross_group_borrow_candidates_for`, exactly as it already passed `pool_free_left=pool_open` to question 2.
6. **One existing test's fixture moved (AC-U7).** `tests/test_so_supply_confirmation.py::test_the_frozen_proposal_does_not_depend_on_the_order_the_lines_were_posted_in` had two lines of one item, location AND date, which under v6 are one unit with no internal walk order to be sensitive to; its own control assertion (`a_then_b[10] != a_then_b[20]`) could no longer hold. The lines are now a week apart, so they are two units and the test keeps its subject. Its composition and the Buy's reason are asserted too, so the extra week is proven to be the ledger rather than the ATP window.
7. **The split reason is the unit's, verbatim (S6).** Line 31 renders "Reserve 5" beside a sentence naming the pool's 25. Left alone deliberately: the sentence that explains it is the unit tooltip of AC-F1, on the frontend.

### Follow-up, NOT built: the donor GROUP ledger (S4)

`_cross_group_borrow_candidates` rebuilds `group_left` per call from `donor_group_net(...).offer`, so the per-WAREHOUSE ledger added in section 3.5 does not bound a donor GROUP. Scenario: the NT group holds 10 at `DC1-NT` and 10 at `MWH-NT` and nets 10 between them; unit A borrows 10 at `DC1-NT` (ledger: DC1-NT 0), unit B is then offered 10 at `MWH-NT` because its own warehouse ledger is untouched and the group's net is re-read live. Two units take 20 out of a group that has 10. The confirmation's `_BorrowLedger` is per warehouse too, so it would not catch it either. Same shape as 3.5, one level up; build it when a live confirmation refuses a borrow the board proposed across two warehouses of one donor group.
