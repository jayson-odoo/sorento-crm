# PLAN: scheduled reorder run takes its scope from the config page (#1340)

Status: in progress (full track: carries a data migration for the seeded description).
UAC: `scm-reorder-run-scheduled-scope-acceptance-criteria.md` (alongside).

## Owner ask (28 Sep, verbatim)

"the reorder run scope yeah I should be able to configure, yeah when I say channel it means the
demand project / dealer / all label, keep it"

## What exists (verified on origin/main d79b46c5)

- `_handler_scm_reorder_run` (`app/scheduler/task_scheduler.py:417`) reads only `budget` and
  `include_market`, calls `create_run(warehouse_codes=[], ...)`: every warehouse, every product,
  every open order, both demand legs. Then `dispatch_ready` fires the low stock email on that run.
- `create_run` already takes `warehouse_codes`, `product_codes`, `plan_horizon_start`,
  `plan_horizon_date`, `demand_class`. `CreateReorderRunRequest` validates the same fields.
- `PATCH /scheduled-tasks/{id}` merges `metadata`, null deletes a key, no validation.
- The config form writes only `company_ids`, `grace_percent` and the SLA channel switches.

## Build

1. `ScmReorderRunTaskMetadata` (`app/schemas/scheduled_task.py`): typed keys
   `warehouse_codes`, `product_codes`, `demand_class` (`project` | `retail`), `horizon_start_days`,
   `horizon_end_days`, `budget`, `include_market`; other keys (`company_ids`, `grace_percent`)
   pass through. `start <= end`; end not negative (the same refusal Start Plan gives a past
   cut-off: it would leave the run with no demand).
2. `update_task` validates the MERGED metadata for key `scm_reorder_run` and raises 422
   `invalid_task_metadata` before anything is written.
3. Handler: parses the metadata with the same model, resolves the relative window against the
   run day in the task's own timezone, builds a `CreateReorderRunRequest` (so
   `require_start_on_or_before_end` and `refuse_so_numbers_on_a_dealer_run` run exactly as on
   the API) and passes every field to `create_run`. Absent key = today's value, so an
   unconfigured task makes the identical call it makes today.
4. Config page: a block shown only for `scm_reorder_run`: Warehouses, Demand (All / Project /
   Dealer, the Start Plan options reused), Sales orders needed From / To in days from the run
   day, Products, Budget, Market insight. `mapFormToUpdateBody` sends null to clear each key.
5. Migration updates the seeded description, guarded on the seeded text so an edited
   description is kept.
6. No change to `low_stock_report_service`; the run's scope flows through to the email.

Out of scope: saved presets, per-user defaults, changes to Start Plan.
