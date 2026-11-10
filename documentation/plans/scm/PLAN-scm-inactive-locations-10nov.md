# PLAN: reorder / low stock scope uses active locations only

Status: in progress (small fix track: under ~300 lines, no migration, no auth/RBAC change)

Lane: SCM-INACTIVE-LOCATIONS. Follow-up of #2309 (LOWSTOCK-BINS-REGRESS, evidence comment
https://github.com/jayson-odoo/sorento-crm/pull/2309#issuecomment-6761732471).

## Journey

Owner, 10 Nov 2026 ~15:50 MYT, option (a): "why is an inactive location allowed to be ticked at
the first place?" and "make sure our SCM reorder plan now used locations are all active".

## Behaviour (option a)

1. Every place the reorder / low stock / daily job scope is picked offers ACTIVE locations only:
   `GET /api/v1/scm/dashboard/warehouses?active_only=true` (`ScmDashboardService.warehouses`,
   `w.is_active = true`), read by `useActiveWarehouseOptions` in Start Plan, Re-plan and the
   daily job scope fields. Without the flag the dashboard and the SO / PO detail code-to-name
   lookups (`useWarehouseOptions`) still see every location.
2. `create_run` refuses an inactive warehouse code with 422, naming every inactive code, same
   shape as the excluded-product refusal: `Inactive location, cannot be named in a run: X, Y`.
   Covers chat, API and anything else that reaches `create_run` with stale codes.
3. Saved scopes drop inactive codes and say which:
   - Re-plan prefill: `resolve_run_scope` keeps `warehouse_codes` whole (the run's own
     history, still shown in the header's read view) and adds `inactive_warehouse_codes`;
     the Re-plan edit (`PlanHeaderTab.beginEdit`) drops those and shows one line
     `Skipped inactive location X`. If every ticked code was inactive, the
     prefill is empty (the nothing-ticked rule: every active location, the report reads the
     site pool) and the line adds `, planning every active location instead`.
   - Daily job: the handler drops inactive codes before `create_run` and the run summary carries
     `message: "Skipped inactive location X"` (same fallback wording when all are inactive).
4. Unchanged: owner ruling 9 Nov (report columns = selected locations), #2309 (inactive never
   counts).

## Tests (red first)

- Dashboard warehouses payload omits an inactive warehouse.
- `create_run` with an inactive code: 422 naming it, no run row.
- `resolve_run_scope` reports the codes deactivated since the run (`inactive_warehouse_codes`), run detail carries them.
- Daily job handler kwargs drop the inactive code, summary message names it; all-inactive falls
  back to `[]` with the fallback wording.
- FE: plan header notice renders the skipped codes.
- Same code active in one company and inactive in another (all-companies scope): the run
  stores only the active warehouse.
- `test_site_pool_supply.py::test_inactive_site_pool_warehouse_counts_nowhere` (#2309's guard)
  deactivates its warehouse after `create_run`, the only way an inactive location can still
  sit in a run now.
