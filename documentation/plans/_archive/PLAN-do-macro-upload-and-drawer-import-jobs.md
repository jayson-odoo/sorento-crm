# PLAN: DO macro uploads (.xlsm) + import jobs in upload drawer

**Date:** 2026-06-04
**Status:** ✅ Implemented + verified (2026-06-04). Browser-verified with real macro files: tracking xlsm imported (8,661 rows, 16 skipped, drawer session "Finished"); lines xlsm with empty Template → 422 toast "The 'Template' sheet has no data rows. Run the macro to populate it…"; populated-Template synthetic xlsm → queued + drawer session. Inline status bars removed from all 7 pages (`LatestImportStatusPanel` deleted); drawer auto-opens on import queue and renders import_job sessions with row counts + link to job detail. Tracking dialog accept widened to settings default (`.xlsx,.xls,.xlsm`). Bonus fix landed earlier same day: import-job progress race (job_id pre-assigned at enqueue across 9 endpoints). Tests: 29 pytest (stripper + upload-activity) + 66 vitest green. Review findings: jobs query bounded (×2 over-fetch); needs_action stays failed-only for import jobs (partial visible via badge, rows not expandable) - accepted.
**Sample files (real data, Google Drive `…/AI Guideline - Copy/`):**
- `1. Delivery Tracking Update for AI System/Order Tracking - Macro Version.xlsm` - sheets: Raw Data, Master (5,501×9), hidden Sheet1, Daily Tracking, **Overall Tracking** (3,163×15, active)
- `2. Details Line Listing Delivery Update for AI System/Order Listing - Macro Version.xlsm` - sheets: **Master** (active, DO headers, wrong for lines), **Template** (lines headers, EMPTY), Transaction Log (28k rows, real line data)

## Findings (verified by running real files through current importers)

1. **DO tracking import already supports the macro file.** `OrderService.import_excel_tracking` looks up sheets BY NAME ("Master" + "Overall Tracking") - both exist in the xlsm; `maybe_strip` already wired in `orders.py:829`. Validation: `valid=True`, 5,498 master + 3,163 tracking rows, would_update 8,644. **No code change.**
2. **DO lines import broken for the macro file.** `process_delivery_order_detail_import` / `validate_delivery_order_detail_excel` read `workbook.active` → 'Master' sheet → 244 "Missing item code/location" errors. Line data lives in 'Transaction Log'; 'Template' has the right headers but zero rows (macro must populate it).
3. **Upload drawer shows only attachment sessions.** Pure import jobs (stock/GRN/DO/products/warehouses/SPO) surface via `LatestImportStatusPanel` inline bar on 7 pages - user wants that bar gone, drawer instead.

## Decisions

| # | Decision | Answer |
|---|---|---|
| 1 | DO lines xlsm sheet rule | **Template sheet, strict.** `.xlsm` → strip VBA + keep Template only (reuse `extract_macro_template_xlsx`); 422 if Template missing (multi-sheet); **422 if Template sheet has no data rows** ("run the macro to populate Template before uploading"). `.xlsx`/`.xls` unchanged (active sheet). |
| 2 | DO tracking | No change - named-sheet lookup + existing `maybe_strip` already handle xlsm. |
| 3 | Status bar replacement | **All 7 pages** (DO×2, Stock, GRN×2, Products, Warehouses, SPO). Remove `LatestImportStatusPanel` usage; import jobs become drawer sessions. |
| 4 | Drawer session model | New `session_type: "import_job"`; BE feed pulls user's `import_jobs` (job_type ≠ `attachment_bulk_import`, window-limited), maps status pending/queued/started→processing, finished→finished (failed_rows>0 → partial), failed→failed; carries processed/total/successful/failed counts + job link. |
| 5 | Drawer UX | Session row: filename (or job-type label), status badge, "X/Y rows" subtitle, click → `/system-management/import-jobs/{id}`. Pages queueing an import open the drawer (same auto-open the attachment flow uses). |

## Implementation order

1. BE: `extract_macro_template_xlsx(require_data=...)` empty-sheet guard; wire into `orders.py` import-order-lines (replace `maybe_strip` for xlsm); pytest.
2. BE: upload-activity feed `import_job` sessions + schema fields; pytest.
3. FE: drawer renders import_job sessions; remove `LatestImportStatusPanel` from 7 pages; open drawer on import queue; vitest.
4. Rebuild FE; Playwright MCP verify: DO page tracking upload (real xlsm, expect queued + drawer progress), DO lines upload (real xlsm, expect Template-empty 422 toast), bar gone from pages.
5. `/code-review`; update this status line.
