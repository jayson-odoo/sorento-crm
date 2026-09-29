# UAC: scheduled reorder run scope (#1340)

- AC-1 A task with none of the scope keys set makes the same `create_run` call as before: all
  active warehouses, all products, no window, both demand legs, market off, full budget.
- AC-2 `warehouse_codes` set: the run plans only those warehouses.
- AC-3 `demand_class` `project` or `retail` reaches the run; absent means All. The page labels
  them Project / Dealer, with All as the empty value, exactly as Start Plan.
- AC-4 `horizon_start_days` / `horizon_end_days` resolve against the run day in the task's
  timezone (run day + N days); either absent means unbounded on that side.
- AC-5 `product_codes` set: the run plans only those products.
- AC-6 `budget` numeric caps the funding split; absent funds everything. `include_market`
  reaches the run.
- AC-7 Saving a bad value (unknown demand, start after end, negative end, negative budget, a
  non-list of warehouses, a string budget) fails the PATCH with 422 and stores nothing.
- AC-8 The block shows only on the `scm_reorder_run` task page; every select is the system
  dropdown; clearing a field sends null for its key.
- AC-9 The low stock email is unchanged; the report link covers the run's own scope.
- AC-10 Usable and non-clipped at 1280 and 375.
