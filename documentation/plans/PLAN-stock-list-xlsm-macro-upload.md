# PLAN: Stock List `.xlsm` (macro) upload support

**Date:** 2026-06-04
**Status:** ✅ Implemented + verified (2026-06-04). Migration 223 applied; BE pipeline live in `excel_macro_stripper.extract_macro_template_xlsx` + both attachment endpoints; FE rule in `lib/excel-utils.resolveImportSheetName`. Verified end-to-end via Playwright MCP with the real macro file (upload → 6591 rows imported, attachment stored/downloaded as Template-only `.xlsx`, no VBA). Tests: 24 pytest + 8 vitest green; e2e spec `e2e/stock-list-xlsm-upload.spec.ts` + committed fixture. Code review: global xlsm Template rule for all TemplateUploadDialog users (Orders/Warehouses included) confirmed intentional; minor cleanups noted (duplicate Stock List type query in create_attachment, 3× filename sanitization) - not blocking.
**Sample file:** `stock balance - Macro Version.xlsm` (real data, Google Drive `…/4. Stock Balance Update for AI System/`) - 3 sheets: `Active Loc` (60×2), `Master` (11,206×10), `Template` (6,592×4: Item Code / Item Description / Location / On Hand Qty). Template sheet is pure values - zero formulas, zero defined names.

## Problem

Dealers send a macro-enabled stock workbook. We need to accept the `.xlsm` on the stock page, update stock balances from its **Template** sheet, and store a clean macro-free **`.xlsx` containing only the Template sheet** as the "Stock List" attachment (the chatbot/n8n consumes this; we can't send macro files to the chatbot).

## Root causes (why the earlier attempt "didn't work")

1. **DB:** `attachment_types.allowed_extensions` for `Stock_List` is `xls,xlsx` - no `xlsm`. Frontend `validateFile` rejects macro files before upload starts.
2. **FE:** shared `components/template/TemplateUploadDialog.tsx` parses **first sheet only** (`workbook.SheetNames[0]`). Macro file's first sheet is `Active Loc` → garbage rows passed to bulk import.
3. **BE:** `app/services/excel_macro_stripper.py` (`maybe_strip_upload(keep_data_sheet=True, data_sheet_candidates=…)`) was built for exactly this but is **never called** from any attachment endpoint - only wired into orders/SPO/GRN imports. Raw `.xlsm` reaches S3/R2 and the n8n webhook.

Already working (no change needed): backend bulk-import header mapping in `app/services/inventory_service.py:971-1024` natively supports `Item Code`, `Item Description`, `Location`, `On Hand Qty`.

## Agreed design decisions

| # | Decision | Answer |
|---|---|---|
| 1 | Pipeline trigger | **`.xlsm` only.** `.xls` / `.xlsx` flow stays exactly as today (no sheet pruning, no rewrite). |
| 2 | Pipeline scope | All paths where resolved attachment type is Stock List: `POST /api/v1/resource-management/attachments/replace-latest-stock-list`, generic `POST /api/v1/resource-management/attachments/` (incl. `on_conflict=replace`), and any replace/resubmit flow. |
| 3 | xlsm processing | Strip VBA → keep **only** the `Template` sheet → **bake formulas to values** (`data_only=True`; guards future cross-sheet formulas from becoming `#REF!`) → save as `.xlsx`. `original_filename`, `stored_filename`, `mime_type` all become `.xlsx` (download extension must match content). Kept sheet keeps its name `Template`. |
| 4 | xlsm without "Template" sheet | Single sheet → keep that sheet. Multi-sheet without `Template` (case-insensitive) → **reject 422** "Workbook must contain a Template sheet". **No first-sheet fallback** - sample proves first sheet can be wrong data. |
| 5 | FE sheet selection | Built into shared `TemplateUploadDialog` (not prop-driven): if file is `.xlsm` → parse `Template` sheet if present; single sheet → use it; multi-sheet without Template → show error (mirrors BE 422). `.xlsx`/`.xls` → first sheet, unchanged. |
| 6 | Allow xlsm | Idempotent alembic migration: append `xlsm` to `allowed_extensions` where `type_name IN ('Stock List','Stock_List')` and not already present. |
| 7 | n8n | No webhook assertion needed for stock list (webhook still fires as today; payload naturally carries converted `.xlsx`). |
| 8 | Verification | Playwright MCP interactive: sidebar → Inventory Management → Stock → **Import** with the real `.xlsm` → stock rows update via bulk import → **Stock List** button (links to `/resource-management/attachments/{id}`) → download → assert `.xlsx`, Template-only, values intact. Both upload AND download must be exercised. |
| 9 | Regression | Real `.xlsm` committed to `sorento_crm_frontend/e2e/fixtures/` + persisted Playwright spec (upload + download). Per memory rule: AI/file features use real fixtures. |

## Key flow (stock page Import)

`TemplateUploadDialog` → `handleUploadTemplate(data, _, file)` in `StockBalanceGrid.tsx:135` does TWO things:
1. `bulkImportStock(data)` - rows parsed client-side (SheetJS) → `POST /api/v1/inventory/stock/bulk-import` (queued job).
2. `replaceLatestStockList(file)` - raw file → `POST …/replace-latest-stock-list` → becomes the Stock List attachment.

Both legs must handle xlsm: leg 1 via FE sheet rule (decision 5), leg 2 via BE strip pipeline (decision 3).

## Implementation order

1. **Migration** - idempotent `UPDATE attachment_types` adding `xlsm` (decision 6).
2. **BE stripper** - extend `excel_macro_stripper.py`: add value-baking (`data_only=True`) mode + strict Template resolution (no first-sheet fallback on multi-sheet; raise → 422). Do NOT change behavior for existing callers (orders.py, spo_allocations.py, grn.py).
3. **BE wiring** - call pipeline in `attachments.py` wherever attachment type resolves to Stock List (`STOCK_LIST_TYPE_NAMES = ("Stock List", "Stock_List")`, attachments.py:233).
4. **FE** - `TemplateUploadDialog.tsx` xlsm sheet rule (decision 5).
5. **Rebuild FE** (`npm run build && npm start` - no HMR), Playwright MCP verify per decision 8.
6. **Tests (Phase 2, not deferred)** - pytest: stripper xlsm rules + 422 + endpoint happy/auth/validation; vitest: dialog xlsm sheet pick; Playwright spec + committed fixture.
7. `/code-review`, then PR.
