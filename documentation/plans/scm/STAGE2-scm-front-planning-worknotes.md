# Stage 2 worknotes: Product plan and channel breakdown

**Status:** IN PROGRESS, 17 August 2026. Branch `fm/scm-stage2-product-plan`, stacked on
`fm/scm-stage0-1a-land` (PR #204).

**Contract:** `PLAN-scm-front-planning.md` sections 5.1 to 5.4, 6.4 and 7 "Stage 2";
`UAC-scm-front-planning.md` Groups E (AC-E01..E07) and F (AC-F01..F12). The plan and UAC win over
this file; this file only slices the work and records where the code lives so the coder does not
rediscover it. Stage 3 (reorder-level rollup, hardening sweep) is not in scope; AC-F04/F05 are
supported by the data model but not built here, and no "Needs level" state or level worklist exists.

## 0. Decisions taken at slicing time (flagged in the PR body)

1. **`projects.so_supply_decisions` lands here, read-only.** Section 4 defines "decided" as
   `projects.sales_orders.so_id = sales_orders.id` with an active `projects.so_supply_decisions`
   row, and AC-E04 reads confirmed unplaced Buy from `projects.order_inquiry_rows` through
   `core_sales_order_line_id`. Neither the table (plan 6.2) nor `order_inquiry_rows.supply_decision_id`
   (plan 6.3) exists yet because Stage 1C has not started. Stage 2 creates both exactly to the 6.2/6.3
   column list so the section 4 predicate is a real SQL predicate and AC-E04 can seed decisions in
   tests. No service writes them in Stage 2; Stage 1C owns the atomic confirmation that does.
   **Exact shape Stage 2 creates and Stage 1C must match** (source: plan section 6.2 and 6.3,
   `projects` schema, `__table_args__ schema="projects"`, uuid ids like every other `projects.*`
   table):

   `projects.so_supply_decisions`

   | Column | Type | Null | Notes |
   |---|---|---|---|
   | `id` | UUID | no | PK, `gen_random_uuid()` default |
   | `company_id` | UUID | no | FK `companies.id`; `CompanyScopedMixin` (owned, not shared) |
   | `project_sales_order_id` | UUID | no | FK `projects.sales_orders.id` ON DELETE CASCADE |
   | `revision_no` | Integer | no | 1-based per Project SO |
   | `state` | String(16) | no | CHECK in (`active`, `superseded`, `challenged`) |
   | `source_revision` | String(64) | yes | source document/version reference the decision was taken on |
   | `line_snapshots` | JSONB | no | list of per-line objects (plan 6.2 list); default `[]` |
   | `confirmed_by` | UUID | yes | FK `users.id` ON DELETE SET NULL |
   | `confirmed_at` | TIMESTAMP (naive UTC) | no | `now()` default |
   | `supersedes_id` | UUID | yes | self FK ON DELETE SET NULL |
   | `superseded_at` | TIMESTAMP | yes | |
   | `superseded_reason` | Text | yes | |
   | `created_at` / `updated_at` | TIMESTAMP | no | audit convention |

   Constraints: `uq_projects_so_supply_decision_rev` UNIQUE `(project_sales_order_id, revision_no)`;
   partial unique index `uq_projects_so_supply_decision_active` on `(project_sales_order_id)`
   WHERE `state = 'active'`; index on `(company_id, state)`.

   `projects.order_inquiry_rows.supply_decision_id` UUID NULL, FK `projects.so_supply_decisions.id`
   ON DELETE SET NULL, index `ix_project_order_inquiry_rows_supply_decision`. Stage 1C adds the
   "one active unplaced row per active decision and SO line" enforcement; Stage 2 only reads.

   **What the Stage 2 predicate reads:** an SO row `sales_orders.id` is *decided* iff
   `EXISTS (SELECT 1 FROM projects.sales_orders pso JOIN projects.so_supply_decisions d
   ON d.project_sales_order_id = pso.id AND d.state = 'active' WHERE pso.so_id = sales_orders.id)`.
   Confirmed unplaced Buy at `(product_id, warehouse_id)` = `SUM(oir.qty)` over
   `projects.order_inquiry_rows oir JOIN projects.so_supply_decisions d ON d.id = oir.supply_decision_id
   AND d.state = 'active' JOIN projects.sales_order_lines psl ON psl.id = oir.so_line_id JOIN
   sales_order_lines sol ON sol.id = psl.core_sales_order_line_id` where `oir.verb` is the Buy verb
   (`ORDER`) and `oir.state` is an unplaced state (not placed / received / cancelled - the coder pins
   the exact state constants from `app/models/project_so.py` and records them here). Product and
   warehouse come from the core line (`sol.product_id`, `sol.warehouse_id`). Nothing matches on
   `provisional_ref`, `autocount_doc_no`, or item code.

2. **Confirmed-Buy leg + sheet leg** are the two Project sources in the read model, exactly as
   section 4: confirmed leg = `order_inquiry_rows` with the Buy verb and an unplaced state, whose
   inquiry row carries a `supply_decision_id` pointing at an `active` decision; sheet leg =
   `sales_orders.demand_origin = 'scm_order_inquiry'` open lines only when that SO has NO active
   decision. Existing `committed` stays the sum of the three new columns so current consumers see no
   change in cardinality or keys.
3. **Migrations:** every new revision id is `NNN_snake` and 32 characters or fewer; `down_revision`
   chains from `373_merge_scm_stage0_1a`; one head, proven on an empty scratch DB before push.
4. **No new gated GET under `app/api/v1/user_management`.** The plan-grain policy field rides the
   existing `GET /user-management/settings/` blob and `POST|PUT /settings/general`; the read-gates
   exact set (42) is untouched. If a slice must add a gated GET there, name it in the exact set.
5. **Frontend dev loop:** `npm run dev` only, never `npm run build` (machine memory is the binding
   constraint). Servers are started only for the duration of a verification and stopped after.

## 1. Slices

| Id | Phase | Content | AC ids |
|---|---|---|---|
| S2-FE | 1 | Frontend mock of every Stage 2 surface, against `USE_*_MOCKS` stores; API contract documented at the top of the touched service files | E03, E07, F01, F02, F06, F08, F10 (FE half), F12 (FE half) |
| S2-BE-1 | 2 | UOM `decimal_places`: migration + backfill, model, schemas, service, list/select/detail, canonical ingest, FE swap | F12 (UOM half) |
| S2-BE-2 | 2 | Plan-grain policy in `system_settings`, `reorder_run.decision_grain` + `front_planning_contract_version`, stamp at `create_run`, decision-write guards (legacy NULL contract rejects; other-grain rejects), run/report responses carry the grain, FE swap | F01, F09, F10 |
| S2-BE-3 | 2 | Read model: `scm.committed_v` gains `project_committed`, `retail_committed`, `unclassified_committed` on the same `(product_id, warehouse_id)` row; `so_supply_decisions` + `order_inquiry_rows.supply_decision_id`; recommendation `inputs` snapshot carries the channel breakdown and shared-supply refs; location need = project_need + retail_need with unclassified excluded; retail free supply minus confirmed non-Buy components | E01, E02, E04, E05, F03, F05, F07 |
| S2-BE-4 | 2 | `order_summary_row` new columns + `order_summary_location_allocation`; `write_rows` re-based (`_demand_aggregates` and `demand_drill` on `demand_class`, `retail_outstanding` in API, `suggested_qty` rounded once at MOQ + multiple + frozen `uom_decimal_places`); `record_decision` validates precision + grain + legacy; generalized `reorder_engine.allocate` in integer minor units and persisted split; `po_worklist` reads only the run's grain; FE swap | E03, E05, E06, F03, F08, F09, F11, F12 |
| S2-REV | 3 | Independent reviewer on Opus (Codex substitute, captain-approved) + fixes; test report keyed to E/F | H03, H04 |

Order: S2-FE first (AC-H02), browser-verified and approved before any backend code. Then BE-1 to
BE-4 test-first (tester writes red tests from the UAC ids, coder makes them green), each with the FE
swap of its mock at the service boundary.

## 2. Frontend mock brief (S2-FE)

Every screen below is reached by sidebar clicks from `/`. Mock data lives in the existing
`lib/*MockStore.ts` files behind their `USE_*_MOCKS` flags (add flags where missing); the mock
stores must produce the states: loading, empty run, legacy run (breakdown unavailable, decisions
refused), product-grain run, location-grain run, and a decision error.

1. **Order Summary (Product grain)** `scm/reorder/components/SummaryOrderReportView.tsx`
   - Header chip **Plan grain: Product** or **Plan grain: Location** from the run's stamped
     `decision_grain`; a legacy run (grain NULL) shows **Legacy run** and read-only state. No per-run
     grain selector anywhere on the plan page or in `RunPlanningModal`.
   - One row per product. The SO column stacks three readings: Project (`project_demand`), Retail
     (`retail_outstanding`), Unclassified (`unclassified_demand_qty`). The Suggested column stacks
     Project Buy (`project_buy_qty`), Retail replenishment (`retail_replenishment_qty`) and the
     once-rounded `suggested_qty` total. `project_demand` (open Project-class SO qty) and
     `project_buy_qty` (confirmed unplaced Buy) sit side by side as two measures.
   - Row expansion has three ledgers: Project (SO lines with SO number, line, location, qty, required
     date, and the decision revision / inquiry reference), Retail (per location: stock, avg daily
     demand, incoming SPO/PO, reorder level, allocation), Unclassified (SO lines + the
     "missing demand class" exception). Ledgers reuse the existing drill popover components where a
     shape already exists.
   - A **Locations** drill per row: member locations with channel breakdown, shared supply once,
     the once-rounded suggested qty, the chosen qty and its split back to locations
     (`location_allocations`).
   - Legacy run: channel cells render "Unavailable", ledgers show the unavailable state, decision
     action disabled with the reason.
2. **Decision sheet** `OrderDecisionSheet.tsx`: chosen qty input step and validation follow the row's
   `uom_decimal_places` (0 => integer only; 3 => up to 3 fractional digits); shows the location split
   the mock returns after save; a grain-mismatch / legacy error renders the API message.
3. **Per-location plan** `PlanLinesGrid.tsx` (Location grain view): Project need, Retail need,
   Unclassified columns beside shared stock / SPO / PO / reorder; under a `product` grain run every
   decision control is disabled with a "Decided at Product grain" hint and the row is read/drill;
   under `location` grain the existing controls stay actionable.
4. **PO worklist** `PoWorklistView.tsx`: shows only the run's grain (Product rows with their location
   split under `product`; recommendation decisions under `location`); no channel key.
5. **Settings > General** `user-management/settings/page.tsx`: field **Plan grain** (Product /
   Location, default Product), one line hint "Applies to runs created afterwards".
6. **UOM master data** `master-data-management/units-of-measure`: `decimal_places` (0..4, default 0)
   in `UOMForm.tsx` create/edit, in the list grid and in the detail page.

Contract to document at the top of `services/summaryOrderService.ts`, `services/poWorklistService.ts`,
`services/reorderRunService.ts` (run object), the settings service and `services/uomService.ts`:

```text
ReorderRun            += decision_grain: 'product' | 'location' | null,
                         front_planning_contract_version: number | null
OrderSummaryReport    += decision_grain, is_legacy: boolean
OrderSummaryRow       += project_buy_qty, retail_replenishment_qty, unclassified_demand_qty,
                         earliest_project_need_date, uom_decimal_places,
                         retail_outstanding (alias of stored dealer_outstanding),
                         retail_outstanding_line_count, unclassified_line_count,
                         channel_calculation_basis (JSON, drill evidence),
                         location_allocations: [{warehouse_code, warehouse_name, allocated_qty}]
GET  /order-summary/{code}/demand?kind=project|retail|unclassified&run_id=   (kind 'dealer' accepted as alias of retail)
GET  /order-summary/{code}/locations?run_id=                                  (member locations, channel breakdown, shared supply, split)
POST /order-summary/{code}/decision  {run_id, chosen_qty, supplier_code}     -> 422 precision, 409 grain/legacy
GET  /po-worklist?run_id=  rows carry decision_grain and location_allocations
GET  /reorder-runs/{id}/recommendations rows += project_need, retail_need, unclassified_need,
                                                 decisions_read_only: boolean
system settings blob  += plan_grain: 'product' | 'location'  (POST /settings/general accepts it)
UOM create/update/response/list/select += decimal_places: number (0..4)
```

## 3. Codebase map (where the code lives)

Backend (`sorento_crm_backend/`):

- `ReorderRun` `app/models/scm.py:249`; `create_run` `app/services/scm/reorder_run_service.py:65`
  (stamp point); executor `run_reorder` `:290`, `_execute_run_scoped` `:355`, calls
  `summary_order_service.write_rows` at `:421`; recommendation writes and `allocate` calls at
  `:966`, `:1354`, `_allocation_lines` `:1427`; `_planning_rows` reads `committed_v` at `:516`.
- Planning mode: `app/services/scm/reorder_policy.py:38-77`, routes `app/api/v1/scm/config.py:83-107`.
- `OrderSummaryRow` `app/models/scm.py:583`; `summary_order_service.py`: `_PROJECT_TYPES`/`_DEALER_TYPES`
  `:60`, `write_rows` `:108` (`suggested_qty` derivation `:130-149`), `_demand_aggregates` `:203`,
  `demand_drill` `:415`, `record_decision` `:793`, `po_worklist` `:872`; routes
  `app/api/v1/scm/order_summary.py`; schemas `app/schemas/scm_order_summary.py`.
- `ReorderRecommendation` `app/models/scm.py:283` (`inputs` JSONB is the frozen snapshot),
  `RecommendationOverride` `:339`; `decision_service.py`; routes `app/api/v1/scm/decisions.py`.
- `reorder_engine.allocate` `app/services/scm/reorder_engine.py:391`, `_apportion` `:373`,
  `round_order_qty` `:339`, `load_supplier_candidates` `:678`.
- `committed_v` SQL constant `app/services/scm/demand.py:97` (`COMMITTED_V_SQL`), latest migration
  `alembic/versions/346_scm_demand_origin_split.py`; `net_position_v` `311_scm_purchasing_base.py`;
  chain test `tests/scm/test_committed_v_migration_chain.py`.
- `class_of` `app/services/scm/demand_class.py`; `_classify_demand`
  `app/services/scm/outstanding_import_service.py:623`; `sales_orders.demand_class` `app/models/order.py:385`.
- Projects schema `app/models/project_so.py`: `ProjectSalesOrderLine.core_sales_order_line_id` `:475`,
  `OrderInquiryRow` `:697` (`verb`, `state`, `so_line_id`), `SOLineAllocation` `:755`.
- UOM: model `app/models/product.py:85`, service `app/services/product_service.py:2351` (list dict
  `:2407`), schemas `app/schemas/product.py:77-98,240`, routes
  `app/api/v1/master_data/units_of_measure.py`, ingest `app/services/master_ingest_service.py:167`.
- System settings: model `app/models/user.py:201`; `SystemSettingUpdate` and both manual builders
  `app/api/v1/user_management/settings.py:17-102,150-243,291-370`.
- Supplier MOQ/multiple: `ProductSupplier.moq/order_multiple` `app/models/procurement.py:85`.
- Alembic head `373_merge_scm_stage0_1a`; id-length test `tests/test_alembic_revision_ids.py`.
- Read gates exact set: `tests/test_user_management_read_gates.py:623`.
- Tests to extend: `tests/scm/test_summary_order_service.py`, `test_order_summary_routes.py`,
  `test_m3_engine.py`, `test_demand_class_mapper.py`, `test_committed_v_migration_chain.py`.

Frontend (`sorento_crm_frontend/`):

- Plan: `app/(protected)/scm/reorder/` - `SummaryOrderReportView.tsx`, `OrderDecisionSheet.tsx`,
  `DemandDrillPopover.tsx`, `PoWorklistView.tsx`, `PlanLinesGrid.tsx`, `ReorderPlanningView.tsx`,
  `RunPlanningModal.tsx`; hooks `useSummaryOrder.ts`, `usePoWorklist.ts`, `useReorderRun.ts`;
  services `summaryOrderService.ts`, `poWorklistService.ts`, `reorderRunService.ts`; types
  `types/summaryOrder.types.ts`, `poWorklist.types.ts`, `reorder.types.ts`; mocks
  `lib/summaryOrderMockStore.ts`, `lib/poWorklistMockStore.ts`.
- Planning mode panel: `app/(protected)/scm/policies/components/PlanningModePanel.tsx` (unchanged).
- UOM: `app/(protected)/master-data-management/units-of-measure/` (`UOMForm.tsx`, `forms/uom-schema.ts`,
  `UOMList.tsx`, `[id]/page.tsx`, `services/uomService.ts`, `types/uom.types.ts`, shared
  `UnitOfMeasure` type in `products/types/product.types.ts:139`).
- Settings: `app/(protected)/user-management/settings/page.tsx`, `forms/general-settings-schema.ts`.
- Sidebar: `config/menu.config.tsx` (Supply Chain `:366`, Units of Measure `:606`, Settings `:359`).

## 4. Evidence log

Filled in as slices land (browser runs, test counts, worked cases for AC-F11 and AC-F12).

### 4.1 Phase 1 mock evidence run (agent-browser, 2026-08-17)

Stack: backend `uvicorn` :8022, frontend `next dev` :3022 (this worktree's `.env.local`), private
session `scm-stage2-product-plan`, login with the `E2E_EMAIL` / `E2E_PASSWORD` pair, servers stopped
after the run. Every screen reached by sidebar clicks from `/`; `?plan_mock=` appended only after the
sidebar navigation to switch mock scenarios.

- Sidebar Supply Chain > Reorder Planning: chip **Plan grain: Product**; per-location grid carries
  Project / Retail / Unclass. columns; Decision cell reads "Decided at Product grain" (AC-F01, F02).
- Actions > Order summary: one row per product; SO demand stacked Project 480 / Retail 186 /
  Unclass. 12 with per-channel drill buttons; Suggested stacked Project Buy 180 / Retail 80 / Total
  300; Locations drill shows BRW and JB with channel split, shared Stock / SPO / PO / Level once,
  "Suggested once at the product: 300", "Chosen: 600", split 400 / 200 (AC-E03, E07, F08).
- Worked case `SRTTB1120`: Project 1 + Retail 1 across BRW/JB, multiple 10, Suggested Total 10
  (AC-F11). Decision sheet at dp 0 strips a typed `2.5` and shows "Whole units only (EA)".
- Worked case `SRTAD9002` (kg, dp 3): need 2.5, suggested 2.5; typed 2.75 accepted ("Up to 3
  decimal places (kg)"); Record decision returns "Split back to locations" BRW 1.375 / JB 1.375 /
  Total 2.75 (AC-F12 FE half). Nit for Phase 2: the success toast formats 2.75 as "3" (`fmtInt`).
- `?plan_mock=legacy`: chip **Legacy run**, 24 "Unavailable" channel cells, every decision cell
  "Legacy run - read only. Create a new plan to decide."; stored project/retail values kept (AC-F10).
- `?plan_mock=location`: chip **Plan grain: Location**; per-location Accept buttons active; Order
  summary product rows locked "Decided at Location grain"; PO worklist lists per-location rows with a
  Locations column (AC-F02, F09).
- User Management > Settings > General: **Plan grain** select, options Product / Location, default
  Product, hint "Applies to runs created afterwards." (AC-F01).
- Product Management > Units of Measure: "Decimal Places" list column; Create UOM form has the
  0..4 field defaulting to 0, `7` is refused at submit (AC-F12 UOM half); 375px viewport renders.
- `errors` empty; console only dev noise. Screenshots kept in the session scratchpad.

### 4.2 S2-BE-1 (UOM decimal_places) and S2-BE-2 (plan grain) - Phase 2 green, 2026-08-17

Migrations, chained from `373_merge_scm_stage0_1a`, one head (`alembic heads` ->
`375_plan_grain_run_stamp`):

- `374_uom_decimal_places` - adds `units_of_measure.decimal_places` nullable, runs
  `app.services.uom_decimal_places.backfill_uom_decimal_places`, then NOT NULL DEFAULT 0 +
  CHECK `0..4`.
- `375_plan_grain_run_stamp` - `system_settings.plan_grain` (NOT NULL, default `product`)
  and `scm.reorder_run.decision_grain` / `.front_planning_contract_version`, both nullable
  and deliberately un-backfilled (NULL contract version = legacy = read-only).

**Backfill behaviour on a row with no value.** Classification is by NAME only; a count
name, an unknown name and a measure name with no observed fractional quantity all resolve
to `0`, and `0` is also the column default afterwards, so the rollout fallback survives and
nothing is left NULL. Measured on the prod-copy database: 12 units, all 12 land on 0 -
`Kilogram` and `Liter` are measure names but no `order_lines` / `sales_order_lines` /
`purchase_order_lines` quantity for their products carries a fractional part, so the
observed scale is 0. An admin edit (or a re-run of the backfill) is how such a unit gets
decimals; nothing is inferred.

**Contract note (deviation, agreed with the red tests).** The backfill treats a row as
unclassified when `decimal_places IS NULL` **or** `= 0`, not NULL alone. During the
migration every row is NULL, so the two are identical there; the `= 0` arm is what lets the
function re-value a row still sitting on the rollout fallback, and it is required by
`tests/test_uom_decimal_places.py::test_backfill_measure_uom_takes_greatest_observed_scale
_capped_at_four`, which measures a unit created under the finished (NOT NULL DEFAULT 0)
schema. A value an admin has actually carried (anything above 0) is never overwritten.

**Neighbour suites that had to state their grain.** The guard is contract, not regression:
a run stamped `product` refuses a location decision and vice versa. `test_m4_decisions` and
`test_m8_slice_c` decide at LOCATION grain, so their run helpers now call the shared
`tests/scm/conftest.py::set_plan_grain(db, "location")` before `create_run`;
`test_summary_order_service` and `test_order_summary_routes` build their run rows directly
and now stamp `decision_grain="product", front_planning_contract_version=1`, because
`record_decision` IS the Product-grain decision and an unstamped run is legacy.

Test counts: `tests/test_uom_decimal_places.py` 77 passed;
`tests/scm/test_plan_grain_policy.py` 20 passed (21 minus the migration-marker test its own
docstring said to delete once the column exists); neighbours
`test_summary_order_service` + `test_m4_decisions` + `test_planning_mode` +
`test_alembic_revision_ids` + `test_order_summary_routes` + `test_settings_app_config_gate`
196 passed together with the two above. FE: `tsc --noEmit` clean on the touched files (28
pre-existing errors, all in `.test.ts(x)` files, unchanged); vitest 3 files / 24 tests
passed for `units-of-measure` + `user-management/settings`.

FE mocks swapped off and deleted: `uomDecimalPlacesMockStore.ts`, `planGrainMockStore.ts`.
The SCM plan mocks (`USE_FRONT_PLANNING_MOCKS`, summary / PO worklist) stay ON for BE-3/BE-4.

### 4.3 S2-BE-3 (channel read model) and S2-BE-4 (product grain) - Phase 2 green, 2026-08-17

Migration `376_scm_channel_read_model` chained from `373_merge_scm_stage0_1a`;
`alembic heads` reports exactly one head, `376_scm_channel_read_model`.

**Test counts (Postgres, prod-copy database).** `test_summary_order_service` 52 passed,
`test_order_summary_routes` 17 passed, `test_product_grain_summary` 31 passed,
`test_channel_read_model` 12 passed; the whole neighbour set
(`+ test_plan_grain_policy test_m4_decisions test_m3_engine
test_committed_v_migration_chain test_m0_view_correctness test_demand_reads_the_decision
test_demand_source_split`) 192 passed, 1 xfailed. Tripwires
`test_company_scope test_schema_uuid_id_principle test_alembic_revision_ids` 38 passed.

**Why five worklist tests went red, and what the fix was.** Not the worklist. `_so` in
`test_summary_order_service` now stamps `demand_class` the way the import does, and S13b
(`demand.is_plan_demand_order`, unchanged here) counts project-class demand ONLY where the
Order Inquiry created the order. So a `demand_class='project'` fixture with no
`demand_origin` is set aside from the coverage timeline, the frozen `shortfall` /
`shortfall_at` became 0 / NULL, and every assertion that depended on a DATED shortfall
(need-by, place-by, late, late-first ordering, the frozen dated position) lost its input.
The five tests now pass `from_inquiry=True`, which is what a project order that reaches the
plan actually looks like; the report's own split is unaffected either way because the
aggregates read the class, not the origin. Same fix in the `test_order_summary_routes`
chain fixture, which additionally needed the class stamped so the re-based demand drill
(`demand_class`, not `order_type`) returns the project line again. No implementation was
weakened back to `order_type`.

**Owned-table count bumped 108 -> 110** in `tests/test_company_scope.py`, deliberately, for
`projects.so_supply_decisions` and `scm.order_summary_location_allocation`. Both carry
`CompanyScopedMixin` (owned, not shared): a decision is one company's project pipeline, and
a location split is a planning artefact of the same kind as the `reorder_recommendation` /
`recommendation_override` rows beside it, loaded by the PO worklist.

**FE swap done.** `USE_FRONT_PLANNING_MOCKS`, `USE_SUMMARY_ORDER_MOCKS` and
`USE_PO_WORKLIST_MOCKS` are all false, so every Stage-2 surface reads the real routes and
`withRunGrain` / `withChannelNeeds` are pass-throughs. **The three mock stores are KEPT, not
deleted** (a deliberate departure from their own "Phase 2 deletes this file" header): their
fixtures are what five vitest specs assert against - `SummaryOrderReportView`,
`DemandDrillPopover`, `OrderDecisionSheet`, `orderImpact` and `summaryOrderService`'s own
mock-branch spec - which is the "unless they are reused by tests" case in CLAUDE.md. The
`?plan_mock=` scenario switch no longer reaches a screen.

The AC-F12 toast nit from 4.1 is fixed: `useRecordOrderDecision` renders the quantity with
`fmtQty` at the row's frozen `uom_decimal_places`, passed as a mutation variable
(`decimalPlaces`) because the decision response carries no precision of its own. An accepted
`2.75 kg` previously toasted as "3".

FE checks: `tsc --noEmit` 28 errors, all in pre-existing `.test.ts(x)` files (unchanged
baseline, none in `scm/reorder`); `vitest run "app/(protected)/scm/reorder"` 70 files /
1030 tests passed; `eslint app/(protected)/scm/reorder` 3 errors, all in files this branch
does not touch.

**Two neighbour regressions, since RESOLVED (see "The firm leg is the confirmed leg" below).** Measured by
running the whole `tests/scm` directory on this tree and on `HEAD` in a throwaway worktree:
base 94 failed / 1540 passed, branch 57 failed / 1578 passed, and exactly two failures are
new -

* `test_pool_netting_parity.py::test_a_shared_pool_covers_its_bins_so_nothing_is_bought`
* `test_demand_breakdown.py::test_a_pooled_covered_row_lists_the_pool_its_own_figure_came_from`

Both are one cause. `_compute_cell` takes `project_need = row["project_committed"]` and adds
it to the order AFTER netting, bypassing the trigger (AC-E05). But `committed_v`'s
`project_committed` is the SUM of both project legs, so the SHEET leg - a
`demand_origin = 'scm_order_inquiry'` order with no active decision - is now treated as firm
Buy as well. The result is a purchase for a SKU whose shared pool already covers the demand
(`project buy: 67 confirmed unplaced Buy in this pool`, 4,397 in the pool), and a `covered`
row that now reads `buy`. AC-E04 defines Project need as **confirmed** unplaced Buy read
through `projects.order_inquiry_rows`, and AC-E05's bypass is worded for "confirmed unplaced
Project Buy" - the sheet leg is a project-class demand READING, which ordinary netting is
supposed to see. Resolving it means separating the legs in the read model (a fifth
`committed_v` column, or `project_confirmed` + `project_sheet` in place of one column) and
feeding only the confirmed leg past the trigger, which changes what `test_channel_read_model`
pins and is a contract call rather than a fixture fix. Everything else in the 57 fails
identically at `HEAD` (six `test_policy_config` and one `test_po_history_import` failure are
prod-copy data - a `reorder_policies.policy_type = 'reorder_level'` row outside the response
literal; the `test_m8_slice_e` and remaining parity failures likewise pre-date the branch).

## The firm leg is the confirmed leg (BE-5)

The plan decision the two regressions above were waiting on, taken as the planner ruled it:
**only the confirmed leg is firm.** Plan 5.3 defines `project_need` as "confirmed unplaced Buy",
AC-E04 and AC-E05 both say "confirmed", and S13b says the book supplies the rest. So:

* `scm.committed_v` gains a FIFTH column, `project_confirmed_committed`, appended last (a
  `CREATE OR REPLACE` may only add columns at the end, which is how the shared local database
  took it without a drop). It is the confirmed leg alone, a SUBSET of `project_committed` and
  never a fourth addend of `committed`, so `net_position_v` and every existing consumer are
  untouched. `project_committed` still sums both legs, because plan 6.4 makes the Project
  COLUMN the display of both.
* `_compute_cell` reads its firm figure off the new column. The sheet remainder
  (`project_committed` less the confirmed leg) stays inside the netted basis alongside Retail,
  which is exactly where pre-Stage-2 `committed` had it, so a shared pool that covers it buys
  nothing again. Unclassified demand is still excluded from actionable need (AC-F05, AC-E06).
* The remainder is stated rather than folded away: `project_sheet_need` on the frozen
  recommendation `inputs`, in the recommendations response, in the per-location basis, in
  `OrderSummaryLocationRowOut`, and on both FE types. It is NOT summed into a product-row
  quantity: the row carries exactly the three the plan pins, and the sheet leg is answered
  inside `retail_replenishment_qty` (with `channel_calculation_basis.project_sheet_netted`
  naming the total). `project_buy_qty` is therefore now confirmed Buy only, which is what it
  was defined as and what `earliest_project_need_date` already read.
* Migration 376 is amended in place, not superseded: it has never left this branch, and the
  `test_committed_v_migration_chain` drift guard compares its frozen body to the live SQL.
  `alembic heads` stays the single `376_scm_channel_read_model`.

Counts after: `tests/scm` 55 failed / 1582 passed (from 57 / 1578 - the two regressions gone,
two new tests green). `test_channel_read_model` 14 passed, `test_product_grain_summary` 31,
`test_summary_order_service` 52, `test_order_summary_routes` 17, `test_demand_breakdown` 14,
`test_committed_v_migration_chain` 4, `test_plan_grain_policy` 20, `test_m4_decisions` 16,
`test_demand_reads_the_decision` 7, `test_demand_source_split` 8, `test_m0_view_correctness` 2,
`test_alembic_revision_ids` 3. `vitest run "app/(protected)/scm/reorder"` 71 files / 1033
tests passed; `tsc --noEmit` still 28 errors, all in pre-existing `.test.ts(x)` files.

Two `test_pool_netting_parity` failures remain and are LOCAL DATA, not this branch:
`test_singleton_pool_planning_is_byte_identical_to_the_snapshot` and
`test_a_partly_covering_pool_sizes_ONE_buy_on_the_pool_shortfall` both fail at `HEAD` too,
because the prod-copy database holds a `scm.reorder_policy` row with
`policy_type = 'reorder_level'` and no levels, so the planner emits `needs_level` where the
golden file expects a forecast buy. Re-run with `policy_type` forced to `reorder_point` (the
shape CI's empty database has) and both pin exactly: PARTIAL buys 340.0 across POOL 71 /
POOL-A 161 / POOL-B 108, POOLED buys nothing and reads `covered`.

## The freeze reads the SIZING GROUP, not the row (BE-6)

A real-stack evidence run over the whole catalogue (network scope, product grain) exposed
three defects the unit tests could not see, because every one of those tests hand-builds a
recommendation `inputs` dict in the PER-WAREHOUSE shape and the network and pool paths
freeze a different one.

**Defect 1 - the basis had no warehouse identity (AC-F08).** `_plan_network` emits ONE buy
per product with `warehouse_id = NULL` and a `_network_agg_cell` snapshot whose shared facts
are all `None`. `summary_order_service._channel_freeze` assumed one buy row per LOCATION and
built `basis.locations` off those rows via `wh_meta.get(str(r.warehouse_id))`, so every
network-mode basis had exactly one entry with `warehouse_code`, `warehouse_name`, `on_hand`,
`incoming_spo`, `on_order_po` and `reorder_level` all null. All 755 rows of the seeded run
were like that, and `/order-summary/{code}/locations` rendered location rows with no
identity.

**Defect 1b - the product row contradicted its own run.** `retail_need` on the aggregate
cell is the SUM of the member cells' `retail_need`, and a member measured alone can be 0 -
untriggered under its own reorder level - while the aggregate is short. Product `MWB242`
carried a buy of 213 (split BRW 0 / BRW-BB 51 / BRW-IB 162) and its summary row read
`project_buy_qty 0 / retail_replenishment_qty 0 / suggested_qty 0`, because the freeze
re-derived a raw need of 0 instead of stating the figure the run had sized. The pool path
had the same shape plus a second hole: a pool member the allocator gave nothing to emits no
row at all, so its channel needs never reached the product's readings.

**Defect 2 - channel disjointness was unproven.** No test put all four classes on one
(product, warehouse) and followed them through the real engine, so nothing would have caught
one open quantity being counted in two channels.

**The fix, one canonical shape everywhere.** Every buy the engine emits now carries
`inputs["plan_basis"]` (`reorder_run_service._plan_basis`) - the basis of the SIZING GROUP
it belongs to rather than of the row it happens to be:

```text
plan_basis = {
  group,                       # dedupe key: warehouse_id | pool_id | "network"
  scope,                       # location | pool | network
  project_need,                # the group's firm confirmed Buy
  retail_need,                 # the group's OWN netted replenishment (the aggregate's)
  project_sheet_need,          # netted inside retail_need, stated not summed
  unclassified_need,           # visible, never sized
  recommended, rounded,        # what the engine sized, before and after supplier terms
  locations: [ { warehouse_id, warehouse_code, warehouse_name,
                 project_need, retail_need, project_sheet_need, unclassified_need,
                 on_hand, incoming_spo, on_order_po, reorder_level, avg_daily_demand,
                 location_suggested_qty } ]   # EVERY member, including zero-allocated
}
```

`_channel_freeze` collapses a product's buy rows to their groups (`_sizing_groups`) and sums
the group figures once - a pool emits one row per allocated location, all carrying the same
basis, and counting it per row would multiply it. Project, sheet and unclassified stay
additive across locations; **netted Retail is the group's own figure**, because a pool or a
network buy is netted ONCE on the aggregate. A run frozen before `plan_basis` existed has no
group and falls back to the row-wise sum, which is exactly right for the per-warehouse shape
it was written in.

Two consequences worth stating rather than discovering:

* A location's channel needs are a **demand statement**, not an allocation statement. Under
  aggregate sizing they do NOT sum to the product's suggestion - a bin can be short 30 while
  the network holds a surplus. What reconciles to the order is `location_suggested_qty`, the
  engine's own split. Under per-warehouse scope (the default, singleton pools) each group is
  one location and the channel sums reconcile exactly as before.
* `warehouse_id` lives in the recommendation snapshot, where the allocator replay reads it;
  `_channel_freeze` strips it from the product row's stored basis, which is addressed by code.

`_persist_location_split` gained the matching fallback: a NETWORK buy names no warehouse, so
there was no per-location row to replay the allocator over and a product-grain decision on a
network run could not be split at all. It now reads the frozen basis's member locations and
their engine shares as the deficit signal (AC-F08, AC-F12).

### Evidence

Re-seeded run `76efe9f7-879a-4d33-b1ff-663d506bda13` (network scope, `decision_grain
product`, contract 1, company `...0001`), 8,327 recommendations, 507 summary rows. The stale
`57022069-...` run was deleted first.

* 2,043 frozen basis location entries, **0** with a null `warehouse_code`, **0** with a null
  `on_hand`.
* 507 of 507 rows: `suggested_qty = ceil(engine rounded_qty)` - the only difference from the
  engine's raw figure is the quantize to the row's frozen `uom_decimal_places` (0 here), which
  is what AC-F11 asks for. `basis.raw_need` equals the engine's figure on 506; the one
  exception is `MWB248`, where the engine had already applied MOQ 100 to a raw need of 33 and
  both answers are 100.
* `MWB242`, the row that read 0: now `retail_replenishment_qty 213`, `suggested_qty 213`,
  matching the engine's buy exactly.

```json
{
  "raw_need": 213.0,
  "locations": [
    {"warehouse_code": "BRW",    "warehouse_name": "BRW",    "on_hand": 0.0, "incoming_spo": 0.0, "on_order_po": 0.0, "reorder_level": null, "project_need": 0.0, "retail_need": 0.0, "project_sheet_need": 0.0,   "unclassified_need": 0.0,    "avg_daily_demand": 0.0, "location_suggested_qty": 0.0},
    {"warehouse_code": "BRW-BB", "warehouse_name": "BRW-BB", "on_hand": 0.0, "incoming_spo": 0.0, "on_order_po": 0.0, "reorder_level": null, "project_need": 0.0, "retail_need": 0.0, "project_sheet_need": 51.0,  "unclassified_need": 1238.0, "avg_daily_demand": 0.0, "location_suggested_qty": 51.0},
    {"warehouse_code": "BRW-IB", "warehouse_name": "BRW-IB", "on_hand": 0.0, "incoming_spo": 0.0, "on_order_po": 0.0, "reorder_level": null, "project_need": 0.0, "retail_need": 0.0, "project_sheet_need": 162.0, "unclassified_need": 0.0,    "avg_daily_demand": 0.0, "location_suggested_qty": 162.0}
  ],
  "rounded_qty": 213.0,
  "supplier_moq": null,
  "supplier_order_multiple": null,
  "uom_decimal_places": 0,
  "project_sheet_netted": 213.0,
  "unclassified_excluded": 1238.0
}
```

`svc.locations(db, "SRTWC286-SH-NEW-P", run_id=...)` on the same run returns two NAMED
locations with disjoint channels (BRW: unclassified 44; BRW-BB: sheet 37, unclassified 38),
`suggested_qty 37`. `record_decision(..., chosen_qty=37)` on that network run splits back to
BRW 0 / BRW-BB 37 - previously it could not split at all. That decision is left in place on
the run (`record_decision` commits), so `SRTWC286-SH-NEW-P` is the one decided row of 507 and
carries two `scm.order_summary_location_allocation` children; every other row is an
undecided freeze.

**No confirmed Project Buy exists anywhere in the local data**, because Stage 1C has not
landed and `projects.so_supply_decisions` is empty, so every `project_buy_qty` in the
evidence run is 0 and the whole project-class book reads through the sheet leg. That is the
honest state, not a defect.

### Tests

Four real-engine regressions in `tests/scm/test_channel_read_model.py`, all driving
`create_run` -> `run_reorder` -> `write_rows` rather than a hand-built `inputs` dict:

* `test_per_warehouse_run_keeps_every_demand_class_in_exactly_one_channel` and
  `test_network_run_keeps_every_demand_class_in_exactly_one_channel` - one SO per class at
  one location (retail 30, sheet 9, unclassified 7, confirmed Buy 12) under BOTH buy scopes.
  Each quantity in exactly one field, `retail_net` short exactly Retail + sheet, the order
  51 = firm 12 + netted 39 with the unclassified 7 excluded, and the frozen basis naming its
  location with non-null shared facts.
* `test_a_network_sized_buy_states_its_own_replenishment_not_the_sum_of_its_cells` - the
  1b regression in miniature: A holds 50 spare, B is short 30, confirmed Buy 5 at B. The
  network buys 5; summing the member cells says 35.
* `test_a_pool_member_the_split_gave_nothing_to_still_reaches_the_product_row` - the pool
  hole: B is allocated nothing and emits no row, and its 20 of unclassified demand must
  still reach the product row.

Hand-built fixtures moved to the canonical shape via
`tests/scm/conftest.py::single_location_plan_basis` (`test_product_grain_summary.py::_rec`
attaches it by default; `test_order_summary_routes.py::channel_chain` builds it inline), with
`test_a_run_frozen_before_plan_basis_existed_still_sums_its_rows` keeping the row-wise
fallback pinned. `test_summary_order_service.py` needed no change: its recommendations carry
no channel figures at all and exercise the pre-channel derivation.

Counts (Postgres, prod-copy database): `test_product_grain_summary` 36,
`test_channel_read_model` 21, `test_order_summary_routes` 22, `test_summary_order_service`
52, `test_plan_grain_policy` 20, `test_demand_breakdown` 14,
`test_committed_v_migration_chain` 4, `test_pool_netting_parity::
test_a_shared_pool_covers_its_bins_so_nothing_is_bought` 1 - **170 passed** together.
Neighbours `test_m3_engine test_m4_decisions test_demand_reads_the_decision
test_demand_source_split test_m0_view_correctness test_reorder_level_run` green; the two
`test_m3_run` failures and the two remaining `test_pool_netting_parity` failures are the
prod-copy-data ones already recorded above and fail identically at `HEAD`. `pyright` on the
two touched service files: 88 errors before and after, none new.

### 4.4 Real-stack evidence run after the sizing-group fix (agent-browser, 2026-08-18)

Stack: backend `uvicorn` :8022, frontend `next dev` :3022 (this worktree's `.env.local`),
private session `scm-stage2-product-plan`, login with the `E2E_EMAIL` / `E2E_PASSWORD` pair,
session closed and both servers stopped after the run. Data: the re-seeded network-scope run
`76efe9f7-879a-4d33-b1ff-663d506bda13` (decision_grain `product`, contract 1; 2,043 basis
location entries, 0 with a null identity; 507/507 rows `suggested_qty` = the engine's own
rounded figure at frozen dp - measured in BE-6). Navigation by sidebar clicks from `/`:
Supply Chain > Reorder Planning, then Actions > Order summary.

- Chip **Plan grain: Product** on the stamped run; Order summary renders one row per
  product with stacked Project / Retail / Unclass. readings and per-channel drill buttons
  (AC-E03 live; AC15S row reads Project 2 / Retail 0 / Unclass. 2 off live
  `demand_class` aggregates).
- `SRTWC286-SH-NEW-P` (the row the defect froze anonymously): Member locations drill now
  shows **named** BRW and BRW-BB rows with per-channel columns, shared Stock / SPO / PO /
  Level shown once, "Suggested once at the product: 37", "Chosen: 37", split BRW 0 /
  BRW-BB 37 - the decision recorded in BE-6's service-level proof survives to the UI
  (AC-F08, AC-F12 durable split). Screenshot `40-real-locations-drill-fixed.png`.
- Run history > a pre-contract run flips the chip to **Legacy run** with "You are viewing a
  past run from ..." and every decision cell reading "Legacy run - read only. Create a new
  plan to decide." (AC-F10 live). Screenshot `41-real-legacy-readonly.png`.
- `errors` empty; console shows no errors beyond dev noise.

Two freeze defects the first real-stack run surfaced (anonymous basis locations; a product
row contradicting its own run's sizing) are the subject of BE-6 above and are what this run
re-verifies as fixed.

## Independent-review fixes (BE-7)

Six findings from the independent review of BE-1..BE-6, fixed in one pass. Two carried a
decision worth stating rather than leaving in a diff.

**1. Decision-grain guard bypasses (AC-F09, AC-F10).** `decide_covered`,
`confirm_decisions` and `reset_run_decisions` were live routes with no guard at all, beside
`accept` / `adjust` / `reject`, which have had one since BE-2. A covered-by-stock answer IS
a location decision (it turns a location's stock into cover or into a purchase) and confirm
is what materialises staged location decisions into draft POs, so both now take
`_assert_location_grain`. Reset is not a decision - putting a product-grain run's read-only
recommendations back to as-generated undoes nothing anybody decided - so it is refused only
for being LEGACY, through the new `plan_grain.assert_not_legacy` (the first half of
`assert_decision_grain`, shared so the wording and the 409 cannot drift). Seven route-level
tests in `test_plan_grain_policy.py` section G; five of them fail at the pre-fix code.
`tests/scm/test_covered_decision.py` now creates its run under the `location` policy, the
same idiom `test_m4_decisions.py` uses - its decisions were always location-grain.

**2. Migration 374 imported live code.** It called
`app.services.uom_decimal_places.backfill_uom_decimal_places`, which is exactly the shape of
the 340/346 replay outage this repo already records. The name lists, the observed-scale SQL
and the "NULL or 0" predicate are now frozen inside the migration as `_backfill_374`, with a
comment naming the service as the live twin; the service is unchanged and still runs for
admin re-runs. Verified byte-identical against the prod copy: 12 units, all resolving to 0,
both implementations writing the same 12 rows, and a carried value of 3 left alone by both
(11 rows rewritten). `test_committed_v_migration_chain::
test_migration_bodies_are_frozen_not_imported` now covers 374. Revision id and chain
position untouched; `alembic heads` stays `377_merge_stage2_main`.

**3. Non-buy sizing groups were invisible (AC-E06, AC-F08).** `write_rows` read
`rec_type = 'buy'` only, so a product buying at location A lost location B entirely when B
came back `covered` / `exception` / `needs_level` - B's unclassified and sheet readings, and
B itself from the basis. Every one of those rows now carries its sizing group's
`plan_basis` (the same `_plan_basis` the buy path already built; the pool and network paths
emit their `needs_level` rows after sizing instead of before, which leaves the row order
unchanged), and the freeze reads all four kinds.

*Decision A - what a non-buy group contributes.* Project, the sheet leg and unclassified
demand are statements about the order book, so they are additive across every group. Netted
Retail replenishment is a SIZED figure and comes only from groups that bought: a covered
group's is 0 by definition, and a group that could not be sourced sized no purchase either.

*Decision B - whose row exists at all.* Reading all four kinds does NOT mean every product
that produced one gets a Product-grain row. On the live catalogue that is 2,691 rows against
507 on the network run (2,599 against 186 per-warehouse), on an unpaginated report, almost
all of them with a suggestion of 0 - the information fatigue AC-C2.2a exists to prevent. So
`_belongs_on_the_book`: a product gets a row when the run sized a purchase for it, OR when
it owes firm confirmed Project Buy the run could not size (AC-E04: a confirmed unplaced Buy
at a supplierless location emits `exception` and no buy anywhere, and dropping it hides a
commitment CS has already made). A covered-only or needs-level-only product stays the
Location grain's work, where each row states its own reason. Both halves are pinned by
tests. Measured consequence: re-freezing the two newest real runs is byte-identical, row for
row and field for field (507 and 186 rows).

**4. The float-sum claim.** `reorder_engine.allocate` returns `parts[i] / scale`, so at a
non-zero precision a Python float sum of the children can land an ulp from `chosen_qty`
while the persisted `Numeric` sum is exact. The allocate docstring, the
`OrderSummaryLocationAllocation` model docstring and the `OrderSummaryLocationAllocationOut`
comment now claim exactness in the stored decimals, and say to reconcile against those
rather than against the returned floats. No behaviour change.

**5. Em-dashes** removed from the lines this branch added (banned by `PRINCIPLES.md`).

**6. The report shipped the whole basis on every row.** `_serialise_row` carried
`channel_calculation_basis` - 2,043 location entries across 507 rows in the evidence run -
on an unpaginated report, for a drill served separately by
`GET /order-summary/{code}/locations` and read by no FE component. Dropped from the
serialiser AND from `OrderSummaryRowOut`, so the contract states it; the stored column and
the drill endpoint are untouched. Pinned by
`test_the_report_does_not_ship_the_per_location_basis_on_every_row`.

Counts (Postgres, prod-copy database): the review's green gate -
`test_product_grain_summary` `test_channel_read_model` `test_order_summary_routes`
`test_summary_order_service` `test_plan_grain_policy` `test_demand_breakdown`
`test_committed_v_migration_chain` `test_m4_decisions` `tests/test_uom_decimal_places`
`tests/test_alembic_revision_ids` - **276 passed**, up from 265 before (11 new tests).
Neighbours `test_covered_decision test_cover_from_stock test_covered_demand_surfaces
test_m4_cash test_m8_slice_a test_m8_slice_c test_m3_engine test_reorder_level_run
test_front_planning_golden` green. Still failing and still failing IDENTICALLY at `HEAD`,
with the same messages: the two `test_m3_run`, the two `test_pool_netting_parity` and the
eleven `test_m5_explainer` / `test_m8_slice_e` prod-copy-data ones. `pyright` per touched
file: identical error counts before and after (40 / 48 / 32 / 2 / 1 / 0 / 0 / 0), `pyflakes`
only its pre-existing findings.
