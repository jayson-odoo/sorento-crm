# SCM Policy Configuration - Phase 2 Test Report

Status: Phase 2 complete. Keyed to `scm-policy-config-acceptance-criteria.md`.
Suites: **pytest 30 green** (`tests/scm/test_policy_config.py`), **vitest 67 green**
(`app/(protected)/scm/policies/**`, 7 files), **playwright 1 green**
(`e2e/scm-policies.spec.ts`). Stack: FE :3000 (prod build), BE :8005, live prod-copy DB.

Legend: PASS / DEFERRED / N-A (backend-owned mirror). Every row names the suite that proves it.

## A - Navigation & access
| AC | Verdict | Evidence |
|----|---------|----------|
| AC-NAV-1 | PASS | playwright: sidebar → Supply Chain → Policies leaf renders + routes `/scm/policies`. |
| AC-NAV-2 | PASS | pytest: bare user + dashboard-view-only → 403 on policy routes. FE leaf gated `scm.policy.manage`. |
| AC-NAV-3 | DEFERRED | Module-disabled path sits at the scm package guard; not exercised by these suites (same guard as all sibling scm routes). |
| AC-NAV-4 | PASS | vitest (grid/service): scope_label human-readable, no UUID; option mappers hold `products.id` as hidden value only. |

## B - Reorder policies list
| AC | Verdict | Evidence |
|----|---------|----------|
| AC-LIST-1 | PASS | pytest list + vitest grid: columns incl. scope, scope target, policy type, key values. |
| AC-LIST-2 | DEFERRED | DataGrid resize config not asserted in tests (visual; browser-verified). |
| AC-LIST-3 | PASS | Now genuinely server-side: `ReorderPolicyGrid` sets `manualPagination`/`manualSorting`/`manualFiltering` and threads `{pageIndex,pageSize,sorting,debouncedSearch}` into `useReorderPolicies` → `buildDataGridParams` → `GET /policies` (page/limit/sort/dir/query). No client-side truncation-at-1000; search reaches backend-only fields (product_code/name/category). vitest grid: hook called with the paging/sort/search args + `pageCount`/`rowCount` from `total`. |
| AC-LIST-4 | PASS | vitest grid: global-only empty-hint renders. |
| AC-LIST-5 | PASS | vitest/browser: "next reorder run" copy near grid. |

## C - Create / edit modal
| AC | Verdict | Evidence |
|----|---------|----------|
| AC-EDIT-1 | PASS | vitest modal: scope switch swaps target picker (sku/product_class/abc_xyz_cell). |
| AC-EDIT-2 | PASS | All engine fields now surfaced as inputs - the previously hardcoded/carried-silently `forecast_window_days` (number), `baseline_source`, `spike_handling`, `buy_scope` (SearchableSelect, plain labels) join the rest. Create defaults to the engine defaults (90 / continuous_only / committed_only / network per `reorder_engine.ensure_reorder_policy_defaults`); edit preserves existing values. vitest modal: four fields render defaulted, round-trip edited values into the write body, and preserve existing values on edit. pytest: write persists all fields incl. hoisted supplier_selection + lead_time_default_days. |
| AC-EDIT-3 | PASS | All dropdowns `SearchableSelect` (no raw select). |
| AC-EDIT-4 | PASS | vitest modal: edit-global locks scope, hides target + delete. |
| AC-EDIT-5 | PASS | vitest hooks/modal: success closes+invalidates+toast; error toasts extracted msg, modal stays open. |
| AC-EDIT-6 | DEFERRED | ~375px modal scroll not asserted (shared dialog scroll rule; visual). |

## D - Validation (BE-authoritative)
| AC | Verdict | Evidence |
|----|---------|----------|
| AC-VAL-1 | PASS | pytest: non-global empty scope_ref → 422. |
| AC-VAL-2 | PASS | pytest: global stores scope_ref NULL. |
| AC-VAL-3 | PASS | pytest: service_level ∉ (0,1) → 422. |
| AC-VAL-4 | PASS | pytest: day fields ≤ 0 → 422. |
| AC-VAL-5 | PASS | pytest: min_override > max_override → 422. |
| AC-VAL-6 | PASS | pytest: invalid enum → 422. |
| AC-VAL-7 | PASS | pytest + vitest: statistical SS without service_level → 422. |
| AC-VAL-8 | PASS | pytest: duplicate active (scope_type, scope_ref) → 422; editing same row allowed. |
| AC-VAL-9 | PASS | pytest: sku→existing product, class→known category_code, cell→`[ABC]-[XYZ]`, else 422. |

## E - Delete
| AC | Verdict | Evidence |
|----|---------|----------|
| AC-DEL-1 | PASS | vitest grid + playwright: AlertDialog confirm, hard-delete, refetch, toast. |
| AC-DEL-2 | PASS | pytest: DELETE global → 422; vitest: no delete affordance on global row. |
| AC-DEL-3 | PASS | Uses `AlertDialog`, never `confirm()`. |

## F - Classification thresholds
| AC | Verdict | Evidence |
|----|---------|----------|
| AC-CFG-1 | PASS | vitest panel: values + empty state + "next analytics run" copy. |
| AC-CFG-2 | PASS | pytest: a,b ∈ (0,1), a+b < 1, x ≤ y, both > 0 → 422; fraction round-trip + analytics parity. |
| AC-CFG-3 | PASS | pytest: read gate = `scm.policy.manage`. |

## G - Supplier scoring
| AC | Verdict | Evidence |
|----|---------|----------|
| AC-SUP-1 | PASS | vitest panel: values + empty state + "next analytics run" copy. |
| AC-SUP-2 | PASS | pytest: weights ∈ [0,1], sum == 1.0±0.001, grace ≥ 0, min_sample ≥ 1 → 422; single-row upsert. |

## H - Resolution preview
| AC | Verdict | Evidence |
|----|---------|----------|
| AC-PREV-1 | PASS | vitest card + playwright: winner + chain (which matched, which won, why). |
| AC-PREV-2 | PASS | pytest: `/resolve` winner id == `resolve_policy_for_sku(db,...)`; most-specific-wins + priority-tiebreak + no-class→global. |
| AC-PREV-3 | PASS | vitest + browser: no-match SKU → global wins with explanatory note, not error. |
| AC-PREV-4 | PASS | product picker shows code/name; endpoint takes resolved id. |
| AC-PREV-5 | DEFERRED | Affected-SKU estimate out of scope for v1 (keyed note). |

## I - Layering & standards
| AC | Verdict | Evidence |
|----|---------|----------|
| AC-STD-1 | PASS | UI → hooks → service → api-client; no component fetch. |
| AC-STD-2 | PASS | `extractApiError` + `buildDataGridParams` + `SearchableSelect` + `AlertDialog`; no hand-rolled equivalents. |
| AC-STD-3 | PASS | Writes gated `scm.policy.manage`; module guard at package mount. |
| AC-STD-4 | PASS | Every section renders empty states. |

## Known follow-ups (non-blocking)
- Product scope picker client-filters the first 100 products (shared `SearchableSelect` static
  limitation, app-wide) - a SKU beyond the first 100 is not findable. Tracked by the
  searchable-dropdown-standard migration (async `fetchOptions` mode). `products/select` already
  accepts `?query=`; the switch is FE-only when that component gains async mode.
- AC-NAV-3 (module-disabled), AC-LIST-2 (grid resize), AC-EDIT-6 (mobile modal scroll) not
  asserted by automated tests - carried by the shared components + browser verification.
