# UAC: low stock report, a ticked inactive location counts nowhere

Plan: `PLAN-lowstock-bins-regress-10nov.md`.

- AC-1: A run that ticks an active site-pool location plus an INACTIVE warehouse (site pool or
  project bin): the inactive one adds nothing to Last in, BRW on hand, BRW PO qty or BRW
  incoming qty, and is not in `report_warehouse_ids`.
- AC-2: A run that ticks an active project bin: it still counts in every per-location column
  (#2296 behaviour unchanged), even when an inactive warehouse is ticked beside it and the
  ticked count reaches the number of active warehouses.
- AC-3: A run with nothing ticked: active site pool only (unchanged).
- AC-4: A run ticking only the site-pool head: the sheet's incoming SPO and PO equal the grid
  cells (AC-13 parity). A run ticking the head and its project bin: sheet 136 / 442, grid
  40 / 42 (owner ruling 10 Nov, crew answer (a)).
- AC-5: The Town snapshot's compare label reads exactly as before (`Tue 27 Oct`), written by
  the shared date helper.
