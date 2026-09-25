# PLAN: Low stock report - split the workbook by supplier / category, the Stock Debt way

Status: in progress, Phase 3 reviews clean, DRAFT PR #1236 (25 Sep 2026); browser pass + owner hand test owed (stack slot). Owner ruled O1-O3 in the lavish round, 25 Sep. Track: feature (three-phase). Lane branch: `feat/low-stock-export-split`, worktree `sorento_crm-low-stock-split`.
UAC: `low-stock-export-split-25sep-acceptance-criteria.md`
Domain: scm (Reorder Planning, `/scm/reorder/<id>`, Actions > "Low stock report Excel")
Parent: `PLAN-low-stock-report.md` (S3 the workbook, S4 the menu item), `PLAN-low-stock-last-in-and-list-scope.md` (S2 "All" = the plan list). Second case of `PLAN-stock-debt-filters-totals-export-24sep.md` R5 / A7 ("the low stock report is the named second case; lift the split then").

## Why

Owner, 24 Sep 2026 (Stock Debt lavish round): "the same asks (split by supplier / product type
on export) are coming for the low stock report". Owner, 25 Sep 2026: "let's apply the same
splitting mechanism to low stock report in reorder planning". The buyer walks the low stock
workbook supplier by supplier, exactly as the Stock Debt buyer does, and the client's own
`Stock Balance 28 Aug 2026.xls` was already filed one category per pair of sheets.

This is the trigger the Stock Debt plan named. The split and the sheet-title rules get
lifted out of `stock_debt_service` into one shared module now that two workbooks pay for it.

## Measured facts (`origin/main` c9a220777, 25 Sep 2026)

| fact | where |
| --- | --- |
| Low stock workbook = ONE run, TWO sheets, "Low stock" then "All", sixteen columns; rows sorted `(category_code, product_code)`; "All" = the plan list's visible rows (hidden rows dropped via `svc.visible_rows`); cap `MAX_LOW_STOCK_ROWS = 5000` on "All" | `low_stock_report_service.py:1-60, 145-330` |
| Category comes from MASTER DATA at export time (`_master_map` -> `category_code`), supplier from the FROZEN row (`row["supplier_name"]`) | `low_stock_report_service._master_map`, `_sheet_row` |
| `export_low_stock(db, run_id=, include_supplier=)` returns `(bytes, content_type, filename, {"low": n, "all": m})`; `include_supplier=False` DROPS the Supplier column (chat route, contact without the reveal key) | `low_stock_report_service.py:232-290` |
| Route: `POST /api/v1/scm/order-summary/export` body `{run_id, format}`; `format=low_stock_xlsx` -> guard on `MAX_LOW_STOCK_ROWS`, one in-flight per user/run/kind (409), `user_downloads` row `kind=low_stock_xlsx`, enqueue `generate_low_stock_report(download_id, run_id, user_id)` on `imports`. Gated `require_permission("scm.dashboard.view")` (JWT only) | `api/v1/scm/order_summary.py:61-300` |
| Task `generate_low_stock_report(download_id, run_id, user_id, *, include_supplier=True)` adopts the run's company, calls `export_low_stock`, stores at `exports/low-stock/<id>/<filename>`, `mark_ready(row_count_low, row_count_all)`, `_record_failure` on any exception | `tasks/export_tasks.py:962-1060` |
| The chat route also calls `export_low_stock` (via the same task, `include_supplier` per reveal key); it never chooses a split | `api/v1/scm/low_stock_report.py:470-500` |
| Stock Debt split: `split in none/supplier/category/supplier_category`; rows grouped by `supplier_name or "No supplier"` / `category_code or "No category"` / `"<supplier> - <category>"`; groups sorted by SANITISED title, case-insensitive; `_sanitize_sheet_title` strips `[]:*?/\`, cuts to 31, never empty; `_unique_sheet_title` adds ` (2)` on collision; one `write_sheet` per group | `stock_debt_service.py:98-133, 1419-1515` |
| Stock Debt's preview counts (`sheet_counts`) ride on the LIST envelope because that list is server-paginated; the FE preview is `previewStockDebtExport(envelope, split)`, no request of its own | `stock_debt_service._sheet_counts`, `stockDebtService.ts:294` |
| Stock Debt FE: `StockDebtExportPopover` = RadioGroup (None / Supplier / Category / Supplier x Category) + "N rows, M sheets" line + Export button; `useExportStockDebt` mutation | `project-sales/stock-debt/components/StockDebtExportPopover.tsx` |
| Reorder plan FE: the low stock export is ONE item in the grid's Actions menu (`ToolbarAction`, `onClick: () => exportLowStock.mutate()`), sharing a pending flag with the other three exports; "Reset planning" in the same menu already opens a dialog (`setResetOpen(true)`) before acting | `scm/reorder/components/ReorderPlanView.tsx:99-176` |
| `exportLowStockReport(runId)` posts `{run_id, format: 'low_stock_xlsx'}`; `useExportLowStockReport(runId)` invalidates My Downloads and toasts | `summaryOrderService.ts:265`, `useSummaryOrder.ts:69` |
| The FE plan row carries `supplier_name` but NO category (`OrderSummaryRow`, `summaryOrder.types.ts:42-160`); the report is fetched whole and paginated client-side | `summaryOrder.types.ts`, `order_summary.py:get_order_summary` |
| Existing tests: `tests/scm/test_low_stock_report.py` (18 tests, two-sheet shape, membership, sort, master data, cap, task, include_supplier), `tests/scm/test_stock_debt_routes.py` (export split AC-13..AC-16), `ReorderPlanView.lowStock.test.tsx` (AC-1/AC-2 menu item + service call) | listed |

## Rulings (owner)

- R1 (from the parent, standing) The low stock export stays on the SAME route, task, kind, cap and in-flight guard. `split` is one more body field; no new endpoint.
- R2 (owner, 25 Sep, O1) Under a split, EVERY group keeps the client's own pair: `"<key> - Low"` then `"<key>"`, Low first, groups in title order. `split=none` is unchanged: "Low stock", "All".
- R3 (owner, 25 Sep, O2) The split picker is a small dialog opened from the Actions menu item (the "Reset planning" pattern), not a fourth menu item per split.
- R4 (owner, 25 Sep, O3) The dialog shows rows AND sheets, like Stock Debt. Captain's reading of the ruling: the plan page never loads the frozen report (it reads `usePlanLines`, a different row set with no category), so a `category_code` on the report row would not reach the dialog; the direct route is one small read on dialog open, `GET /scm/order-summary/low-stock-preview?run_id=`, computed off the SAME `_split()` the workbook is built from, so the counts are the workbook's own. Sheets shown = groups x 2 (R2), 2 under `none`.
- R5 A split by supplier is refused when the Supplier column is withheld (`include_supplier=False`): the sheet titles would leak the names the column hides. 422 in `export_low_stock`; the chat path never sends a split so it is unaffected.
- R6 `split` on any format other than `low_stock_xlsx` is refused with 422, not ignored.

## Assumptions stated, not ruled

- A1 The split KEYS are the workbook's own cells: supplier = the frozen row's `supplier_name` (the Supplier column), category = master data `category_code` (the Category column). "No supplier" / "No category" buckets for blanks, as Stock Debt.
- A2 Within a group, rows keep the existing `(category_code, product_code)` order; the Low sheet is the same subset rule (`_is_low`) applied to the group's rows.
- A3 A group with no low rows still gets its ` - Low` sheet (header only). Every group is a pair; an empty Low sheet says "nothing low here" where the buyer looks for it.
- A4 The 31-char sheet-title limit: the base title is cut to 25 so ` - Low` fits; both sheets of a pair share the base, so a collision suffix ` (2)` lands on both.
- A5 The cap stays on the total "All" row count (5,000). No cap on the number of sheets; `supplier_category` on a 1,500-product run measured 14 suppliers on Stock Debt and will be in the same order of magnitude here.
- A6 The in-flight 409 stays per `kind`; two low stock exports of different splits for the same run cannot run at once. Nobody asked for that.
- A7 Sanitised-title sort, case-insensitive, is lifted as-is (the reviewer-ruled behaviour on Stock Debt).

## Open (owner, one line each)

- none. O1 -> R2, O2 -> R3, O3 -> R4 (lavish round, 25 Sep 2026).

## Design

### Backend

`app/services/scm/workbook_split.py` (new, lifted from `stock_debt_service`):

- `SPLIT_VALUES = ("none", "supplier", "category", "supplier_category")`.
- `sanitize_sheet_title(raw, *, limit=31)`, `unique_sheet_title(raw, used, *, limit=31)`: the two Stock Debt helpers, unchanged in behaviour, `limit` added for the ` - Low` suffix (A4).
- `split_rows(rows, split, *, supplier, category) -> list[tuple[str, list]]`: `supplier`/`category` are callables `row -> str | None`; returns `(key, rows)` pairs, none-buckets applied, sorted by sanitised key case-insensitive. `split == "none"` is the caller's own business (each workbook has its own fixed titles).
- `app/schemas/export_split.py`: `ExportSplit = Literal[...]`, imported by both `stock_debt.py` and `scm_order_summary.py`.

`stock_debt_service._render_workbook` calls `split_rows` and `unique_sheet_title`; its module-level helpers are deleted. Existing Stock Debt export tests must stay green unchanged (the lift is behaviour-preserving).

`low_stock_report_service.export_low_stock(db, *, run_id, include_supplier=True, split="none")`:

- `split` not in `SPLIT_VALUES` -> 422. `split in ("supplier", "supplier_category")` with `include_supplier=False` -> 422 "Split by supplier is not available without the Supplier column" (R5).
- `split == "none"`: today's two sheets, byte-for-byte the same path.
- Otherwise: `split_rows(all_rows, split, supplier=lambda r: r.get("supplier_name"), category=lambda r: master[r["product_code"]]["category_code"])`; for each `(key, group)`: `base = unique_sheet_title(key, used, limit=25)`; sheet `f"{base} - Low"` with `[r for r in group if _is_low(r)]`, then sheet `base` with `group`. Same `write_sheet`, same columns, same `_sheet_row`.
- Return tuple unchanged; the counts dict gains `"sheets"` (logged by the task, not stamped).
- `low_stock_preview(db, run_id) -> {"rows": n, "sheet_counts": {"supplier", "category", "supplier_category"}}`: `_split()` once, then distinct keys over `all_rows` with the SAME key callables the workbook uses (none-buckets included, pairs only when present). Group counts, not sheet counts: the FE doubles them (R2).

Route `GET /scm/order-summary/low-stock-preview?run_id=` (`_VIEW`, API key allowed - a read): `run_id` optional (newest completed run, as the report), validated + `assert_run_visible` like the export; returns `LowStockPreviewOut {rows, sheet_counts}`. Called once per dialog open, never on page load.

Route `export_order_summary`: `OrderSummaryExportIn.split: ExportSplit = "none"`; `split != "none"` with any other format -> 422 (R6); forwarded as `split=` kwarg to `enqueue_job(generate_low_stock_report, ...)`. Task signature gains `split: str = "none"`, passed through to `export_low_stock`.

### Frontend

- `components/common/export-split.ts` (new): `ExportSplit` type and `EXPORT_SPLIT_OPTIONS` (the four labels), imported by `StockDebtExportPopover` (drop its local copy) and the new dialog.
- `scm/reorder/components/LowStockExportDialog.tsx` (new): `Dialog` with a RadioGroup over `EXPORT_SPLIT_OPTIONS`, a one-line "N rows, M sheets" from `useLowStockPreview(runId, open)` (fetched when the dialog opens; "..." while loading; the line hides on error, Export stays enabled), Export button disabled while pending. Same radio markup as the popover. Sheets = `none` -> 2, else `sheet_counts[split] * 2` (R2), computed in `previewLowStockExport(preview, split)` in the service, the twin of `previewStockDebtExport`.
- `getLowStockPreview(runId)` in `summaryOrderService` with a mock branch under the existing `USE_SUMMARY_ORDER_MOCKS` flag (Phase 1).
- `ReorderPlanView`: the "Low stock report Excel" item opens the dialog (`setLowStockOpen(true)`), the dialog's Export calls `exportLowStock.mutate(split)` and closes on success. The shared pending flag is unchanged.
- `exportLowStockReport(runId, split)` posts `{run_id, format: 'low_stock_xlsx', split}`; `useExportLowStockReport` takes `split` as the mutation variable.

### Phase order

1. Phase 1 (FE): dialog + wiring + service body + preview hook against the mock. No backend. The export call is real (no mock branch exists for exports, by the parent's ruling); the backend ignores the unknown field until Phase 2, which is fine for a mock pass.
2. Phase 2 (tester first, then coder): `workbook_split.py` + tests, the lift in `stock_debt_service`, `export_low_stock` split, route + task plumbing, the preview read. Test list in the UAC.
3. Phase 3: reviewer + security-reviewer (R5 is the one new exposure; the route's permission and JWT-only gate are untouched) + browser pass via sidebar: Procurement > Supply Chain > Reorder Planning > a plan > Actions > Low stock report Excel > Supplier > Export > My Downloads.

## Out of scope

- Cell selection on the reorder plan grid (the other named second case; still not triggered).
- A per-split in-flight guard (A6).
- Changing the chat route's report (no split there).
