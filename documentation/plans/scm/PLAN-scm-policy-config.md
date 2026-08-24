# PLAN - SCM Policy Configuration UI

Status: Phase 1 (FE prototype) + Phase 2 (BE + off-mocks + tests) COMPLETE; Phase 3 (review) in progress.
Tests: pytest 30 · vitest 67 · playwright 1 - all green. Report: `scm-policy-config-test-report.md`.
Classification: **MODULE** (`scm`). No new tables, no schema migration, no RBAC migration - 
`scm.policy.manage` already exists (`274_scm_m0_views_reg.py:106`) and all target tables exist from
M0 (`app/models/scm.py`). New surface only: 1 router file + schemas + 1 service + FE area + 1 menu leaf.
UAC: `documentation/plans/scm/scm-policy-config-acceptance-criteria.md` (binding contract; written first).
Worktree: `/Users/tehjayson/Documents/foundryx/sorento_crm-scm`, branch `feat/scm-reorder-copilot`.

## 1. Approach (recommended, justified)

Add a single "Policies" area under Supply Chain at `/scm/policies`, gated `scm.policy.manage`, that
edits the three existing policy families and offers a resolution preview. This is **config for the
M3 reorder engine already built** - the golden constraint is that the preview and all validation
mirror the engine's real behaviour, never a parallel reimplementation.

Key design decisions:

- **Reuse the engine resolver verbatim.** The `resolve` endpoint calls
  `reorder_engine.resolve_policy_for_sku(db, product_id, warehouse_id)` (`reorder_engine.py:561`) and
  returns both the winner and the full candidate chain assembled from `load_policies` +
  `resolve_policy`. No resolution logic is reimplemented on FE or in the new service. (Risk #1.)
- **`scope_ref` storage matches the resolver's comparison keys** (UAC "Binding facts"): SKU →
  `products.id`; class → `category_code`; cell → `A-X`; global → NULL. The FE SearchableSelect for
  SKU holds `products.id` as the hidden option value with a `product_code · name` label, so no UUID
  is displayed (AC-NAV-4) while storage stays resolver-compatible. The list + resolve endpoints join
  back to `products`/`product_categories` to render human labels.
- **No `list_query_registry`.** SCM's existing grids (reorder recommendations) are bespoke SQL
  endpoints, not registry-backed; the policies grid follows the same local pattern with a small
  server-side sort allowlist (mirror `reorder_runs.py:_SORT`). No registry change needed. (Called out
  under "list_query registry changes": none.)
- **Reorder CRUD = modal; the two global forms = inline settings panels** (per CRUD UX standard +
  user decision). Global reorder default is edited through the same modal with scope locked.
- **Consumption-timing copy differs by family** (grill finding, verified `analytics_service.py:72`):
  reorder policies → "next reorder run"; classification + supplier scoring → "next analytics run".
- **Upsert the single global rows** by reusing the `ensure_*` ensure-defaults helpers'
  canonical-row selection so the UI and the analytics/engine paths always agree on which row wins
  when historical duplicates exist. (Risk #4.)

## 2. RBAC / module-guard impact

- Router mounted in `app/api/v1/scm/__init__.py` under the existing
  `require_module_enabled_with_api_key("scm")` wrapper (same as siblings).
- Writes + reads gated `scm.policy.manage`. **Decision:** read gate is also `scm.policy.manage` (not
  `scm.dashboard.view`). Justification: this is an admin/config surface, not a dashboard view; the
  people who read it are the people allowed to change it, and gating reads behind manage keeps the
  menu leaf from appearing for view-only dashboard users. (Contrast: `config.py` reads on
  `dashboard.view` because that knob is shown *alongside* dashboard numbers; the Policies area is
  standalone.) Recorded in AC-CFG-3.
- FE menu leaf added to `config/menu.config.tsx` Supply Chain group (`menu.config.tsx:384`) with
  `permission: 'scm.policy.manage'` - verify via sidebar click-through, not deep URL (feedback rule).

## 3. Migrations / registry / worker / embeddings

- **Migrations: NONE.** Tables + RBAC slug already exist. If a stray need appears (e.g. a partial
  unique index to enforce AC-VAL-8 at the DB level), flag it - but the plan enforces uniqueness in
  the service layer against active rows, matching how the engine already tolerates duplicates.
- **list_query registry: no change** (bespoke endpoint).
- **Embedding pipeline: no impact** (policy config is numeric OLTP config; not embedded).
- **Worker / RQ: no change.** No task edits. Note in PR: policy edits are consumed by the existing
  reorder-run task (reorder policies) and the analytics job (classification/supplier) on their next
  run - no new enqueue.

## 4. Phase 1 - FE prototype (mock data; NO backend, NO tests yet)

Location: `sorento_crm_frontend/app/(protected)/scm/policies/` mirroring the reorder folder shape
(`components/`, `hooks/`, `services/`, `types/`, `page.tsx`).

Build against mock fixtures/stubbed hooks:

- `page.tsx` → `PolicyConfigView` with three sections, each rendering even when empty (AC-STD-4):
  1. **Reorder policies** - DataGrid (AC-LIST-1/2) + "Add policy" toolbar button + row Edit/Delete;
     `AddEditPolicyModal` (AC-EDIT-*) with scope-driven target picker; `ConfirmDeleteDialog`.
  2. **Classification thresholds** - `ClassificationThresholdsPanel` inline form (AC-CFG-*).
  3. **Supplier scoring** - `SupplierScoringPanel` inline form (AC-SUP-*).
  4. **Resolution preview** - `ResolutionPreviewCard` (product + optional warehouse pickers →
     winner + chain, AC-PREV-*).
- Mock every hook state: loading / empty / error / data, plus modal create-success / validation-error
  / delete-confirm, and preview "global wins (no cell/class match)" (AC-PREV-3).
- Verify with Playwright MCP: sidebar → Supply Chain → Policies; exercise each state; screenshot the
  golden path + edges for the PR.

**Document the API contract at the top of `services/policyService.ts` (and mirror here):**

```
GET    /api/v1/scm/policies?page&limit&sort&dir&query
  -> { data: ReorderPolicyRow[], total }
  ReorderPolicyRow = {
    id, scope_type, scope_ref, scope_label,     // scope_label human-readable, no UUID
    policy_type, service_level, safety_stock_method, safety_days, review_period_days,
    forecast_window_days, baseline_source, spike_handling, buy_scope, dead_stock_days,
    overstock_days, min_override, max_override, priority, is_active,
    supplier_selection, lead_time_default_days   // hoisted out of factor_toggles
  }
POST   /api/v1/scm/policies              body = ReorderPolicyWrite       -> ReorderPolicyRow (201)
PUT    /api/v1/scm/policies/{id}         body = ReorderPolicyWrite       -> ReorderPolicyRow
DELETE /api/v1/scm/policies/{id}         -> 204   (422 if scope_type='global')
  ReorderPolicyWrite: same fields minus id/scope_label; scope_ref required unless global;
    for sku, scope_ref = products.id (from picker's hidden value).

GET    /api/v1/scm/policies/classification   -> AbcXyzPolicy (or {seeded defaults, exists:false})
PUT    /api/v1/scm/policies/classification   body = AbcXyzWrite   -> AbcXyzPolicy   (upsert single row)

GET    /api/v1/scm/policies/supplier-scoring -> SupplierScoringPolicy (or defaults)
PUT    /api/v1/scm/policies/supplier-scoring body = SupplierScoringWrite -> SupplierScoringPolicy

GET    /api/v1/scm/policies/resolve?product_id=&warehouse_id=
  -> {
       product: { product_code, product_name },
       warehouse: { warehouse_code, warehouse_name } | null,
       abc_xyz_cell: "A-X" | null, product_class: "<category_code>" | null,
       winner: ReorderPolicyRow | null,
       chain: [ { scope_type, scope_ref, scope_label, matched: bool, is_winner: bool,
                  reason: "most-specific-active" | "priority-tiebreak" | "no-match" | "inactive" } ],
       affected_sku_count?: number   // AC-PREV-5, may be omitted/DEFERRED
     }
```

All FE fetches go through `policyService.ts` → `lib/api-client`; params via `buildDataGridParams`;
scope-target product/class pickers via `SearchableSelect` reusing `scmOptionsService`
(`getProductOptions`, `getCategoryOptions`) - but note those return `product_code`/`category_id`
today; add `getProductOptionsById` (value = `products.id`) and a class-by-`category_code` option
source, since storage keys differ (see Risk #2). Do NOT touch backend in Phase 1.

Output of Phase 1: clickable mocked area + this locked contract. STOP for sign-off before Phase 2.

## 5. Phase 2 - Backend wiring + FE off-mocks, TEST-FIRST (red → green → refactor)

New backend files:
- `app/api/v1/scm/policies.py` - router (mounted in `scm/__init__.py`), all endpoints above.
- `app/schemas/scm_policy.py` - Pydantic request/response with validators encoding AC-VAL-*.
- `app/services/scm/policy_service.py` - CRUD + upsert + resolve-assembly (reusing
  `reorder_engine.resolve_policy_for_sku` / `load_policies` / `resolve_policy`;
  `analytics_service.ensure_*` canonical-row helpers for the two global upserts).

Validators (AC-VAL / AC-CFG / AC-SUP) live in the schema + service, raising `AppException(422)`
(global handler serializes). `factor_toggles` hoist/merge handled in the service so
`supplier_selection` + `lead_time_default_days` round-trip as first-class fields without clobbering
other JSONB keys.

**Tests land here, test-first (never deferred to Phase 3):**

pytest (`sorento_crm_backend/tests/scm/test_policy_config.py`):
- CRUD happy paths: list (paging/sort/search), create each scope, update, hard-delete removes the row.
- Auth denial (missing `scm.policy.manage` → 403) + module-disabled path.
- Validation: every AC-VAL-1..9, AC-CFG-2, AC-SUP-2 (each a failing test first).
- Delete-global blocked (AC-DEL-2). Uniqueness on active (scope_type, scope_ref) (AC-VAL-8).
- **Resolver parity (AC-PREV-2):** golden fixture with global + class + cell + SKU overrides; assert
  `/resolve` winner == `resolve_policy_for_sku(db, ...)` directly, and assert most-specific-wins +
  priority-tiebreak + no-classification→global (AC-PREV-1/3). This is the anti-drift test (Risk #1).
- Upsert single-row for classification + supplier scoring (second PUT updates, does not insert a 2nd
  active row).

vitest (`app/(protected)/scm/policies/**`):
- `policyService.test.ts` - request shaping (buildDataGridParams), extractApiError on failure,
  factor_toggles hoist mapping.
- Hook tests for `usePolicies` query + create/update/delete mutations (invalidate + toast).
- Component tests: grid (loading/empty/error/data + empty-hint AC-LIST-4), modal (scope-driven
  target picker, validation surfacing), the two panels, preview card (winner + chain + global-wins).

playwright (`e2e/scm-policies.spec.ts`):
- Sidebar → Supply Chain → Policies → add SKU override (modal, SearchableSelect) → row appears →
  edit → confirm-delete dialog → row gone; assert `browser_network_requests` hit the right
  `/api/v1/scm/policies*` endpoints; run the preview for a product and assert the winner/chain render.

Then wire FE off mocks onto the real service, delete mock fixtures (keep any reused by vitest).
Re-verify with Playwright MCP against the live stack (`:3000` + `:8000`; worker not required for this
feature). Output: BE merged, FE off-mocks, three suites green.

## 6. Phase 3 - Code review

`/code-review` on the Phase-1+2 diff; address with `--fix` / `/simplify`. PR must include: Phase-1
prototype screenshots, evidence Phase 2 drove from failing tests, and the test report keyed to the
UAC ids. Reviewer checklist = `documentation/reference/PR-CHECKLIST.md` + DoD gate.

## 7. Risks & mitigations

1. **Preview drifting from the engine.** The single largest risk. Mitigation: `/resolve` calls the
   engine's own `resolve_policy_for_sku`; the parity pytest asserts endpoint == engine on a golden
   fixture. Never reimplement precedence on FE or in the new service.
2. **`scope_ref` key mismatch (UUID vs code).** SKU stores `products.id`; class stores
   `category_code`; cell stores `A-X`. Getting this wrong = overrides silently never resolve.
   Mitigation: UAC "Binding facts" pins each key to the verified resolver line; the FE SKU picker
   holds `products.id` as hidden value; validators reject scope_ref that doesn't resolve (AC-VAL-9);
   the parity test catches a mis-stored SKU override (it wouldn't win).
3. **Silently-ineffective policies.** e.g. statistical SS with no service_level (engine falls back to
   fixed_days at run time). Mitigation: AC-VAL-7 blocks the save so the UI never lies about what the
   run will do.
4. **Historical duplicate global rows** (`config.py` already notes duplicates possible;
   `abc_xyz_policy`/`supplier_scoring_policy` schema allows many). Mitigation: reuse the canonical
   `global_policy_row` / `ensure_*` selection so upsert targets the SAME row the engine/analytics
   read; block deletion of any `scope_type='global'` reorder row (AC-DEL-2). Full dedupe of legacy
   duplicates is OUT OF SCOPE (flag if the user wants a cleanup migration).
5. **Wrong "takes effect" copy.** Classification + supplier scoring feed the **analytics** job, not
   the reorder run (verified `analytics_service.py:72`). Copy must say "next analytics run" for those
   two and "next reorder run" for reorder policies (AC-CFG-1/AC-SUP-1). Getting this wrong misleads
   the operator into expecting an immediate effect on a reorder run.
6. **Broad-impact edits.** Changing a global/class policy that many SKUs resolve to has wide blast
   radius. Mitigation (nice-to-have, AC-PREV-5): show "N SKUs currently resolve to this policy". If
   the count query is expensive, DEFER with a keyed note rather than shipping a slow endpoint.
7. **`factor_toggles` JSONB clobber.** Hoisting supplier_selection/lead_time_default_days must
   merge, not replace, the JSONB. Mitigation: service reads existing toggles, updates the two keys,
   writes back; a pytest asserts an unrelated toggle key survives an update.

## 8. Internal grill round (self-review of this plan)

- *Q: Is a resolution "chain" over-engineering vs just the winner?* No - the user explicitly wants to
  understand most-specific-wins (locked decision). The chain is the teaching surface; keep it.
- *Q: Should the global reorder default be creatable/deletable?* No - exactly one global default,
  always present, edited via modal, never deleted (AC-DEL-2, AC-EDIT-4).
- *Q: Read gate - dashboard.view or policy.manage?* Chose policy.manage (Section 2 justification);
  flagged as an explicit decision the user can veto.
- *Q: Do the two global forms belong in this feature at all, given they feed analytics not the run?*
  Yes - user locked "ALL engine policies in one Policies area"; but the copy must not conflate the
  two consumption paths (Risk #5). This was the main grill correction to the naive plan.
- *Q: Any migration hiding here?* Only if we want DB-level uniqueness for AC-VAL-8. Chose
  service-layer enforcement to match how the engine already tolerates duplicate rows; a partial
  unique index is a possible hardening the user can request.
- *Q: SKU scope_ref as UUID vs product_code - could we store product_code and change the resolver?*
  No - the engine is already built and shipped for M3; the config UI adapts to it, never the reverse
  (do not refactor a shipped engine for a config screen). Store `products.id`.

## 9. Open questions for the user (grill before Phase 1)

1. **Read gate:** confirm `scm.policy.manage` for BOTH read and write (vs `scm.dashboard.view` for
   read). I recommend manage-for-both; veto if view-only users should see policies read-only.
2. **AC-VAL-8 enforcement level:** service-layer only (my pick) vs a DB partial unique index
   migration on active (scope_type, scope_ref)? Index is stronger but adds the one migration this
   feature otherwise avoids.
3. **AC-VAL-7 strictness:** hard-block saving statistical SS without service_level (my pick), or
   allow-with-warning banner? Hard-block prevents a policy that silently won't do what it says.
4. **Supplier-weight sum:** enforce delivery_weight + quality_weight == 1.0 (my pick, AC-SUP-2) or
   allow arbitrary positive weights the analytics job normalizes? Depends on how M2 consumes them - 
   confirm the intended contract.
5. **Affected-SKU estimate (AC-PREV-5):** in scope for v1 or DEFERRED? It's the most expensive piece
   and a nice-to-have; I'll DEFER unless you want it now.
6. **Legacy duplicate global rows:** leave as-is (my pick - upsert the canonical row) or add a
   one-off cleanup migration to collapse duplicates? Out of scope unless you ask.
