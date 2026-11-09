# PLAN: low stock report per-location columns follow the run's locations (LOWSTOCK-LASTIN-LOCATION)

Status: in progress (small fix track: no migration, no auth/RBAC change, no new ingest surface)

## Problem

Owner, 9 Nov 2026, relaying purchasing (6 Nov): on the BRW low stock report, SRTWT167-QT's
"Last in qty" read `KMTU9395907 - 99`, the BRW-BB (project bin) line of a receipt split
BRW 121 / BRW-BB 180 / BRW-BB 99. Ruling: "when I run BRW stock report it should take BRW
only"; the same for Reorder Planning's low stock report and the daily low stock job.

## Where (all three surfaces are ONE code path)

- BRW low stock report + its Excel export, Reorder Planning's low stock report and the daily
  job's report all read the frozen `scm.order_summary_rows` that
  `summary_order_service.write_rows` writes for a reorder run; the daily job
  (`task_scheduler._handler_scm_reorder_run`) creates a run whose `warehouse_ids` come from its
  `warehouse_codes` metadata.
- `write_rows` read Last in from `spo_last_receipt_service.last_in_map`, which had NO
  location filter; BRW on hand / BRW PO qty / BRW incoming qty read the site-pool rule
  network-wide, not the run's `warehouse_ids`.

## Fix

One shared location set per run (`run.warehouse_ids` intersected with active site-pool
warehouses), passed to every per-location reader. No receipt in those locations means Last
in is blank.
