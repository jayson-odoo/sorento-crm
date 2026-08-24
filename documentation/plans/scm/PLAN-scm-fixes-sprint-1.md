# PLAN: SCM fixes sprint 1 - retire the red tests, close the sibling-stock gap, hygiene

**Status:** GRILLED 24 August 2026 (Q1 = A, Q2 = project + order_inquiry origin, Q4 = add BL-027 as S5; Q3 pending the captain's go). Implementation in progress.
**UAC:** `scm-fixes-sprint-1-acceptance-criteria.md`
**Branch:** `feat/scm-fixes-improvements` (worktree `.claude/worktrees/scm-fixes`, FE 3020 / BE 8020)
**Base:** `origin/main` e6ccd915c

## 1. What the investigation found (this changes the sprint)

The sprint was scoped from the inventory line "7 confirmed Coverage-arithmetic defects, 8 red
tests". Running the tests on main today and reading the failures:

| Finding | Evidence |
| --- | --- |
| The 7 Coverage defects are ALREADY FIXED on main by #222. `coverage_service.py` has `buy_qty = timeline.peak_deficit` (l.1044), on-hand-basis availability (l.776), `unplaceable_demand_qty` / `unplaceable_on_order_qty` on `Coverage` (l.243), `pool_code` fallback (l.810). | `app/services/scm/coverage_service.py` |
| The 8 tests are red for ONE reason: the fixture seeds `demand_class="project"` with no `demand_origin`, and S13b (#223) made project demand count only where the Order Inquiry created it (`is_plan_demand_order`: class is not project OR origin = order_inquiry). The seeded line is filtered out, so every case sees zero demand. | `app/services/scm/demand.py:147`; scratch run with `demand_class="retail"`: **19/19 pass** |
| Covered-demand test: 3 of 4 already pass. The 4th (`covered_available == 500`) fails because the fixture never enables pool netting, and `_pool_netting_enabled` is OFF by default; each bin is its own singleton pool so "available in this pool" is the bin's own 0. Scratch run with `UPDATE scm.reorder_policy SET pool_netting = true`: **6/6 pass**. | `reorder_run_service.py:_pool_netting_enabled`; live DB: all 5 policies `pool_netting = false` |
| So the real, still-open gap behind the captain's quote ("BRW holds 5, it still needs buying, but SAY it") is narrower than the test claims: **under pool netting OFF (the live state), a bin short by 1 with 5 in a sibling bin of the same pool gets a plain Buy row and the 5 are never mentioned.** `_transfer_flags_for` only fires on overstock-vs-short, not on "sibling has enough". CORRECTION (S2 build): this holds for RETAIL-class (or firm Project) demand, which is netted and sized. UNCLASSIFIED committed demand is carried, never sized, so with netting off it yields a `covered` row reading "0 available in this pool covers 1 committed" - a self-contradiction on the same panel. Not in this UAC; sprint-2 ticket. AC-E03 is seeded retail. | run instrumented: both bins went through `_emit_cell` |
| Real pool roots self-reference (`pool_warehouse_id = id`, 16/16); the fixture root has NULL. Harmless today (`_pool_map` COALESCEs), but the fixture should match reality. | live DB query |

Consequence: Groups A-D are a **fixture repair + xfail removal**, not engine work. Group E has
one engine decision (section 4, Q1). Nothing in this sprint needs a migration.

## 2. Slices

### S1 - Coverage tests tell the truth again (UAC A, B, C, D, F04) [BE][T]

- `tests/scm/test_coverage_arithmetic.py::_so_line`: seed `demand_origin=ORDER_INQUIRY_ORIGIN`
  beside `demand_class="project"` (import both constants from `app.services.scm.demand`).
  The docstrings describe a project customer (TUJU RESIDENCE); keeping the class truthful
  and adding the origin is the fixture that matches S13b, not a retreat to retail.
- Remove all 8 `@pytest.mark.xfail` markers. Rewrite the module docstring: it no longer
  pins seven defects, it pins the contract #222 delivered (buy_qty is the peak deficit,
  availability shares the timeline's on-hand basis, unplaceable rows are reported not
  netted, the pool keeps its name).
- Add one guard test: a `demand_class="project"` line WITHOUT `demand_origin` is NOT
  demand on the timeline (the S13b rule, pinned here so the next fixture drift is caught
  at the reader, not two weeks later).
- AC-C05: assert `unplaceable_demand_qty` / `unplaceable_on_order_qty` in the coverage
  route's response (check `app/schemas/scm_coverage.py` declares them; `response_model`
  drops undeclared fields silently).

### S2 - Covered demand states both numbers, netting on or off (UAC E) [BE][T]

- `tests/scm/test_covered_demand_surfaces.py`: fixture sets the root self-referencing
  (`_pool(db, root, root)`) and enables `pool_netting` on the policy inside the savepoint
  (same pattern as `test_demand_breakdown.py:210`). Remove the 4 xfail markers.
- Engine change, gated on Q1: under pool netting OFF, when a bin's Buy row is emitted and a
  sibling bin of the same pool holds on-hand >= the committed shortage, the Buy row carries
  `inputs.sibling_available` (sum of sibling on-hand) and `inputs.sibling_pool_code`, and
  the reason label appends "; <n> available at <pool> (netting off)". No change to the
  quantity bought. A new test pins it: netting off, bin short 1, sibling 5 -> Buy 1 with
  `sibling_available == 5`.
- Frontend: the Reorder Planning row already renders `triggered_reason`; no new column.
  Verified in the browser via sidebar clicks on a product whose plan shows the hint.

### S3 - BL-036 supplier_code constraint (UAC F01, F02) [BE][T]

- `app/models/procurement.py:44`: drop `unique=True`; add
  `__table_args__ = (UniqueConstraint("company_id", "supplier_code",
  name="uq_suppliers_company_supplier_code"), ...)` merged with whatever `__table_args__`
  the class already carries. No migration: 305 already did this in prod.
- Delete `_schema_isolates_supplier_code` and its skip in
  `tests/scm/test_outstanding_import_company_isolation.py`; the test runs.
- Run `tests/scm/test_outstanding_import_company_isolation.py` and
  `tests/test_procurement*.py` on a fresh `create_all` schema (the `zzt_` scratch schema
  fixture) to prove nothing else relied on the global unique.

### S5 - BL-027: the seven /scm grids sort (UAC G) [FE][T]

- Files: `reorder/components/{PoWorklistView,PlanExceptionsView,NeedsLevelView,CoveredByStockView}.tsx`,
  `simulation/components/ScenariosGrid.tsx`, `loading-plan/components/LoadingPlanView.tsx`
  (its table now lives in a child; find the `useReactTable` that renders it),
  `incoming/components/ConsolidatedPackingListPanel.tsx`.
- Pattern already proven on `reorder/components/PlanLinesGrid.tsx` and
  `SummaryOrderReportView.tsx`: `SortingState` + `onSortingChange` + `getSortedRowModel()`,
  numeric `accessorFn` on quantity/money columns, ISO-date `accessorFn` on date columns,
  and an `accessorFn` for every id-only computed column (the way "Still owed" did).
- One vitest per grid: render with three rows, click the header, assert row order flips
  numerically (not lexically: 9 < 10). Browser check via sidebar on Reorder Planning and
  Incoming Containers.

### S4 - Hygiene (UAC F03, F05) [T]

- BL-025: one test on `procurement_service.update_shipment` - a line saved with
  `unit_cost=12.5, currency="USD"`, edited with a payload naming only `product_id` and
  `quantity_shipped`, keeps both. Mark BL-025 Done in `documentation/backlogs/backlog.md`
  naming the test.
- Close PRs #192, #204, #207, #208, #209, #212, #213, #214, #228, #229 with one comment
  each: "Superseded: this content landed on main via #222 / #223 / #231 / #237 (squash).
  Closing; the branch stays." Mapping: 192/204/207/208/209/212/213/214 -> #222; 228 -> #223;
  229 -> #231. **Outward-facing; needs the captain's go (Q3).**

## 3. Testing seams

- Coverage: `CoverageService(db).coverage_for(product_id, pool_id=...)` against the `ZZT`
  rolled-back chain - already the seam the file uses.
- Reorder run: `svc.create_run(db, codes, enqueue=False)` + `svc.run_reorder(run_id, db=db)`
  then read `scm.reorder_recommendation.inputs` - already the seam.
- Model constraint: `create_all` on the scratch schema; assert the constraint name via
  `inspect(engine).get_unique_constraints("suppliers")`.
- No new FE unit tests: no FE code changes in this sprint.

## 4. Open questions for the grill

- **Q1 (S2, engine) - ANSWERED A by default (no objection at grill):** Under pool netting OFF, should the Buy row SAY "5 available at
  BRW-BB"? Options: (a) yes, as `inputs.sibling_available` + reason suffix, quantity
  unchanged [recommended: matches the quote, changes no number]; (b) no - the answer is
  "turn pool netting on for that policy", and the sprint only repairs the fixture; (c) emit
  a second `covered` row beside the Buy (rejected: two rows for one line contradicts the
  whole-line rule).
- **Q2 (S1):** Fixture keeps `demand_class="project"` and adds `demand_origin="order_inquiry"`
  (truthful to the docstrings) rather than switching to retail. Objections?
- **Q3 (S4):** Go to close the ten stale PRs with the superseded-by comment?
- **Q4 (scope) - ANSWERED: BL-027 pulled in as S5.** Freed capacity. With A-D collapsing to a fixture fix, sprint 1 has room
  for one more item from the inventory: BL-027 (seven grids that show a sort arrow and
  never sort) or BL-024 (plan grid rounds to whole units vs summary's `uom_decimal_places`).
  Pull one in, or ship sprint 1 small?

## 5. Out of scope

Ladder v2 rule questions, section-13 board scoring, BL-043/044, dead mock stores, Stage 3
AC-F04 rollup: sprint 2 per the inventory.

## 6. Evidence

- **AC-G04 (24 Aug, agent-browser on :3020, sidebar route Supply Chain > Incoming Containers > BEAU4776828, 43 lines):** Qty header click 1 ordered the column 20, 24, 60, 78, 90, 100 (numeric, not lexical); click 2 ordered it 6,000, 6,000, 5,000, 5,000, 4,000, 3,500. `errors` empty. The PO worklist on the current run is empty (nothing decided), so its sort is covered by vitest only.
- Incidental: during the run Postgres briefly entered recovery; `GET /scm/inbound-shipments` returned 401 (auth dependency maps a DB error to 401) and the page painted "No container read yet" over it. Logged as BL-045 candidate: an unreachable database should read as 503, and the empty state must not mask a failed read.
