# PLAN - Plan list and low stock report show every planned product; Low = on hand below reorder level

Status: in progress - small fix track (no migration, no auth change, no new UI)
Domain: scm
Lane: LOWSTOCK-SHOW-ALL
Owner ruling source: chat, 30 Sep 2026 06:30 ("SHOW ALL HIDDEN ITEMS AGAIN")
UAC: `lowstock-show-all-acceptance-criteria.md`
Supersedes: `PLAN-low-stock-last-in-and-list-scope.md` S2 / AC-60..AC-64 (PR #919, 15 Sep),
`PLAN-plan-list-tile-sheet-one-scope.md` S6/S7 (AC-1..AC-5b, 10 Sep) and
`PLAN-reorder-one-formula.md` S3 (AC-12..AC-14, stored `hidden_by_default`) on the ONE
question of which rows are on the buyer's business by default. Everything else in those
plans stands.

## The ruling

The 12 Aug rule ("if net is not below my reorder level, it is not my business") is reversed.
Every product a run planned is on the list, in both exports, on the Decisions tile and in
the plans list's counts. The low stock workbook's "Low" sheet is the one and only narrowing,
and it is the client's own rule: `BRW on hand < reorder level`, nothing else. No "covered by
PO/SPO" column (owner said no).

## What hides rows today, measured in code

One rule, `app/services/scm/plan_scope.py:29-48`: `rec_type == covered` AND
`policy_type == reorder_level` AND a level exists AND `net_position > level`. It is stamped
once per recommendation at write time (`reorder_run_service._build_rec`, :3418-3424, into
`scm.reorder_recommendation.hidden_by_default`, migration 512) and READ in seven places:

| Reader | File:line | Effect today |
| --- | --- | --- |
| Recommendations serializer | `app/api/v1/scm/reorder_runs.py:1223,1524` | ships `hidden_by_default` to the FE |
| Plan list (FE) | `PlanLinesSection.tsx:116-155` (`defaultVisibleLines` / `visibleLines`) | drops flagged rows unless a "Covered by stock" status filter or a Filters `rec_type` condition (`lib/planLineFilters.ts`) reveals them |
| Tile totals / budget footer (FE) | `PlanLinesSection.tsx:168-171,395` | counted over `defaultVisibleLines` |
| Decisions total | `decision_service.list_plan_row_decisions` :1391-1407 | `total_count` excludes flagged products |
| Plans list counters | `decision_service._refresh_run_counts` :143, `reorder_run_service` :716 (`planned_count`), :4157 (`run_log.recommendation_count`) | exclude flagged rows |
| Order sheet export + guard | `summary_order_service.visible_rows` :1834-1865, `_hidden_product_ids_for_run` :1742-1771, `export_guard_stats` :1806-1822 | drop flagged product codes; guard subtracts them |
| Low stock workbook | `low_stock_report_service._split` :165-166 | reads `svc.visible_rows`; All and Low both lose the flagged rows |

The `plan_scope.py:16-19` docstring says `net_position` is "the rec's OWN stored column
ALONE - never the engine's decision net (`net_position + po_ordered`)". That is wrong:
`_build_rec` passes `c["net"]` (:3423), which `_planning_rows` builds as
`net_position + po_ordered` (:2665), i.e. **on hand + incoming SPO + open PO - committed
demand** (`explain_net`, :3871/:3982). The module is deleted in this lane (its only caller
was the stamp), so the wrong sentence goes with it; the correct definition of net is
recorded here.

## Decision: stop computing the flag, not just stop hiding

Nothing else needs `hidden_by_default` once no reader narrows on it: the tile and the plans
list counters exist to count "what the list shows" (owner, 10 Sep), and the list now shows
everything. Keeping the stamp alive with zero readers would be a rule with no consumer, and
old runs already carry `true` on 413 rows, so a reader left behind would keep hiding on
those runs. So:

- `plan_scope.py` is deleted; `_build_rec` no longer stamps the column.
- Every reader above stops reading it. `visible_rows` and `_hidden_product_ids_for_run`
  are deleted; `export_report` and `_split` read `rep["rows"]` whole; `export_guard_stats`
  is one COUNT again.
- The FE list renders `planLines.lines` as they arrive; `defaultVisibleLines`,
  `visibleLines`, `appliedFilterGroup`, `lib/planLineFilters.ts` and the grid's
  `onFilterGroupChange` prop go (the reveal has nothing left to reveal). The serializer
  drops the key and `reorder.types.ts` drops the field.
- **The column stays** (`scm.reorder_recommendation.hidden_by_default`, NOT NULL DEFAULT
  false, migration 512): new rows land `false` through the server default, nothing reads
  it. Dropping it is a migration, which puts this lane on the migration track for no
  behaviour. Trigger to drop it: the next SCM lane that already carries a migration adds
  `op.drop_column("reorder_recommendation", "hidden_by_default", schema="scm")`.

## Expected effect (dev DB, run `dd28049a`, 18 Sep)

| Figure | Before | After |
| --- | --- | --- |
| Planned rows in the run | 1,393 | 1,393 |
| Flagged hidden by default | 413 | 0 read |
| Plan list / All sheet / order sheet rows | 980 | 1,393 |
| Low sheet rows (`pool_on_hand < reorder_level`) | 604 | 798 |

The 194 rows joining Low were hidden covered rows that sit below their raw level (on hand
below level, but net above it once SPO/PO supply is counted).

## Slices (one lane, one PR)

### S1 - Backend: every reader stops narrowing
- `summary_order_service`: delete `_hidden_product_ids_for_run`, `visible_rows`;
  `export_guard_stats` returns the plain COUNT; `export_report` prints `rep["rows"]`.
- `low_stock_report_service._split`: `rows = rep["rows"]`; docstrings updated. `_is_low`
  unchanged. Every caller follows through the one builder: in-app preview
  (`order_summary.py:370` `build_low_stock_view`), Excel export (`export_tasks.py:1176`
  `export_low_stock`), the export cap guard (`order_summary.py:199,227-232`), the chat/
  WhatsApp tool (`api/v1/scm/low_stock_report.py:401` -> `generate_low_stock_report`),
  the daily ready trigger counts (`scheduler/task_scheduler.py:525` -> `dispatch_ready` ->
  `ready_context` -> `_split`).
- `decision_service`: `_refresh_run_counts` drops the `FILTER (WHERE NOT r.hidden_by_default)`;
  `list_plan_row_decisions` counts every decidable product.
- `reorder_run_service`: `_build_rec` stops stamping; `planned_count` and `_summarise`'s
  `recommendation_count` count every rec of the decidable / every type respectively.
- `reorder_runs.py`: serializer and its SELECT drop `hidden_by_default`.
- `models/scm.py`: the column stays, its comment says it is retired and why.
- `plan_scope.py`: deleted.

### S2 - Frontend: the list is the run
- `PlanLinesSection.tsx`: `gridRows`, the grid, `reportedTotals` and `PlanBudgetReview` all
  read `planLines.lines`. Remove `appliedFilterGroup` and the `planLineFilters` import.
- `PlanLinesGrid.tsx`: drop the `onFilterGroupChange` prop (its only consumer was the reveal).
- Delete `lib/planLineFilters.ts` + its test and `PlanLinesSection.visibleLines.test.tsx`.
- `reorder.types.ts`: drop `hidden_by_default`.

### S3 - Tests (red first)
- `tests/scm/test_low_stock_report.py`: `test_low_sheet_membership` (a covered-above-net
  row below its raw level IS low), `test_all_sheet_matches_the_plan_list_hidden_dropped`
  becomes `test_all_sheet_is_every_planned_row` (All == `report()` rows == order sheet
  rows), `test_export_low_stock_counts_are_the_visible_counts` -> whole-run counts,
  `test_low_stock_guard_uses_export_guard_stats` -> guard counts every frozen row,
  `test_cap_applies_to_visible_rows` -> cap on every frozen row. `_hide` is deleted.
- `tests/scm/test_plan_scope_hidden_by_default.py` and
  `tests/scm/test_hidden_by_default_column.py` are replaced by
  `tests/scm/test_plan_shows_every_row.py`: the serializer carries no `hidden_by_default`
  key; `plan-row-decisions` `total_count` counts the covered-above-level product; export,
  guard and `report()` agree on 3 of 3; `_summarise`, `_refresh_run_counts` and
  `planned_count` count the covered-above-level rec; `_build_rec` leaves the column false.
- FE: `PlanLinesSection.test.tsx` cases that pin hiding flip to "renders every line";
  `planLineFilters.test.ts` and `PlanLinesSection.visibleLines.test.tsx` deleted.

### S4 - Docs
- `documentation/user-guides/supply-chain/low-stock-report.md` "What the workbook shows".
- `documentation/user-guides/supply-chain/run-a-reorder-plan.md` Filters paragraph.
- Dated supersede notes on `PLAN-low-stock-last-in-and-list-scope.md` (S2 / AC-60..64),
  `PLAN-plan-list-tile-sheet-one-scope.md` and `PLAN-reorder-one-formula.md` S3.

## Not in scope
- Dropping the `hidden_by_default` column (trigger named above).
- Any new column on the workbook (owner: no "covered by PO/SPO" column).
- `orderQtyLedger.lineBreachStatus` ("Line not breached" sentence on the ledger) - a
  per-row explanation, not a visibility rule; untouched.

## Verification
- pytest on a private sandbox DB: `tests/scm/test_low_stock_report.py
  tests/scm/test_plan_shows_every_row.py tests/scm/test_order_summary_sheet.py
  tests/scm/test_summary_order_service.py tests/scm/test_order_sheet_export_downloads.py
  tests/scm/test_reorder_one_formula.py tests/scm/test_plan_row_decisions*.py`, then the
  rest of `tests/scm` in chunks.
- vitest: `app/(protected)/scm/reorder`.
- Hand test (owner, crew test copy): `laneboard/scripts/<PR>.md`.
