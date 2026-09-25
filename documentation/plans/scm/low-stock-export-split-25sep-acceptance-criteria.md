# UAC: Low stock report - workbook split by supplier / category

Plan: `PLAN-low-stock-export-split-25sep.md`
Owner rulings: R2-R4 (lavish round, 25 Sep 2026); R1, R5, R6 standing.

## Shared split helpers (lifted)

- AC-1 `workbook_split.split_rows(rows, "supplier", supplier=..., category=...)` returns `(key, rows)` pairs keyed on the supplier callable, `"No supplier"` for a blank/None, sorted by the sanitised key case-insensitive; `"category"` keys on the category callable with `"No category"`; `"supplier_category"` keys on `"<supplier> - <category>"` and only pairs that have at least one row appear.
- AC-1b `sanitize_sheet_title` strips `[]:*?/\`, trims, cuts to `limit` (default 31), never returns empty (`"Sheet"`); `unique_sheet_title` appends ` (2)`, ` (3)` on a collision within `limit`.
- AC-2 The Stock Debt export (`tests/scm/test_stock_debt_routes.py` split cases AC-13..AC-16) passes UNCHANGED after the lift; `stock_debt_service` no longer defines its own `_sanitize_sheet_title` / `_unique_sheet_title`.

## Backend workbook

- AC-3 `export_low_stock(split="none")` is today's workbook: "Low stock" then "All", sixteen columns, unchanged (the existing 18 tests stay green).
- AC-4 `split="category"`: for every distinct master-data `category_code` among the visible rows (blank -> "No category"), two sheets in order `"<category> - Low"` then `"<category>"`; groups in sanitised-title order; each `"<category>"` sheet holds exactly the group's rows in `product_code` order; each ` - Low` sheet holds the group's rows with `pool_on_hand < reorder_level`, header only when there are none (A3). The workbook's total "All" rows across groups equals the `split="none"` "All" count.
- AC-5 `split="supplier"`: keyed on the frozen row's `supplier_name` (blank -> "No supplier"), same pair rule as AC-4.
- AC-6 `split="supplier_category"`: keyed on `"<supplier> - <category>"`, only present pairs; a key longer than 25 chars is cut so `"<base> - Low"` fits 31; two keys that agree on the cut get ` (2)` on BOTH sheets of the second pair.
- AC-7 Text cells on every split sheet go through `_xlsx_safe_text` exactly as the unsplit sheets do (no new writer; `_sheet_row` is the only row builder).
- AC-8 (R5) `split="supplier"` or `"supplier_category"` with `include_supplier=False` raises 422 before any sheet is written; `split="category"` with `include_supplier=False` works and drops the Supplier column on every sheet.
- AC-9 The cap: a run with more than `MAX_LOW_STOCK_ROWS` visible rows is refused 422 whatever the split (the split never changes the count that is checked).
- AC-10 The returned counts dict carries `low`, `all` (unchanged semantics: whole run, not per group) and `sheets`.

## Backend route + task

- AC-11 `POST /scm/order-summary/export` body `{run_id, format: "low_stock_xlsx", split: "supplier"}` creates the `low_stock_xlsx` download row and enqueues `generate_low_stock_report` with `split="supplier"` in its kwargs; `split` omitted enqueues with `split="none"` (or no kwarg), and the existing enqueue test stays green.
- AC-12 `split: "bogus"` -> 422 (schema), no download row.
- AC-13 (R6) `split: "supplier"` with `format: "xlsx"`, `"pdf"` or `"oi_worksheet"` -> 422 "split applies to the low stock report only", no download row, nothing enqueued.
- AC-14 `generate_low_stock_report(..., split="category")` forwards `split` to `export_low_stock` and marks the row ready with `row_count_low` / `row_count_all` as before; the log line carries the sheet count.
- AC-15 The in-flight 409 is unchanged: a second low stock export for the same user and run while one is pending answers 409 regardless of split.
- AC-15b (R4) `GET /scm/order-summary/low-stock-preview?run_id=<id>` answers `{rows, sheet_counts: {supplier, category, supplier_category}}` where `rows` = the visible row count (the "All" count) and each sheet count = the number of GROUPS the workbook would write under that split, keyed exactly as the workbook keys them (none-buckets included, pairs only when present); behind `scm.dashboard.view`; 404 on a malformed or invisible run; `run_id` omitted = newest completed run. Declared on `LowStockPreviewOut` and asserted by name through the route.

## Frontend

- AC-16 Actions > "Low stock report Excel" opens the split dialog instead of starting the export; the dialog offers None / Supplier / Category / Supplier x Category, None selected by default.
- AC-16b (R4) On open the dialog fetches the preview once (`getLowStockPreview(runId)`) and shows "N rows, M sheets": M = 2 under None, `sheet_counts[split] * 2` otherwise, re-computed locally when the radio changes (no second fetch). While loading the line reads "..."; on a failed preview the line is hidden and Export stays enabled (the preview is a courtesy, not a gate).
- AC-17 Export in the dialog calls `exportLowStockReport(runId, split)` with the chosen value, the request body is `{run_id, format: 'low_stock_xlsx', split}`, My Downloads queries invalidate, the existing toast fires, the dialog closes.
- AC-18 A refused export (422 / 409) toasts the extracted message, the dialog stays open, nothing else changes.
- AC-19 The dialog's Export button and the Actions item disable while ANY of the four exports is pending (the shared flag, unchanged).
- AC-20 `StockDebtExportPopover` renders the same four options from the shared `EXPORT_SPLIT_OPTIONS`; its existing tests stay green.
- AC-21 Usable at 375px and 1280px; no UUID and no feature explanation rendered.

## Browser pass (agent-browser, via sidebar)

- AC-E2E-1 Procurement > Supply Chain > Reorder Planning > open a plan > Actions > Low stock report Excel > choose Supplier > Export: toast, My Downloads shows the row pending then ready, the file opens with `"<supplier> - Low"` / `"<supplier>"` pairs.

## Test list

Backend (`tests/scm/test_workbook_split.py`, `tests/scm/test_low_stock_report.py`, `tests/scm/test_order_summary_export.py` or where the route tests live):

1. `test_split_rows_supplier_none_bucket_and_sort` (AC-1)
2. `test_split_rows_category_and_pairs_only_present` (AC-1)
3. `test_sanitize_and_unique_titles_with_limit` (AC-1b)
4. Stock Debt AC-13..AC-16 existing tests (AC-2, no new test)
5. `test_low_stock_split_none_is_unchanged` (AC-3, assert the two titles and column count)
6. `test_low_stock_split_category_pairs_low_then_all` (AC-4)
7. `test_low_stock_split_category_empty_low_sheet_is_header_only` (AC-4 / A3)
8. `test_low_stock_split_supplier_keys_on_frozen_supplier_name` (AC-5)
9. `test_low_stock_split_supplier_category_title_cut_and_collision` (AC-6)
10. `test_low_stock_split_supplier_refused_without_supplier_column` (AC-8)
11. `test_low_stock_split_category_allowed_without_supplier_column` (AC-8)
12. `test_low_stock_cap_applies_under_split` (AC-9)
13. `test_export_route_forwards_split_to_task` (AC-11)
14. `test_export_route_rejects_unknown_split` (AC-12)
15. `test_export_route_rejects_split_on_other_formats` (AC-13)
16. `test_generate_low_stock_report_forwards_split` (AC-14)
16b. `test_low_stock_preview_counts_match_the_workbook` (AC-15b: same run, the preview's group counts equal the sheet count / 2 of each split's workbook; rows = visible count)
16c. `test_low_stock_preview_route_404_on_invisible_run_and_fields_declared` (AC-15b)

Frontend (vitest):

17. `ReorderPlanView.lowStock.test.tsx`: item opens the dialog; Export with Supplier calls the service with `'supplier'`; refused export keeps the dialog open; pending disables (AC-16..AC-19; the existing AC-2 test is rewritten to go through the dialog)
18. `summaryOrderService.test.ts` (or the existing service spec): body carries `split` (AC-17)
19. `LowStockExportDialog.test.tsx`: default None, radio changes, preview line "N rows, M sheets" doubles the group count and reads 2 under None, "..." while loading, hidden on error with Export enabled (AC-16, AC-16b)
20. `summaryOrderService.test.ts`: `previewLowStockExport` (none -> 2 sheets; supplier -> supplier x 2) and `getLowStockPreview` GET shape (AC-16b)
