# UAC - Plan list and low stock report show every planned product

Plan: `PLAN-lowstock-show-all.md`. Numbering continues
`low-stock-last-in-and-list-scope-acceptance-criteria.md` (ends at AC-65).

## Plan list, tile, counters

- **AC-66** `GET /reorder-runs/{run}/recommendations` rows carry NO `hidden_by_default` key.
  A covered rec on the manual `reorder_level` basis with `net_position` far above its level
  is returned like any other rec.
- **AC-67** `GET /reorder-runs/{run}/plan-row-decisions` `total_count` counts every product
  with a decidable rec type: 1 buy + 1 covered-above-level + 1 covered-below-level = 3.
- **AC-68** `reorder_run_service._summarise(recs)["recommendation_count"]`,
  `decision_service._refresh_run_counts` (`planned_count`) and the run's own `planned_count`
  stamped at generation all count the covered-above-level rec: 1 buy + 1 covered-above-level
  + 1 covered-below-level = 3 (`recommendation_count` also counts an `exception` rec: 4).
- **AC-69** Migration `lsa_0001_show_all_counts` recounts every run's stored counters without
  the hidden filter and drops `scm.reorder_recommendation.hidden_by_default`: a run stamped the
  old way (`planned_count = 2`, `run_log.recommendation_count = 2`) holding 2 buys + 1
  covered-above-level + 1 exception reads 3 / 4 after `_recount_runs()`, and the same after a
  second call; `ReorderRecommendation` no longer maps the column; `alembic heads` is one head.
- **AC-70** The plan Lines tab renders every line `usePlanLines` returns, with no status filter
  and no Filters condition; the tile totals (`onTotalsChange`) and `PlanBudgetReview` count the
  same lines. A line whose payload still says `hidden_by_default: true` (an old run) renders.
- **AC-71** `app/services/scm/plan_scope.py`, `summary_order_service.visible_rows`,
  `summary_order_service._hidden_product_ids_for_run` and `lib/planLineFilters.ts` no longer
  exist.

## Order sheet and low stock workbook

- **AC-72** For a run with 3 frozen `order_summary_row`s of which 1 product's rec is covered
  with net above its manual level: `export_report(fmt="xlsx")` prints 3 data rows,
  `export_guard_stats.row_count == 3`, `report()` lists 3.
- **AC-73** Low stock "All" sheet == every `report()` row for the run, in `(category_code,
  product_code)` order, covered-above-level products included; `export_low_stock` returns
  `counts["all"]` equal to that number.
- **AC-74** Low stock "Low" sheet == the rows with `pool_on_hand < reorder_level`, both known,
  strictly below; a covered-above-level product with on hand 40 against level 100 IS on Low.
  At the level, above it, NULL level or NULL on hand are not low (unchanged).
- **AC-75** `MAX_LOW_STOCK_ROWS` applies to every frozen row: 5 frozen rows with a cap of 2
  refuse 422 whatever their recs say; the export route's guard reads the plain
  `export_guard_stats` count for the same run (5) and refuses at a cap of 3.
- **AC-76** `build_low_stock_view` (in-app preview), `export_low_stock` (Excel, chat push) and
  `ready_context` (daily trigger `report.rows` / `report.low`) all report the whole-run counts
  off the same `_split`, so for the AC-73/AC-74 run `rows == 3` and `low` equals the Low sheet
  length.

## Docs

- **AC-77** `low-stock-report.md` "What the workbook shows" says All is every product the plan
  planned and Low is on hand strictly below reorder level; `run-a-reorder-plan.md` Filters no
  longer describes a hidden-by-default row or a reveal condition.
- **AC-78** `PLAN-low-stock-last-in-and-list-scope.md` carries a dated note that S2 / AC-60..64
  are superseded by this plan (30 Sep 2026).

## Expected effect on the dev DB (run `dd28049a`, 18 Sep)

- All: 980 -> 1,393. Low: 604 -> 798. Plan list Lines: 980 -> 1,393.
