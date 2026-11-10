# PLAN: low stock report, a ticked inactive location counts nowhere (#2296 regression)

Status: in review, PR #2309, reviewer READY (small fix track: under 300 lines, no migration, no auth/RBAC change)

Lane: LOWSTOCK-BINS-REGRESS. Release blocker on main a4af6565 (#2296, LOWSTOCK-PROJECT-BINS,
`PLAN-lowstock-project-bins-10nov.md`). UAC: `lowstock-bins-regress-acceptance-criteria.md`.

## Journey

Crew's release sweep on a fresh DB: `tests/scm/test_site_pool_supply.py` fails two tests on
a4af6565 that pass on ba0e7578.

- `test_inactive_site_pool_warehouse_counts_nowhere`: report incoming SPO 102, expected 40.
- `test_sheet_supply_columns_equal_the_grid_cells`: report incoming SPO 136, expected 40.

## Root cause

`summary_order_service.report_warehouse_ids` (`summary_order_service.py:927-929`) is the one
location set every per-location column reads. Before #2296 it kept the run's locations to
`pool_predicate.active_site_pool_sql` (active AND not a project bin). #2296 drops that whole
predicate for a run whose locations were ticked, so the `is_active` leg went with the
project-bin leg: a ticked INACTIVE warehouse now counts (its SPO 62 gives 40 + 62 = 102).

The 136 is a different matter: that test ticks the head AND its project bin, so 40 + 96 = 136
is exactly the owner's 10 Nov ruling (a ticked project bin counts). The test pinned the
pre-#2296 rule "sheet == grid" for a bin-ticked run. Crew answer 10 Nov, option (a): the grid's
buy maths was never in scope; amend the test (parity on a head-only run; the bin-ticked run
pins sheet 136/442 vs grid 40/42).

## Change

1. `report_warehouse_ids`: always keep `Warehouse.is_active`; only the project-bin leg yields
   to ticking. Nothing ticked still reads the full active site pool. No other reader changes:
   they read the set they are handed.
1b. Reviewer should-fix (same seam): only the ACTIVE ticked ids feed the "nothing ticked"
   count (`reorder_run_service._covers_every_warehouse`, ticked ids >= active warehouses).
   A ticked inactive id lifted the count to "All" and dropped a project bin ticked beside it.
2. Test 1 amended per crew (a), comment cites `PLAN-lowstock-project-bins-10nov.md:9-13`.
3. Separate commit: `app/services/town/snapshot.py:74-75` hand-rolled weekday/month tables go
   through a new `app/utils/date_format.fmt_day_label` (`Tue 27 Oct`, text unchanged), which
   clears `tests/test_date_format.py::test_no_hand_rolled_month_name_table_outside_the_helper`.

## Tests (red first)

- `tests/scm/test_lowstock_run_locations.py`: a ticked inactive project bin counts in no column
  (Last in, on hand, PO, incoming) and drops out of the shared set; a ticked inactive site-pool
  warehouse drops out of the shared set; a ticked inactive id does not make a ticked bin read as
  nothing ticked.
- `tests/scm/test_site_pool_supply.py`: the two sweep failures green; test 1 amended.
- `tests/test_date_format.py`: `fmt_day_label` unit test; the guard test green.
- `tests/town/test_town_snapshot_v3.py`: the label text unchanged (`Tue 27 Oct`, `Wed 2 Dec`).
