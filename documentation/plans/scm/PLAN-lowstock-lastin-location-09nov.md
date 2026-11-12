# PLAN: low stock report per-location columns follow the run's locations (LOWSTOCK-LASTIN-LOCATION)

Status: implemented, awaiting owner hand test (small fix track: no migration, no auth/RBAC
change, no new ingest surface)

## Problem

Owner, 9 Nov 2026, relaying purchasing (6 Nov): on the BRW low stock report, SRTWT167-QT's
"Last in qty" read `KMTU9395907 - 99`, the BRW-BB (project bin) line of a receipt split
BRW 121 / BRW-BB 180 / BRW-BB 99. Ruling: "when I run BRW stock report it should take BRW
only"; the same for Reorder Planning's low stock report and the daily low stock job.

## Where (all three surfaces are ONE code path)

Every surface prints the frozen `scm.order_summary_row` rows that
`summary_order_service.write_rows` writes for one `scm.reorder_run`:

- (a) BRW low stock report (chat route `app/api/v1/scm/low_stock_report.py::_prepare` calls
  `reorder_run_service.create_run(warehouse_codes)`) and its Excel export
  (`low_stock_report_service._sheet_row` / `export_low_stock`).
- (b) Reorder Planning's low stock report (`/scm/low-stock-report/<runId>`, same view).
- (c) The daily job (`task_scheduler._handler_scm_reorder_run`): `create_run` with the task
  config's `warehouse_codes`, then `low_stock_report_service.dispatch_ready`.

`create_run` stamps `run.warehouse_ids` (`reorder_run_service._resolve_warehouse_ids`).

Column sources before this lane (`write_rows`):

| Column | Source | Location filter before |
| --- | --- | --- |
| Last in qty / date | `spo_allocations` newest visible line (`spo_last_receipt_service.last_in_map`): SPO qty, container, `coalesce(expected, issue, created)` | NONE (network, project bins included) - the bug |
| BRW on hand | `stock.quantity_on_hand` (`_pool_on_hand_map`) | active site-pool, network-wide |
| BRW PO qty | open `purchase_order_lines` (`site_pool_supply.open_po_by_product`) | active site-pool, network-wide |
| BRW incoming qty | open `spo_allocations` + container (`open_spo_by_product`) | active site-pool, network-wide |
| Dealer o/s | recommendations' frozen `retail_committed` | already the run's own (recs are per run location) |

## Fix

One shared set, `summary_order_service.report_warehouse_ids(run)`: the run's
`warehouse_ids` kept to active site-pool locations (so a project bin never answers a BRW
column, even on a run that also planned it). All four readers above take it as
`warehouse_ids`. No receipt in those locations means Last in is blank. A run with a NULL
scope (none stored) keeps the pre-lane readings; `[]` matches nothing. `last_in_map` matches
a line by warehouse id, and by the book's `location_code` only when the line has no
warehouse id.

Last in qty is ONE RECEIPT, not one line (crew decision, 10 Nov 2026): the lines of the
newest SPO number + container + delivery date inside the report locations, SUMMED, so it
matches BRW incoming qty (SRTWB248 on BRW + BRW-RSV: 170 + 4 = 174). A tie on date and
recorded instant falls to SPO number, then container, highest first: never row order.

## Consequences named for the owner

- OPEN with the owner, unchanged here: whether a project bin (BRW-IB, BRW-BB) picked in
  Start Plan should count in these columns. Today `report_warehouse_ids` drops it on purpose.

- On a location-scoped run, "BRW on hand" is now that location's stock, so the "Low stock"
  sheet (`_is_low`: on hand below reorder level) can list a product that has stock only
  elsewhere in the network, and the Suggestion's "Stock N" part caps against the same figure.
  This is the ruling applied to the on hand column; an all-locations run is unchanged.
- Not changed (not on the low stock sheet): `CoverageService.network_positions` figures and
  `_demand_aggregates` line counts / ageing stay network-wide.

## Excel "blank row"

The export writes one sheet row per product: BRW PO qty is ONE cell with line breaks
(`800\n202609-S0079 - 300\n202610-S0158 - 500`), pinned by
`test_excel_export_is_one_row_per_item_with_the_brw_last_in`. The extra row in the relayed
copy is that cell's third line as rendered or pasted, not a row the file holds.
