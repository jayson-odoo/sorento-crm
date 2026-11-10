# PLAN: reorder / low stock scope uses active locations only

Status: in progress (small fix track: under ~300 lines, no migration, no auth/RBAC change)

Lane: SCM-INACTIVE-LOCATIONS. Follow-up of #2309 (LOWSTOCK-BINS-REGRESS, evidence comment
https://github.com/jayson-odoo/sorento-crm/pull/2309#issuecomment-6761732471).

## Journey

Owner, 10 Nov 2026 ~15:50 MYT, option (a): "why is an inactive location allowed to be ticked at
the first place?" and "make sure our SCM reorder plan now used locations are all active".

## Behaviour (option a)

1. Every place the reorder / low stock / daily job scope is picked offers ACTIVE locations only:
   `GET /api/v1/scm/dashboard/warehouses` (`ScmDashboardService.warehouses`) gains
   `w.is_active = true`. It feeds Start Plan, Re-plan (both via `useWarehouseOptions`) and the
   daily job scope fields.
2. `create_run` refuses an inactive warehouse code with 422, naming every inactive code, same
   shape as the excluded-product refusal: `Inactive location, cannot be named in a run: X, Y`.
   Covers chat, API and anything else that reaches `create_run` with stale codes.
3. Saved scopes drop inactive codes and say which:
   - Re-plan prefill: `resolve_run_scope` returns only active codes in `warehouse_codes` plus
     `inactive_warehouse_codes`; the plan header shows one line
     `Skipped inactive location X` when re-planning. If every ticked code was inactive, the
     prefill is empty (the nothing-ticked rule: every active location, the report reads the
     site pool) and the line adds `, planning every active location instead`.
   - Daily job: the handler drops inactive codes before `create_run` and the run summary carries
     `message: "Skipped inactive location X"` (same fallback wording when all are inactive).
4. Unchanged: owner ruling 9 Nov (report columns = selected locations), #2309 (inactive never
   counts).

## Tests (red first)

- Dashboard warehouses payload omits an inactive warehouse.
- `create_run` with an inactive code: 422 naming it, no run row.
- `resolve_run_scope` drops the inactive code and reports it; all-inactive gives `[]`.
- Daily job handler kwargs drop the inactive code, summary message names it; all-inactive falls
  back to `[]` with the fallback wording.
- FE: plan header notice renders the skipped codes.
