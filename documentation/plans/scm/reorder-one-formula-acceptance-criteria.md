# UAC: Reorder planning - one formula, one scope

Plan: `PLAN-reorder-one-formula.md`. Each AC names the test that pins it. B2155 figures: on hand 128, SPO 0, PO 339, project 493, retail 170, no level.

## Formula (S4)

- **AC-1** A product-grain row with no buyer level plans as level 0: `recommended_qty` = `0 - net` = 196 for B2155, `rounded_qty` 196 with no MOQ, `inputs.reorder_level` stays null, `inputs.needs_level` stays true, `reason_label` names the level-0 breach, never "project buy". Test: `tests/scm/test_reorder_one_formula.py::test_no_level_product_row_buys_level_zero_gap`.
- **AC-2** A level-set product-grain row: CBMC5570 (level 100, retail 2, PO 1) -> `recommended_qty` 101; the open PO is netted ONCE (engine), never again by the sheet or the grid. Test: `::test_level_row_nets_po_once`.
- **AC-3** A location-grain row with project demand no longer adds `project_need` on top of the retail netting: project is inside `net`, `recommended_qty = level - net` (level 0 when none). Test: `::test_location_row_project_inside_net`.
- **AC-4** Sheet `suggested_qty` = rounded buy (196), `suggestion` = "Stock 128 + PO 339 + Buy 196"; CSK2800-QT-shaped row = "Buy 914"; a covered row = "Nothing" and `suggested_qty` 0. Test: `tests/scm/test_order_summary_sheet.py::test_suggestion_parts_are_display_of_the_net`.
- **AC-5** Frontend `suggestedDecisionFor(line)` for the B2155 line returns `{stock: {qty: 128}, po: 339, buy: 196}`; `summariseMix` prints "Stock 128 + PO 339 + Buy 196"; for CBMC5570 `{po: 1, buy: 101}`. No `poOffset` subtraction on top of `order_qty`. Test: `lib/planEdits.test.ts` ("one formula" describe block).
- **AC-6** `composeMixture` with the B2155 parts: turning stock off -> Buy 324 (196 + 128); PO off -> Buy 535; editing stock to 100 -> Buy 224. Never negative. Test: `lib/orderQtyLedger.test.ts`.
- **AC-7** Ledger "Gap to line" = `level - net` (196) on the B2155 line, and "Buy before rounding" 196; a covered row above its line still prints "Line not breached". Test: `components/PlanOrderQtyLedger.test.tsx`.
- **AC-8** Panel prefill: BRW input 128, PO input 339, Buy 196 for the B2155 line; a project-only line with open PO still shows the PO part (P8 retired). Test: `components/PlanRowPanel.test.tsx`.

## Sheet Dealer o/s (S2)

- **AC-9** On a run carrying the channel snapshot, `OrderSummaryRow.dealer_outstanding` = sum of the product's recs' `inputs.retail_committed` (170 for B2155) even when the SO book holds 1381 open retail units outside the run's window; `dealer_outstanding_line_count` follows the same source. Legacy run (no snapshot): unchanged SO-book read. Test: `tests/scm/test_summary_order_service.py::test_dealer_outstanding_is_the_runs_horizoned_retail`.
- **AC-10** The exported sheet (PDF rows + xlsx rows) prints that figure in "Dealer o/s". Test: `tests/scm/test_order_summary_sheet.py::test_sheet_dealer_os_matches_grid_retail`.

## One scope for the counters (S3)

- **AC-11** Migration adds `scm.reorder_recommendation.hidden_by_default` (NOT NULL, default false) and backfills existing rows so that, for every seeded rec, the column equals `plan_scope.hidden_by_default(...)` evaluated in Python. Test: `tests/scm/test_hidden_by_default_column.py::test_backfill_matches_python_rule`.
- **AC-12** A fresh run stamps the column at write time; `run_log.recommendation_count` counts only rows where it is false; `_refresh_run_counts` planned counts DISTINCT product over rows where it is false; the recommendations serializer's `hidden_by_default` and `list_plan_row_decisions` total read the column. Seed: 3 products, one covered-above-level (hidden), expect count 2 everywhere. Test: `::test_run_counts_read_the_column`.
- **AC-13** `PlanBudgetReview` receives the default-visible totals: with 3 lines of which 1 is `hidden_by_default`, the footer reads "0 of 2" and "2 lines still to decide". Test: `components/PlanLinesSection.test.tsx`.
- **AC-14** Plan list row: Lines and Decided total equal the tile's total on the same run (browser evidence, lane end).

## Browser (lane end, agent-browser, evidence under `documentation/plans/scm/evidence/reorder-plan-tidy/`)

- **AC-15** Latest plan on the lane stack: footer, tile and plan-list Lines agree; a B2155-shaped row reads Suggested qty = the Buy part of its Suggestion; the ledger's Gap to line equals its Buy before rounding.
