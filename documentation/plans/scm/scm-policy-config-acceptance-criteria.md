# SCM Policy Configuration - Acceptance Criteria (UAC)

Status: DRAFT (written FIRST, pre-plan, pre-code)
Classification: **MODULE** - part of the installable `scm` module (App-Store `scm` catalog entry
+ `tenant_modules` + `require_module_enabled_with_api_key("scm")`). Tables already live in the
`scm.*` Postgres schema (M0). This feature adds NO new tables and NO new migration for schema; it
only adds routes/schemas/services + FE + one menu leaf. RBAC slug `scm.policy.manage` already
exists (migration `274_scm_m0_views_reg.py`), so no RBAC migration either.
Related: `PLAN-scm-m3-reorder-engine.md`, `PLAN-scm-reorder-copilot.md`.

## Purpose

Let an operator tune the reorder engine's policies from the app instead of hand-editing
`scm.*` tables in the DB. Three policy families, one "Policies" area under Supply Chain:
1. **Reorder policies** - scoped CRUD (`scm.reorder_policy`), resolved most-specific-active-wins.
2. **Classification thresholds** - the single global `scm.abc_xyz_policy` row.
3. **Supplier scoring** - the single global `scm.supplier_scoring_policy` row.

Plus a **resolution preview** ("resolve for SKU X") that calls the SAME resolver the run uses.

## Binding facts the ACs depend on (verified in code)

- Resolver: `resolve_policy` / `resolve_policy_for_sku` in
  `sorento_crm_backend/app/services/scm/reorder_engine.py:75,561`. Precedence:
  `sku > abc_xyz_cell > product_class > global`; ties break on `priority` (higher wins) then
  `scope_ref`. Only `is_active` rows considered.
- `scope_ref` semantics per `_policy_matches` (`reorder_engine.py:98`):
 - `sku` → **`products.id` (UUID)**; matched by `str(scope_ref) == str(product_id)`.
 - `product_class` → **`product_categories.category_code`** (string; see `load_category_code`
    `reorder_engine.py:475`).
 - `abc_xyz_cell` → **`"{abc}-{xyz}"`** e.g. `A-X` (see `resolve_policy_for_sku:568`).
 - `global` → `scope_ref` NULL.
- `factor_toggles` JSONB carries `supplier_selection` (`primary|best_score|lowest_cost`) and
  `lead_time_default_days` (int) - see `ensure_reorder_policy_defaults` / `engine_toggles`
  (`reorder_engine.py:405-452`). These are surfaced as first-class form fields.
- Consumption timing (verified):
 - `scm.reorder_policy` is read by the **reorder run** → edits take effect on the **next reorder run**.
 - `scm.abc_xyz_policy` + `scm.supplier_scoring_policy` are read by the **M2 analytics job**
    (`analytics_service.py:72-136`), which recomputes `item_classification` / `supplier_performance`
    → edits take effect on the **next analytics run**, which the following reorder run then consumes.
    (This distinction MUST be reflected in the UI copy - see AC-CFG-1 / AC-SUP-1.)

---

## AC group A - Navigation & access (RBAC + module guard)

- **AC-NAV-1** GIVEN the `scm` module is enabled for the tenant AND my role has `scm.policy.manage`,
  WHEN I open the "Supply Chain" sidebar group, THEN a "Policies" leaf is visible and routes to
  `/scm/policies`.
- **AC-NAV-2** GIVEN my role LACKS `scm.policy.manage`, WHEN I view the Supply Chain group, THEN the
  "Policies" leaf is NOT rendered, AND a direct GET to `/scm/policies` API returns 403.
- **AC-NAV-3** GIVEN the `scm` module is DISABLED for the tenant, WHEN any policy API is called,
  THEN the module guard returns the standard module-disabled response (per
  `require_module_enabled_with_api_key("scm")`).
- **AC-NAV-4** No UUID is ever displayed in the Policies UI (SKU shows `product_code`, class shows
  `category_code`, cell shows `A-X`). (Cursor rule: no UUIDs in FE UI.)

## AC group B - Reorder policies list

- **AC-LIST-1** GIVEN reorder policies exist at mixed scopes, WHEN I open `/scm/policies`, THEN a
  DataGrid lists them with columns: Scope (global/SKU/Class/ABC-XYZ cell), Scope target
  (human-readable: `-` for global, `product_code · name` for SKU, `category_code` for class,
  `A-X` for cell), Policy type, key values (service level, SS method, safety days, lead-time default,
  supplier selection), Active, Priority.
- **AC-LIST-2** The grid uses `tableLayout: { width: 'fixed', columnsResizable: true }`,
  `columnResizeMode: 'onChange'`, explicit column `size`, and long text uses `truncate` + `title`.
- **AC-LIST-3** The grid supports server-side paging/sort/search built via `buildDataGridParams`
  (no hand-built `URLSearchParams`).
- **AC-LIST-4** GIVEN no non-global overrides exist, THEN the grid still shows the global default row
  and renders an explicit empty-hint ("Only the global default policy is configured. Add an override
  to tune specific SKUs, classes, or ABC-XYZ cells.").
- **AC-LIST-5** Every row states, near the grid, that "Policy edits take effect on the next reorder
  run" (they do not auto-run).

## AC group C - Create / edit reorder override (modal)

- **AC-EDIT-1** WHEN I click "Add policy", THEN a modal opens with: Scope type
  (`global` disabled/absent - global default is edited, not created), Scope target picker that
  switches by scope type:
 - `sku` → product `SearchableSelect` (label `product_code · name`, hidden value = `products.id`);
 - `product_class` → product-class `SearchableSelect` (value = `category_code`);
 - `abc_xyz_cell` → two pickers ABC ∈ {A,B,C} × XYZ ∈ {X,Y,Z}, composed to `A-X`.
- **AC-EDIT-2** The modal exposes policy fields: policy_type (`reorder_point|periodic_review|min_max`),
  service_level, safety_stock_method (`fixed_days|statistical|manual`), safety_days,
  review_period_days, forecast_window_days, baseline_source, spike_handling, buy_scope,
  dead_stock_days, overstock_days, min_override, max_override, priority, is_active, AND the two
  `factor_toggles` fields surfaced first-class: supplier_selection (`primary|best_score|lowest_cost`)
  and lead_time_default_days.
- **AC-EDIT-3** All dropdown-selects in the modal are searchable (`SearchableSelect`) - no raw
  `<select>` / `@/components/ui/select`.
- **AC-EDIT-4** WHEN I edit the **global default** row, THEN the modal opens with scope locked to
  `global`, scope target hidden, and the delete action is absent (AC-DEL-2).
- **AC-EDIT-5** On successful create/update the modal closes, the grid invalidates + refetches, and a
  success toast shows. On error, the extracted message (`extractApiError`) shows in a toast and the
  modal stays open.
- **AC-EDIT-6** Modal is scrollable at ~375px width with the submit button reachable (mobile modal
  scroll rule).

## AC group D - Validation (BE-authoritative, mirrored FE)

- **AC-VAL-1** scope_ref REQUIRED for non-global scopes; a non-global create/update with empty
  scope_ref → 422 with a field message.
- **AC-VAL-2** scope_ref MUST NOT be sent for `global`; global rows keep scope_ref NULL.
- **AC-VAL-3** service_level, when provided, MUST be strictly between 0 and 1 (exclusive) → else 422.
- **AC-VAL-4** All day fields (safety_days, review_period_days, forecast_window_days, dead_stock_days,
  overstock_days, lead_time_default_days) MUST be > 0 when provided → else 422.
- **AC-VAL-5** min_override/max_override, when both provided, MUST satisfy min ≤ max → else 422.
- **AC-VAL-6** supplier_selection ∈ {primary,best_score,lowest_cost}; safety_stock_method ∈
  {fixed_days,statistical,manual}; policy_type ∈ {reorder_point,periodic_review,min_max};
  scope_type ∈ {sku,product_class,abc_xyz_cell,global} - invalid enum → 422.
- **AC-VAL-7** (coherence) `safety_stock_method='statistical'` with no `service_level` → 422 with a
  message ("Statistical safety stock requires a service level"). (The engine silently falls back to
  fixed_days at run time; the config UI must not let the user save a policy that will silently not do
  what they asked.)
- **AC-VAL-8** (uniqueness) A create whose (scope_type, scope_ref) already exists on an ACTIVE policy
  → 409/422 with "A policy already exists for this scope"; editing that same row is allowed.
  (Prevents two SKU overrides silently tie-breaking on priority.)
- **AC-VAL-9** (referential) scope_ref for `sku` must resolve to an existing product; for
  `product_class` must be a known `category_code`; else 422. Cell must be a valid `A|B|C`-`X|Y|Z`.

## AC group E - Delete reorder override

- **AC-DEL-1** WHEN I delete a non-global override, THEN an `AlertDialog` confirm appears ("Confirm
  delete" / "This action cannot be undone", destructive button styling); on confirm the row is
  **hard-deleted** (DELETE removes the DB row, not a soft flag), grid refetches, success toast.
- **AC-DEL-2** GIVEN a `global` scope row, THEN it has NO delete affordance, AND a DELETE API call
  targeting a global row → 422 ("The global default policy cannot be deleted").
- **AC-DEL-3** Deletion never uses the browser `confirm()`.

## AC group F - Classification thresholds (global single form)

- **AC-CFG-1** WHEN I open the "Classification thresholds" inline settings panel, THEN it shows the
  single active `abc_xyz_policy` (abc_a_pct, abc_b_pct, xyz_x_max, xyz_y_max) with an explicit empty
  state if none exists yet (seeded defaults offered), AND copy stating "Changes take effect on the
  next analytics run, which reclassifies items; the following reorder run then uses the new classes."
- **AC-CFG-2** Save upserts the single active row (`scm.policy.manage`). abc_a_pct/abc_b_pct ∈ (0,1),
  abc_a_pct + abc_b_pct < 1 (A + B share below 100%, remainder = C); xyz_x_max ≤ xyz_y_max, both > 0
  → else 422.
- **AC-CFG-3** Read gate = `scm.policy.manage` (write and read are the same manage surface - this is
  an admin/config screen, justified in the plan).

## AC group G - Supplier scoring (global single form)

- **AC-SUP-1** WHEN I open the "Supplier scoring" inline settings panel, THEN it shows the single
  active `supplier_scoring_policy` (delivery_weight, quality_weight, grace_days, min_sample_size)
  with an empty state if none, AND copy stating "Changes take effect on the next analytics run, which
  recomputes supplier scores."
- **AC-SUP-2** Save upserts the single active row. delivery_weight + quality_weight MUST be provided
  and each in [0,1]; their sum SHOULD equal 1.0 (± 0.001) - else 422 with a message. grace_days ≥ 0,
  min_sample_size ≥ 1 → else 422.

## AC group H - Resolution preview (the tester)

- **AC-PREV-1** WHEN I pick a product (SearchableSelect, optional warehouse) and run the preview,
  THEN the UI calls `GET /scm/policies/resolve?product_id=&warehouse_id=` and shows the **winning
  policy** (its scope, target, and effective values) PLUS the **resolution chain**: which scopes were
  evaluated (sku / abc_xyz_cell / product_class / global), which matched, which won, and WHY
  (most-specific-active, priority tiebreak).
- **AC-PREV-2** The preview result MUST equal what an actual reorder run would resolve - it is
  produced by calling the SAME `resolve_policy_for_sku` the engine uses, NOT a reimplementation.
  (Test AC pins this: a golden fixture asserts the endpoint output == `resolve_policy_for_sku(...)`.)
- **AC-PREV-3** GIVEN a SKU with no classification cell and no class override, THEN the chain shows
  those scopes as "no match" and the global default as the winner, with an explanatory note (never an
  error).
- **AC-PREV-4** The product picker takes a `product_code`/name (no UUID shown); the endpoint accepts
  the product id resolved from that pick.
- **AC-PREV-5** (nice-to-have, may be DEFERRED with a keyed note) The preview shows an
  affected-SKU estimate: "N SKUs currently resolve to this policy" for the winning override.

## AC group I - Layering & standards (hard-fail gates)

- **AC-STD-1** FE layering respected: UI → hooks (`usePolicies*`) → feature service
  (`policyService.ts`) → `lib/api-client` → backend. No fetch calls in components.
- **AC-STD-2** Uses shared `extractApiError`, `buildDataGridParams`, `SearchableSelect`,
  `ConfirmDeleteDialog`/`AlertDialog`, shared mutation-hook patterns. No hand-rolled equivalents.
- **AC-STD-3** All writes gated by `scm.policy.manage`; module guard on the router.
- **AC-STD-4** Every detail section renders even when empty (empty states per CRUD UX standard).

## Test report keying

Phase-2 test report (`documentation/plans/scm/scm-policy-config-test-report.md`) keys every AC id to
PASS / FAIL / DEFERRED with the vitest / playwright / pytest that proves it.
