# Stage 0 readiness: SCM front planning

**Status:** DONE for Stage 0 and Stage 1A, 17 August 2026. Work branch `fm/scm-front-stage0-1a`;
landing branch `fm/scm-stage0-1a-land`, created from that ref and the one that carries the PR.

**Plan:** `PLAN-scm-front-planning.md`. **UAC:** `UAC-scm-front-planning.md`.

This note records the Stage 0 gate outputs the plan asks for: the implementation baseline
contract and merge base, the reconciliation of that baseline with current SCM core, the
`scm.reorder_level` profile, the tests identified for deliberate contract replacement, and the
golden fixtures written before any calculation code exists.

## 1. Branch contract and merge base

| Item | Value |
|---|---|
| Implementation baseline | `origin/feat/project-lead-to-so` at `aab24c0c3550e2837b52abdff1342126acdaabe5` |
| Baseline merge base with `origin/main` | `43e6f553c31f6ade1ab875464cf3749b224f5ca5` |
| Plan branch (PR #192) base on `origin/main` | `b6379b59b3402cbc6262e5d3a722921b6004489c` |
| Merge commit bringing the baseline onto this branch | `90bde5eb` (655 files, 12 hand-resolved conflicts) |
| Alembic join of the two chains | `2c859e3161da` (empty merge of `354_projects_schema_move` and `366_merge_363_365`) |
| First Stage 0 migration | `372_project_so_line_core_link` (368 to 371 are held by sibling branches) |
| Merge of `origin/main` onto the landing branch | `38862e72d` (7 hand-resolved conflicts, all union-preserving except the two select components) |
| Alembic join of the two 372s | `1925dbc3f`, revision `373_merge_scm_stage0_1a` (empty merge of `372_merge_three_heads` and `372_project_so_line_core_link`) |

The projects schema move (migration 354, ADR-0011) is preserved exactly as the baseline has it:
47 tables under `projects`, models pin `__table_args__ schema="projects"`, core FKs stay bare.

Conflict resolutions (all unions of intent, none dropped a side): `public/__init__.py` router
mounts, `scm/purchase_history.py` order-inquiry shim, `entity_resolver.py` savepoint around the
schema-qualified table name, `product_service.py` and `ProductAttachmentsTab.tsx` (both lineages
had fixed the same brochure-image bug; main's funnel kept), `project_order_inquiry_import_service.py`
(branch ownership move plus main's outcome codes), `status_engine/registry.py` (both bootstrap
paths run), `bootstrap_env.py`, `_pg_fixture.py` (`scm`, `dealer_kit`, `projects` schemas),
`conftest.py` (advisory lock outside, prefix sweep inside), `test_company_scope.py` (105 mappers
then, 108 after the `origin/main` merge below, both measured), `worker.py` (queue union including
`project_docs`). Two clean auto-merges were broken and repaired: `app/tasks/import_tasks.py`
imported the moved `scm.order_inquiry_service`, and the branch's photo test pinned a control main
had replaced.

The second merge (`38862e72d`) brought `origin/main` forward onto the landing branch and conflicted
in seven files. Six are unions of intent with nothing dropped: `public/__init__.py` router mounts
again (this branch's `geo` and `quotation_sign` beside main's `onboarding`), `models/access.py`
(`RespondContact` keeps both new columns, `requires_registered_project` and `outbound_enabled`),
`test_company_scope.py` (the owned-table tripwire is main's 67 plus this branch's 41, and 108 is
what the mappers measure), `test_schema_uuid_id_principle.py` (main's `team_member_brands` beside
this branch's schema-qualified `projects.*` junctions), and `sorento_crm_mcp/server.py` twice, where
the project-sales slimming and main's `company_id` strip are disjoint additions that only collided
by landing at the same offset. The seventh is the one genuine rewrite: `SearchableSelect.tsx` and
`SearchableMultiSelect.tsx` both took main's newer `wrapOptions` branching shape, with this branch's
16rem menu floor folded into the non-wrap arm so neither intent is lost. Main's three new owned
tables are what moves the mapper count from 105 to 108.

Merged-tree smoke: every Project Sales suite green (108 tests), migration 354 suite green,
`tests/scm` 1502 passed with 55 failures all classified as pre-existing shared-DB drift or the two
`test_m3_run.py` failures that predate the merge (default `buy_scope` flip in `1dc247982`).

## 2. No duplicate tables

The plan's target model (section 6) maps onto existing baseline tables. Nothing new is proposed
where a table already exists:

| Plan concept | Existing table (baseline) | Stage 0 action |
|---|---|---|
| Accepted demand and dates | `projects.po_versions`, `po_lines`, `delivery_schedules`, `delivery_schedule_versions`, `delivery_phases`, `delivery_schedule_cells` | reuse |
| Project SO header to core SO | `projects.sales_orders.so_id` | reuse |
| Project SO line to core SO line | `projects.sales_order_lines` | add `core_sales_order_line_id` (372) |
| Component ledger | `projects.so_line_allocations` (`own`, `brw`, `other_project`, `order`) | reuse; `other_location`, `decision_id`, `reason`, `donor_impact_snapshot` land in 1C |
| Cross-project Borrow audit | `projects.allocation_claims` | reuse; direct-accepted write lands in 1C |
| Buy handoff | `projects.order_inquiries`, `order_inquiry_rows` | reuse; `supply_decision_id` lands in 1C |
| Decision revision | `projects.so_supply_decisions` | new in 1C (does not exist anywhere today) |
| Channel class | `sales_orders.demand_class` via `app.services.scm.demand_class.class_of` | reuse; sheet stamp routed through mapper |

## 3. Order Inquiry rule applied now

`ProjectSODraftService.publish` no longer calls `derive_for_sales_order`; publish writes status,
actor and timestamp only, and `PublishResponse` drops `order_inquiry_id`. `derive_for_sales_order`
remains in `project_order_inquiry_service.py` as the engine Stage 1C's atomic confirmation will
call with the confirmed Buy residual only. `derive_for_amendment` is untouched (amendment
exception verbs stay separate). Publish still writes no core `sales_orders` row, so it is not a
demand-class stamp point.

Untouched means still live: `project_so_delta_service.publish_amendment` (~line 680) calls
`derive_for_amendment` on every amendment publish, so amendment exception verbs (DELAY, ADVANCE,
CANCEL BALANCE) still reach `order_inquiry_rows` BEFORE any Stage 1C supply confirmation.
Filtering them out of the demand readers is Stage 1C's job, and AC-A04 depends on it.

## 4. Two quantity paths, and the one invariant that replaces them

Baseline path A: `ProjectAllocationService.confirm` writes `so_line_allocations` summing to at most
`line.qty`, guarded by live stock. Baseline path B: `ProjectOrderInquiryService.derive_*` nets the
same `line.qty` against pre-order and inbound pools into `order_inquiry_rows`. The two never share
a ledger. Stage 1C replaces both with the section 3.1 balance
`open_so_qty = timely_spo_coverage + reserve + borrow + buy`, evaluated once per line inside the
atomic SO confirmation. The golden cases in `tests/scm/front_planning_golden.py` pin the target
numbers now; `tests/scm/test_front_planning_golden.py` XFAILs strictly until the engine exists.

## 5. Tests identified for deliberate contract replacement (AC-H01)

Replaced in Stage 0:

- `tests/test_project_order_inquiry.py::test_publishing_a_sales_order_raises_one_inquiry_row_per_line`
  is now `test_publishing_a_sales_order_raises_no_inquiry_row` (AC-D01). Every other test that
  used publish as the trigger calls `derive_for_sales_order` directly, so the netting engine stays
  pinned until 1C.

Kept as-is until Stage 1C replaces the behaviour they pin:

- Per-line partial allocation: `tests/test_project_allocation.py::test_a_partial_decision_reads_as_partial`,
  `::test_confirming_a_source_stamps_it_and_becomes_the_stock_location`, `::test_a_split_reads_as_both_locations`,
  `::test_an_override_replaces_the_previous_decision`, `::test_clearing_the_decision_unallocates_the_line`.
- Second-approver Borrow (requested to accepted claim): `tests/test_project_allocation.py::test_a_cross_project_pull_raises_a_claim_and_moves_nothing`,
  `::test_confirming_a_held_source_without_an_accepted_claim_is_refused`, `::test_accepting_a_claim_sources_the_line`,
  `::test_only_the_holding_projects_cs_may_answer_a_claim`, `::test_a_refusal_needs_a_reason`, `::test_a_claim_is_answered_once`.
- Independent inquiry netting: `tests/test_project_order_inquiry.py::test_a_pre_order_on_the_same_project_nets_off_the_earliest_dates`,
  `::test_a_pool_already_promised_to_an_earlier_publish_is_not_promised_twice`, `::test_stock_on_the_water_carries_its_spo_reference`,
  `::test_demand_landing_inside_the_reserve_window_is_reserved_as_well_as_ordered`, and `tests/test_project_order_inquiry_engine.py`.
- Same-day ordering: `tests/scm/test_coverage_timeline.py::test_same_day_demand_is_ordered_before_supply` (1C flips it with `_sort_key`).

## 6. Classification precedence and stamp points (plan 5.2)

- Mapper: `app/services/scm/demand_class.py::class_of` (substring `project` / `projects` / `contract`
  to `project`, any other stated value to `retail`, nothing stated to `None`). Pinned in
  `tests/scm/test_demand_class_mapper.py`.
- Precedence: `outstanding_import_service._classify_demand` reads stored `order_type`, stated
  `order_type`, customer market segment, then `sales_agents.demand_class` (present on `main`, now on
  this branch after the merge).
- Stamp points: outstanding-order import (`outstanding_import_service`, line ~1167) and the sheet
  import (`project_order_inquiry_import_service`, now `demand_class=class_of(order_type)`). Publish
  stamps nothing.
- Compatibility: `summary_order_service._demand_aggregates` still splits on `order_type`; its
  re-base onto `demand_class` is Stage 2 work and is not touched here.

## 7. `scm.reorder_level` profile (informational; Q7 says sum)

Measured on the local prod-copy database on 2026-08-17:

| Measure | Count |
|---|---|
| Rows | 24,311 across 11,172 products |
| Product-wide rows (`warehouse_id IS NULL`) | 11,007 |
| Rows with `level IS NULL` | 13,302 |
| Products with more than one concrete location row | 2,567 (2,565 identical across locations, 2 conflicting) |
| Products with both a product-wide row and location rows | 3,107 |

The Q7 rule (product level = sum of concrete location levels, NULL or absent as 0, product-wide rows
not a competing winner) needs no consolidation: conflicts are two products, and the sum is computed
at read time in Stage 3.

## 8. Other Stage 0 confirmations against main

- `scm.committed_v` is one row per `(product_id, warehouse_id)` (migration 346), `net_position_v`
  keys off it (migration 311); the channel columns land in Stage 2 on that same row.
- `warehouses.segment`, `is_active`, `counts_as_available`, `pool_warehouse_id` and
  `scm.item_classification.abc_class` / `computed_at` all exist, so the section 3.3 predicate is
  computable from existing data.
- `units_of_measure` has no `decimal_places` yet (Stage 2 adds and backfills it).
- `reorder_engine.allocate(buy_qty, warehouses)` returns integers; the decimal generalisation is
  Stage 2.

## 9. Stage 1A outcome

The baseline already persists dated release lines: `ProjectSODraftService.build` spreads accepted
PO lines across confirmed schedule phases into `projects.sales_order_lines` (`delivery_date`,
`phase_id`) grouped one Project SO per area group, and `import_file` renders the AutoCount CSV.
Stage 1A adds only: a copy-friendly worksheet read (`GET /project-sales/sales-orders/{id}/worksheet`
plus the `/worksheet` screen) sharing the CSV row builder, and idempotent rebuild. The rebuild
guarantee is per area group, not per build: a group that was drafted before keeps the provisional
reference CS has written down, and a group that appears for the first time (a revised schedule
adding one) is minted a fresh reference that can never be one still owed to a carried group. Same
inputs, same line set. No AutoCount write. Demand stays uncommitted and outside Purchasing.

`can_export` is enforced, not reported: `GET .../import-file` answers 422 `so_export_blocked`
unless the order is published (or amended) with no unacknowledged hard finding.

## 10. Stage 1A evidence run (agent-browser, 2026-08-17)

Stack: backend `uvicorn` on 8020, frontend `npm run dev` on 3021 (this worktree's `.env.local`
origins), private session `stage1a-p2`, login with the `E2E_EMAIL` / `E2E_PASSWORD` pair.

Steps by clicks from `/`: sidebar Project Sales, Pipeline, project PRJ-000002, Sales orders tab,
row PSO-000002, Worksheet button. `get url` confirmed at every hop.

- `network requests --filter /api/v1/project-sales` shows
  `GET /api/v1/project-sales/sales-orders/{id}/worksheet 200`.
- `errors` empty; `console` only dev noise (i18next, Fast Refresh, the pre-existing tiptap
  duplicate-extension warning).
- Screen: PSO-000002, Blocked, TOWER, customer PO HQ/26/01/121, 101 lines with Reserve Qty 0,
  total RM 454,724.68 (equals the list row), Validation card "36 stops the export" (equals the list
  row's 36 blocking; the copy now reads "36 findings stop the export" after the review), both
  export actions disabled with title "Publish first".
- Viewports 1280x800 and 375x812 both rendered without overflow.
- Backend tests: `tests/test_project_so_worksheet.py` (16), `tests/test_project_so_line_core_link.py`
  (3) and `tests/test_project_so_draft.py::test_rebuilding_from_the_same_inputs_is_a_no_op` cover the
  published-clean, published-with-hard-finding, 404, auth-denial, CSV parity and no-op rebuild
  cases the local data cannot show (every local project SO is blocked).
- Frontend: 49 across the four suites the worksheet touches, measured together:
  `SalesOrderWorksheetClient.test.tsx`, `useSalesOrderWorksheet.test.tsx`,
  `SalesOrderDetailClient.test.tsx` and `projectSalesOrderService.test.ts` (the last two carry the
  download repair below).

Regression guard for the flow is this recorded run, not a new Playwright spec, per the standing
order in CLAUDE.md.

One repair found by the evidence run and fixed on this branch: the AutoCount import file was
downloaded through a frontend-origin anchor on three screens (SO detail, publish dialog, the new
worksheet) and 404ed; all three now share one api-client blob download with the filename taken
from Content-Disposition.
