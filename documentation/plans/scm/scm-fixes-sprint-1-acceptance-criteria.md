# UAC: SCM fixes sprint 1 - the Coverage panel agrees with its own timeline

**Status:** GRILLED 24 August 2026; BL-027 added as Group G.
**Plan:** `PLAN-scm-fixes-sprint-1.md`
**Branch:** `feat/scm-fixes-improvements` (worktree `.claude/worktrees/scm-fixes`)

## Journey

**Actor:** the buyer (purchasing planner) deciding whether to spend money on a container.

1. They arrive from the sidebar: Supply Chain -> Reorder Planning, on today's plan.
2. They open a plan row and read its **Coverage panel**: opening balance, own / pool /
   other-holder split, the dated timeline beside it, and the verdict (`Buy N` or `Use stock`).
3. The system already knows everything the verdict needs: on-hand stock, reservations,
   dated open sales orders, dated shipments on the water with their per-site allocations,
   receipts already taken. **No question is asked of the buyer.** Their single decision is
   "accept the Buy, or not".
4. They act on the verdict. If the panel says `Buy 100` beside a timeline that never dips
   below zero, one of the two is lying, and today the loud one is. The buyer either orders
   a container already on the water or learns to ignore the panel. Either way the tool is
   abandoned in week one.
5. At the end they hold a verdict they can act on: a buy quantity that equals the peak
   deficit of the timeline they are looking at, a source split that says where today's
   cover comes from (with the pool named), and an explicit report of any commitment or
   on-order quantity the data cannot place at a site - never silently dropped.
6. Nobody else is told automatically; this sprint changes no notification.

A second, smaller journey: the same buyer reads a plan row for a product whose pool already
covers the committed quantity. CS already decided the line needs buying; the engine's job is
to SAY "the pool has 5, you committed 1" as a suggestion, not to drop the row and decide
"use stock" for them. The row must carry both numbers the choice turns on.

Two hygiene items ride along because they cost less than a plan of their own: a model
constraint that hides a CI test (BL-036), and a backlog entry whose fix already shipped
without a test (BL-025). Ten stale `fm/scm-*` PRs are closed with a pointer to the merged
PR that absorbed each.

## Investigation note (24 Aug)

The 7 Coverage defects are already fixed on main (#222). The 8 tests are red only because
the fixture predates S13b: project demand counts only with `demand_origin = order_inquiry`.
Groups A-D therefore hold as the CONTRACT (they must stay green), and the work is the
fixture repair in S1 plus one new guard (AC-A06). See the plan, section 1.

## Phase 2 (backend, test-first; the red tests already exist)

### Group A: buy_qty is the timeline's peak deficit

- **AC-A01 [BE][T]** Given 500 allocated on a shipment arriving in 10 days and 100 due in
  30 days with nothing on hand, When coverage is resolved for the pool, Then
  `timeline.closing_balance == 400`, `peak_deficit == 0`, `buy_qty == 0`, `use_stock` is
  true. (`test_supply_arriving_before_the_demand_means_nothing_has_to_be_bought`)
- **AC-A02 [BE][T]** Given 100 due in 30 days and 500 arriving in 50, Then
  `closing_balance == 400`, `peak_deficit == 100`, `buy_qty == 100`, `use_stock` false.
  A fix that trusts the closing balance fails this. (`test_supply_arriving_after_...`)
- **AC-A03 [BE][T]** Given nothing on hand, nothing on order, 100 committed, Then
  `buy_qty == 100 == peak_deficit`. A fix that returns zero fails this.
  (`test_with_no_supply_at_all_...`)
- **AC-A04 [BE][T]** Given 30 in the pool and 500 arriving before 100 is due, Then the
  allocations still report 30 as pool cover, and no residual "buy 70" survives.
  (`test_the_allocations_still_say_where_todays_cover_comes_from_when_nothing_is_bought`)
- **AC-A05 [BE][T]** In every case `cov.buy_qty == cov.timeline.peak_deficit`; the two are
  one number, not two computations.
- **AC-A06 [BE][T]** Given a `demand_class="project"` line with NO `demand_origin`, When
  coverage is resolved, Then it is NOT a demand event on the timeline (the S13b rule,
  pinned at the reader so the next fixture drift fails loudly).

### Group B: a reservation is demand once

- **AC-B01 [BE][T]** Given 100 on hand all reserved against one open order of 100, Then
  `opening_balance == 100`, `availability.pool == 100`, allocations `[(pool, 100)]`,
  `closing_balance == 0`, `buy_qty == 0`, `use_stock` true.
  (`test_a_reservation_is_demand_once_not_twice`)
- **AC-B02 [BE][T]** Given 200 on hand, 60 reserved, 60 committed, Then
  `availability.pool == 200` (on-hand basis, same as the opening balance) and
  `closing_balance == 140`, `buy_qty == 0`. (`test_partly_reserved_stock_...`)
- **AC-B03 [BE][T]** The availability split and the opening balance share one basis:
  on-hand. The timeline is the only place a promise is subtracted.

### Group C: unplaceable rows are reported, never swallowed

- **AC-C01 [BE][T]** Given a sales-order line of 80 with `warehouse_id IS NULL`, Then the
  coverage result reports 80 under an unplaceable-demand field (one of the names
  `_UNPLACEABLE_DEMAND_FIELDS` accepts) and the pool balance is unchanged.
  (`test_demand_with_no_warehouse_is_reported_rather_than_swallowed`)
- **AC-C02 [BE][T]** Given a purchase-order line of 500 with a NULL warehouse, Then 500 is
  reported under an unplaceable-supply field and in-transit stays 0. (already green;
  stays green)
- **AC-C03 [BE][T]** Given the same two rows, Then `closing_balance == 0` and the timeline
  carries no row for them - reported, not netted into whichever pool was asked. (guard,
  already green)
- **AC-C04 [BE][T]** Given a line that DOES have a warehouse, Then the unplaceable fields
  are `None`/0 and the timeline is normal. (guard,
  `test_a_line_that_does_have_a_warehouse_is_not_reported_as_unplaceable`)
- **AC-C05 [BE]** The `Coverage` response schema exposes the unplaceable demand and
  supply quantities to the frontend (the `response_model` must declare them; asserted in a
  route test).

### Group D: the pool keeps its name

- **AC-D01 [BE][T]** Given a pool warehouse with `counts_as_available = False` and a
  member bin holding 400, Then `pool_code` is the pool's code and `opening_balance == 400`.
  (`test_the_pool_keeps_its_name_when_the_pool_bin_itself_is_unavailable`)

### Group E: covered demand is a suggestion that states both numbers

- **AC-E01 [BE][T]** Given 1 committed at a bin and 500 available in the same pool, When
  the reorder run completes, Then a `rec_type == "covered"` row exists for the product
  with `inputs.covered_committed == 1`, `inputs.covered_available == 500`, and
  `triggered_reason` contains "available in this pool".
  (`test_the_row_states_both_numbers_the_choice_turns_on`)
- **AC-E02 [BE][T]** The three sibling tests in `test_covered_demand_surfaces.py` that
  already pass keep passing; all four lose their `xfail` marker. The fixture enables
  `pool_netting` and self-references the pool root, as production does.
- **AC-E03 [BE][T]** (gated on grill Q1) Given pool netting OFF, a bin short by 1 and a
  sibling bin of the same pool holding 5, When the run completes, Then the bin's row is
  still a `buy` of 1 AND carries `inputs.sibling_available == 5` (a sibling lends only
  what it has not itself committed; a run scoped to the short bin alone sees no siblings),
  `inputs.sibling_pool_code == <pool code>`, and its `triggered_reason` names the 5.
- **AC-E04 [E2E]** The Reorder Planning row shows that reason text in the browser, reached
  by sidebar clicks.

### Group F: hygiene

- **AC-F01 [BE][T]** `Supplier` model declares the per-company key in `__table_args__` in
  the SAME form migration 305 created it (`Index(..., unique=True)` named
  `uq_suppliers_company_supplier_code`, since 305 emitted CREATE UNIQUE INDEX) and no
  column-level `unique=True`, so autogenerate reflects no diff. No new migration.
- **AC-F02 [BE][T]** The probe-and-skip at
  `tests/scm/test_outstanding_import_company_isolation.py:611` is deleted and
  `test_a_creditor_code_owned_only_by_another_company_gets_its_own_row_back_created` runs
  and passes on a `create_all` schema.
- **AC-F03 [BE][T]** A test proves `procurement_service.update_shipment` keeps a line's
  `unit_cost` and `currency` when the payload omits them; BL-025 is marked Done with the
  test name.
- **AC-F04 [T]** `test_coverage_arithmetic.py`: every `xfail` marker removed; the file is
  fully green. Module docstring rewritten from "seven confirmed defects" to the contract it
  now pins.
- **AC-F05** PRs #192, #204, #207, #208, #209, #212, #213, #214, #228, #229 are closed with
  a comment naming the merged PR that absorbed each (#222, #223, #231, #237).

### Group G: the seven /scm grids sort (BL-027)

- **AC-G01 [FE][T]** For each of the seven grids, clicking a sortable column header
  reorders the rows; a second click reverses; quantity and money columns sort numerically
  (9 before 10), date columns chronologically.
- **AC-G02 [FE][T]** Every id-only computed column that shows a sort arrow has an
  `accessorFn` so it sorts on the displayed value.
- **AC-G03 [FE][T]** One vitest per grid asserts AC-G01 on three rows.
- **AC-G04 [E2E]** Sort verified in the browser via sidebar clicks on Reorder Planning
  (PO worklist tab) and Incoming Containers (consolidated packing list).

### Non-functional

- **AC-N01 [T]** `pytest tests/scm -q` has no new failures against the pre-sprint run.
- **AC-N02 [E2E]** Coverage panel verified in the browser via sidebar clicks for one real
  product with a live reservation and one with a shipment on the water: the verdict equals
  the timeline's peak deficit. Evidence recorded in the plan.
- **AC-N03** No em-dashes or en-dashes in any line added.

## Out of scope (backlog)

- Defect 3 (partial receipt across pools) and defect 7 (epsilon vs rounding): their tests
  already pass on main; nothing to do. Confirm in AC-F04's run.
- Ladder v2 rule questions, section-13 board scoring, BL-027 sorting, BL-024 precision,
  BL-043/044: sprint 2.
