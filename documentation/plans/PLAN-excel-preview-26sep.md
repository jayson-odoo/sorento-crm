# PLAN: In-app Excel preview, low stock report first

Status: draft for the owner's grill (26 Sep 2026). Planning lane only, no feature code. Track:
full (new read route, new email event, a shared viewer across about 12 sites; well over 300
lines). No migration, no new permission, no new ingest surface.
UAC: `excel-preview-26sep-acceptance-criteria.md` (same folder)
Mockup: `excel-preview-26sep-mockup.html` (same folder; open in a browser)
Classification: the low stock report page is part of the SCM module (`scm` router, its module
guard, `scm.dashboard.view`); `SpreadsheetViewer` is core UI (`components/common`), like
`PdfViewer`.
Parents: `scm/PLAN-low-stock-report.md` (the run-bounded workbook), `scm/PLAN-low-stock-export-
split-25sep.md` (#1236, the split). Sibling: #1256 (themed `PdfViewer`, open), whose toolbar and
lazy-loading pattern this plan copies.

## 1. Why

Owner, 26 Sep 2026: the daily low stock automation sends users a link; with a split by supplier
and category there are too many sheets to open blind, so the user must be able to view the report
in the system first and choose to export. And more widely: "enforce this for every Excel in our
system", because clicking an Excel in My Downloads saves it when they may only want to look.

Owner clarification, 01:40Z (binding): the link lands on a page that is the Excel preview of the
plan, NOT the reorder planning screen ("too confusing"); split by supplier / category, default
both; filter the suppliers and categories wanted; download that Excel.

## 2. Inventory: every place the system produces or offers an Excel

Measured on `origin/main` 46711c61. `BE` = `sorento_crm_backend/app`, `FE` =
`sorento_crm_frontend`. Every backend workbook is openpyxl; there is no xlsxwriter or pandas.

### A. Queued exports: a My Downloads row + an RQ task on `imports`, stored to S3/R2

All reach the user through My Downloads, so S3 (My Downloads preview) covers every one of them.

| Kind | Route (enqueue) | Task | Builder | FE trigger |
| --- | --- | --- | --- | --- |
| `low_stock_xlsx` | `POST /scm/order-summary/export` `format=low_stock_xlsx`, `BE/api/v1/scm/order_summary.py:117,139` | `BE/tasks/export_tasks.py:1092` | `BE/services/scm/low_stock_report_service.py:236` `export_low_stock` | `FE/app/(protected)/scm/reorder/components/ReorderPlanView.tsx:146-150` -> `LowStockExportDialog.tsx:31` |
| `order_sheet_xlsx` / `_pdf` | same route, `format=xlsx\|pdf` | `export_tasks.py:631` | `summary_order_service.py:1866` (`_render_export_xlsx` :1721) | `ReorderPlanView.tsx:132-157` |
| `oi_worksheet_xlsx` | same route, `format=oi_worksheet` | `export_tasks.py:724` | `OrderInquiryWorklistService.export_xlsx` | same menu |
| `quotation_xlsx` | `POST .../issues/{i}/export/xlsx`, `BE/api/v1/projects/quotation_documents.py:750` | `export_tasks.py:484` | `project_quotation_excel_service.py:602` | `QuotationDocumentClient.tsx:419,550` |
| `order_inquiry_worklist_xlsx` | `POST /project-sales/order-inquiries/export`, `projects/order_inquiries.py:569` | `export_tasks.py:1302` | worklist `export_xlsx` | `OrderInquiriesClient.tsx:1093` |
| `order_inquiry_xlsx` | `POST /project-sales/order-inquiries/{id}/export`, `:638` | `export_tasks.py:1219` | | `OrderInquiryDetail.tsx:764` |
| `stock_debt_xlsx` | `POST /project-sales/stock-debt/export`, `projects/stock_debt.py:168` | `export_tasks.py:1374` | `stock_debt_service.py:1391` (has `split`) | `StockDebtExportPopover.tsx:40` |
| `packing_list_xlsx` | `POST /scm/inbound-shipments/{id}/packing-list/export`, `scm/fulfilment.py:1170` | `export_tasks.py:102` | `consolidated_packing_list.py:547` | `packing-lists/[id]/layout.tsx:181` |
| `report_xlsx` | `POST /reports/{key}/export`, `reports/reports.py:216` | `tasks/report_export_tasks.py:32` | `services/reports/xlsx_renderer.py:410` | `components/reports/ReportPage.tsx:455,532` |
| CSV `chat_history_export` | `POST /system/chat-history/export`, `system/chat_history.py:110` | `export_tasks.py:536` | csv.writer | `system-management/chat-history/page.tsx:390` |

### B. Synchronous routes: bytes in the response, the browser saves them straight away

These are the sites S4 swaps to "preview first". Each already fetches a same-origin blob, so
the preview needs no new route.

| Route | Route file:line | Builder | FE trigger (saves via `saveBlobAs` or equivalent) |
| --- | --- | --- | --- |
| `GET /project-sales/projects/{p}/order-inquiry-export` | `projects/order_inquiries.py:1068` | `project_order_inquiry_service.py:10249` | `[projectId]/order-inquiries/components/OrderInquiryClient.tsx:381` |
| `GET /project-sales/amendments/{id}/autocount-change-list.xlsx` | `projects/sales_orders.py:936` | `project_so_delta_service.py:1042` | `revisions/components/AmendmentReviewClient.tsx:224` |
| `GET /scm/proforma-invoices/{id}/export` | `scm/proforma_invoices.py:368` | `proforma_invoice_service.py:2378` | `scm/proforma-invoices/[id]/components/ProformaInvoiceDetail.tsx:570` |
| `POST /scm/container-requests/document?format=xlsx` | `scm/container_requests.py:215` | `container_request_xlsx.py:100` | `scm/loading-plan/components/LoadingPlanView.tsx:366` |
| `GET /scm/inbound-shipments/{id}/spo-worksheet/export` | `scm/fulfilment.py:1420` | `spo_conversion_service.py:3673` | `packing-lists/components/SpoPlannerTable.tsx:1403` |
| `GET /scm/supplier-notices/{id}/document?kind=xlsx` (signed URL JSON) | `scm/fulfilment.py:778` | stored on `SupplierNotice` | `scm/loading-plan/components/SentRequestsPanel.tsx:87-90` |
| `GET /autocount/pulls/{job_id}/download.xlsx` | `integrations/autocount_pull.py:223` | `autocount_pull_service.py:549,631` | `AutocountPullReview.tsx:202` |
| API only, no screen: `GET .../issues/{i}/xlsx`, `GET /project-sales/order-inquiries/export`, `GET .../packing-list/export` | `quotation_documents.py:609`, `order_inquiries.py:500`, `fulfilment.py:1150` | | none (the screens use the queued versions in A) |
| CSV: divergence corrective import, SO import file, import-job rows | `projects/divergences.py:217`, `projects/sales_orders.py:764`, `system/jobs.py:278` | | `DivergenceReviewClient.tsx:127`, `SalesOrderDetailClient.tsx:426,693`, `ImportJobRowsCard.tsx:219` |

The supplier notice row fetches a signed bucket URL, which sends no CORS headers; its preview
reads bytes through a small same-origin byte route beside it (the `/downloads/{id}/file`
precedent). That is the only new route S4 needs.

### C. Built in the browser

| Site | Library | Notes |
| --- | --- | --- |
| DataGrid toolbar "Export" (`components/ui/data-grid-list-toolbar.tsx:359`, 107 lists pass `exportConfig`) and the all-records export (`components/list/ListQueryExportDialog.tsx:261` over `POST /list-query/export`) | SheetJS via `lib/excel-utils.ts:28` | The grid on screen already IS the preview. Recommended out of scope (grill Q6) |
| Stock balance (`inventory-management/stock/components/StockBalanceGrid.tsx:252-263`) | SheetJS | A grid export, same as above |
| AutoCount pull compare (`PullCompareTab.tsx:182`) | SheetJS | A grid export, same as above |
| Purchase request (`purchase-requests/lib/purchase-request-excel-export.ts:149,268,337,389`, called at `PurchaseRequestDetail.tsx:371-373`, `FormRevisionsTab.tsx:118`) | SheetJS | A detail-page document, not a grid: previewed in S4 |
| Stock inquiry (`stock-inquiries/utils/exportStockInquiryToExcel.ts:135`, called at `StockInquiryDetail.tsx:222`) | exceljs | Same: previewed in S4 |
| Product import template (`products/components/ProductsList.tsx:897-900`) | SheetJS | An empty template: no preview, stays a download |

### D. Delivered outside our UI

| Channel | Where | In scope? |
| --- | --- | --- |
| WhatsApp low stock report (chat route + late push) | `BE/api/v1/scm/low_stock_report.py:536`, `export_tasks.py:1003-1090` | No: the recipient is in WhatsApp, not in the CRM. The file also lands in the linked user's My Downloads, which S3 covers |
| Supplier container request email attachment | `supplier_notice_service.py:1596-1625` | No: the recipient is an external supplier |
| Chat attachments of stored files | `services/chatbot/engine.py:4200-4208` | No: same reason |

### E. My Downloads and the existing preview (what already works)

- `user_downloads` (`BE/models/download.py:26`); routes `GET /downloads` (:27),
  `GET /downloads/{id}/url` (:47, presigned 1 h), `GET /downloads/{id}/file` (:66, same-origin
  bytes, added for the preview). Retention 30 days (`download_service.py:250`).
- `FE/components/my-downloads/DownloadRow.tsx`: the row BODY runs `onDownload` (:87-97,
  `window.open` of the signed URL; title "Click to download", :133-149); a separate Eye icon runs
  `onPreview` (:104-119) into `AttachmentPreviewModal` (:197).
- `FE/components/common/AttachmentPreviewModal.tsx` ALREADY previews `.xlsx/.xls/.xlsm/.csv`:
  `ExcelSlide` (:544-715) fetches bytes, lazy-imports SheetJS, sheet tabs as buttons (:655-671),
  search with highlight, but shows only the first 200 rows and 40 columns (:511-527), a plain
  `<table>` whose header scrolls away, no virtualisation.

So My Downloads is a REPAIR, not a build (PRINCIPLES "check whether it exists"): the preview is
there but hidden behind an icon, the row click saves, and the preview is too thin to trust.

### F. The daily email: does not exist yet

The owner describes "an automation to send an email to specific users every day". The code has
none: the daily job `_handler_scm_reorder_run` (`BE/scheduler/task_scheduler.py:411-450`) creates
and funds a run and returns; no email event, template or outbox producer mentions low stock, and
no plan describes one. Either it lives outside this repo (an n8n flow) or it is the intent. Grill
Q1; this plan builds it in-system (S2) unless the owner says otherwise.

## 3. Decision: one viewer, two feeders

**A shared `SpreadsheetViewer` (`components/common/SpreadsheetViewer.tsx`, lazy like
`PdfViewer`) that renders a normalised workbook model `{sheets: [{title, columns?, rows}]}`.
Two things feed it:**

1. **A stored file** (My Downloads, attachments, the sync exports in 2B, the browser-built
   documents in 2C): the bytes are parsed in the browser with SheetJS, lazy-loaded. The file IS
   the truth, so parsing the file is the only preview that can never disagree with it.
2. **The low stock report**, which has no file yet when the user looks at it (the user is still
   choosing the split and filters): a JSON view route built by the SAME function that builds the
   workbook (section 4), so the view and the file cannot disagree either.

Why not a JSON rows route next to every export: 20 producers would each need a route, a schema
and tests, and each route would be a second rendering of the file that CAN drift from it. The
browser already has the bytes (or can fetch them same-origin) and already has a parser. Only the
low stock report needs a route, because only it previews something that is not a file yet.

Why SheetJS and not exceljs: SheetJS is already the preview's parser and already lazy-loaded
(`await import('xlsx')` in `ExcelSlide`). Measured from the npm tarball (0.18.5): the core build
is 437 KB minified / **141 KB gzip**; the mini build (xlsx + csv only) 251 KB / 79 KB gzip. It
lands in its own chunk on first preview, never in a page's initial chunk (the #1256 rule).
exceljs is heavier and Node-shaped; it stays for the one site that writes styled workbooks.

Large files:

- **Virtualised rows** via `@tanstack/react-virtual` 3.x (new dependency; about 12 KB gzip
  unminified for core + react, measured from the tarballs; the same TanStack family as the
  react-table the grid already uses; goes through `pick-ui-library` per DESIGN-LANGUAGE section 8).
  Only the rows in view are in the DOM, so a 50,000-row sheet scrolls like a 50-row one.
- **Only the open sheet is converted**, and the declared-range trap stays fixed: a sheet that
  claims 1,048,000 rows is scanned to the cap, not converted whole (`ExcelSlide`'s 18.8 s lesson,
  `AttachmentPreviewModal.tsx:511-527`). The display cap rises from 200 to 50,000 rows and 40 to
  60 columns; beyond it a footnote names the cut and Download is the way to the rest.
- **Size gate**: files over 25 MB are not parsed ("Too large to preview here" + Download). The
  largest queued export is capped at 5,000 rows (low stock, stock debt, OI worksheet), far below.
- Parsing stays on the main thread. Trigger for a Web Worker (named, not built): a real file
  whose open-sheet parse takes over 1 s on the owner's laptop.

Viewer look, matched to `PdfViewer` (#1256): one toolbar of ghost icon `Button`s
(`mode="icon" variant="ghost" size="sm"`), `text-xs tabular-nums text-muted-foreground` labels,
wrapping as whole groups at 375px; `fileActions` prop (Download + Open) off inside a chrome that
already has them; loading skeleton shaped like the grid; "This file could not be shown here" +
Download on a parse error. Grid styles copied from `DataGrid`: sticky header
(`sticky top-0 bg-background/90 backdrop-blur-xs`, `data-grid-table.tsx:207-214`), cell borders,
`--text-2sm`, numbers right-aligned tabular, first column pinned. Sheet tabs are
`TabsList variant="line"`, scrolling, never wrapping; over 12 sheets a "Go to sheet"
`SearchableSelect` sits beside them (a supplier x category low stock split can reach 100+ sheets).
No motion beyond the lightbox spring the modal already has.

Dependency note: SheetJS on npm is frozen at 0.18.5, which carries two published advisories
fixed upstream (prototype pollution on crafted files, fixed 0.19.3; ReDoS, fixed 0.20.2). The
preview ALREADY parses user-uploaded attachments with it today. S3 moves the dependency to the
vendor's current tarball (`https://cdn.sheetjs.com/xlsx-0.20.3/xlsx-0.20.3.tgz` in
`package.json`), the vendor's only distribution since 0.18.5. Grill Q7.

## 4. The low stock report page (S1)

### Backend

`low_stock_report_service.py` today builds rows inside `export_low_stock` (:236-345) and counts
groups again in `low_stock_preview` (:347). Refactor into ONE model builder the workbook renders:

```python
def build_low_stock_model(db, *, run_id, include_supplier=True, split="none",
                          suppliers=None, categories=None) -> dict:
    # {as_of, columns, rows: [tuple], sheets: [(title, [row index])],
    #  facets: {suppliers: [(key, rows, low)], categories: [...]},
    #  counts: {rows, low, sheets}, over_cap, filename}
```

- Filters apply to `frozen["all_rows"]` before the split, on the SAME key callables the split
  uses (`supplier_name or "No supplier"`, master `category_code or "No category"`). The "Low
  stock" sheet under `none` and every ` - Low` sheet are `_is_low` over the filtered rows.
- Facets are over the whole run (every choice stays visible), with row and low counts.
- `rows` are `_sheet_row(...)` output, each row once; sheets carry indexes. 5,000 rows x 16
  columns is about 1 MB of JSON before gzip.
- The cap moves from the run's visible count to the filtered count (AC-7): a filter can bring an
  oversized run under it. Over the cap the model carries counts and `over_cap`, no rows.
- `export_low_stock(...)` keeps its signature plus `suppliers`/`categories`, and becomes
  "build the model, write each sheet with `svc.write_sheet`". Its tuple return is unchanged, so
  the task, the chat route and the 18 existing tests are untouched.
- `low_stock_preview` and `GET /scm/order-summary/low-stock-preview` are deleted with the dialog
  (the page shows the same counts from the view).

Routes (`BE/api/v1/scm/order_summary.py`, beside the export):

- `GET /scm/order-summary/low-stock-view?run_id=&split=&supplier=&category=` -> `LowStockViewOut`
  (AC-1). `scm.dashboard.view`, JWT only like the export (the report carries supplier names).
  `split` defaults to `supplier_category` here (owner: "default both").
- `OrderSummaryExportIn` gains `suppliers: list[str] | None`, `categories: list[str] | None`;
  refused with 422 on any format but `low_stock_xlsx` (the R6 pattern of #1236); forwarded to
  `generate_low_stock_report(..., suppliers=, categories=)` and on to `export_low_stock`.

### Frontend

- `app/(protected)/scm/low-stock-report/[runId]/page.tsx` and `.../low-stock-report/page.tsx`
  (newest completed run). Sidebar item "Low stock report" under Procurement > Supply Chain, same
  `moduleKey` and permission as Reorder Planning (grill Q2).
- Layering: `LowStockReportView` -> `useLowStockView(runId, split, suppliers, categories)`
  (`placeholderData: keepPreviousData`, debounced 250 ms) -> `lowStockReportService.getView()` ->
  `apiFetch`. Mock branch under the existing `USE_SUMMARY_ORDER_MOCKS` for Phase 1.
- Toolbar per AC-11; body `SpreadsheetViewer workbook={toModel(view)} fileActions={false}`
  (the page's own Download is the action).
- Download: `useLowStockDownload` posts the export (split + filters), then watches that
  download row through the existing `GET /downloads?source_entity_type=reorder_run&
  source_entity_id=<run>` poll (`MyDownloadsContext.tsx:54` polls in-flight rows every 4 s; the page's own watch sets
  `refetchIntervalInBackground: true` per D27, so a hidden tab still sees the file land), and
  when ready fetches `/downloads/{id}/file` and saves the blob (no popup, so no blocker). Grill Q4.
- Reorder Planning's Actions > "Low stock report Excel" becomes a link to the page for that run;
  `LowStockExportDialog.tsx` is deleted (grill Q3). One surface, not two that can drift.

## 5. The daily email (S2)

- `EventDef("scm_low_stock_daily", "Daily low stock report", ...)` in
  `BE/services/email_event_registry.py` (seeded on startup: no migration; the admin switch comes
  free).
- Recipients: `low_stock_email_user_ids` on the reorder run scheduled task's `metadata`, edited in
  `ScheduledTaskForm.tsx` the way `company_ids` / `send_email` already are (:84-97). One list of
  users is one preference; it does not need a table. Trigger for a table: per-user schedules or
  per-recipient filters.
- `_handler_scm_reorder_run` (`task_scheduler.py:411`), after funding, calls
  `low_stock_email_service.send_daily(db, run_id, user_ids)`: one
  `email_outbox_service.enqueue(event_key="scm_low_stock_daily", ...)` per active user with an
  email; subject `Low stock report 26 Sep 2026: 42 low`; one link to
  `<FRONTEND_BASE_URL>/scm/low-stock-report/<run_id>`. Best effort: caught and logged, never
  fails the run (PRINCIPLES layering, post-commit side effects).
- The email carries a link, not the file (grill Q5): the owner's point is to look first.

## 6. My Downloads (S3)

- `DownloadRow.tsx`: for a ready `.xlsx/.xls/.xlsm/.csv/.pdf` row, the row body runs
  `onPreview` (today :133-149 run `onDownload`), title "Preview"; the Download icon runs
  `onDownload`; the separate Eye icon goes (the row IS the preview). Other kinds unchanged.
- `AttachmentPreviewModal`: `ExcelSlide` (:544-715) is replaced by
  `<SpreadsheetViewer loadData={...} fileActions={false} />`; the modal header keeps Download and
  Open. Search and highlight move into the viewer (existing tests move with them). PDFs use
  #1256's `PdfViewer` once it merges; this plan does not depend on it.
- `KIND_LABEL` gains the three missing kinds.

## 7. The remaining sources (S4)

- `hooks/useSpreadsheetPreview.tsx`: `open({ load: () => Promise<Blob>, fileName })` mounts one
  `AttachmentPreviewModal` with a single item whose bytes come from the blob; Download calls
  `saveBlobAs`, lifted from `app/(protected)/project-sales/_shared/services/fileDownload.ts:19`
  into `lib/` now that a second domain uses it. Each 2B site replaces its direct save with `open(...)`. The supplier notice site
  gets a same-origin byte route beside `GET /scm/supplier-notices/{id}/document` (JWT, same
  permission).
- The purchase request and stock inquiry builders return an `ArrayBuffer`
  (`XLSX.write(wb, {type: 'array'})` / `workbook.xlsx.writeBuffer()`) instead of writing the
  file, and open the same preview.
- Queued exports (2A) keep their toast; the preview is one click away in My Downloads.

## 8. Slices (thin, vertical, in order)

| Slice | What | Journey | Executors |
| --- | --- | --- | --- |
| S1 | Low stock report page: model builder + view route + filters on the export + page + `SpreadsheetViewer` (JSON feeder only) + Actions link, dialog removed | J-A 3-7 | Phase 1 coder (page vs mock) -> Phase 2 tester, coder -> reviewer + browser |
| S2 | Daily email: event, recipients in scheduled-task metadata, send after the run, form field | J-A 1-2 | tester -> coder (small) |
| S3 | SheetJS feeder (dependency bump), `ExcelSlide` -> `SpreadsheetViewer`, virtualisation, My Downloads row click = preview | J-B | Phase 1 -> 2 -> 3 |
| S4 | `useSpreadsheetPreview` + 7 sync sites + supplier notice byte route + 2 browser-built documents | J-C | coder, one site per commit |

One lane, one branch, one PR (lane merge discipline); S1 is the first commit set and can be
hand-tested alone. S2 depends on S1 (the link target). S3 depends on S1 only for the viewer
component. S4 depends on S3.

## 9. Risks

- **Many sheets.** A supplier x category split on a 1,500-product run can pass 100 sheets. The
  "Go to sheet" search and the filters are the answer; the tab strip alone is not.
- **View payload.** 5,000 rows x 16 columns per refetch; rows travel once, gzip on the response,
  and a debounce keeps a burst of filter clicks to one request.
- **Auto-save after async.** A save that fires seconds after the click is a blob-anchor save, not
  `window.open`, so popup blockers do not apply; Chrome may still ask once about "multiple
  downloads" if the user downloads twice quickly. Acceptable.
- **The SheetJS source change** (tarball URL) needs `npm install --force` in CI and Docker as
  today; verify the lockfile integrity line lands.
- **#1256 overlap**: both edit `AttachmentPreviewModal.tsx`; S3 lands after #1256 or merges it in.

## 10. Out of scope

- DataGrid toolbar and list-query exports (the grid is the preview), unless grill Q6 says no.
- WhatsApp and supplier email deliveries (not in our UI).
- CSV routes stay downloads in S4 except where a screen already offers them (the viewer reads CSV
  for free once it exists; wiring the three CSV sites is a one-line follow-up per site).
- Editing cells in the preview.

## 11. Grill questions for the owner

Posted on the PR as one comment. Each has a recommendation; silence means the recommendation
stands.

1. **The daily email does not exist in the code.** Is it an n8n flow today, or the intent?
   Recommend: build it in-system (S2), sent right after the daily reorder run, one link, no
   attachment.
2. **Where do people find the page besides the email?** Recommend: a "Low stock report" sidebar
   item under Procurement > Supply Chain (opens the newest run), same permission as Reorder
   Planning.
3. **Reorder Planning's Actions > Low stock report Excel**: keep the split dialog, or send the
   user to the new page for that run? Recommend: send them to the page and delete the dialog, so
   there is one way to pick a split and it always shows what you get.
4. **Download on the page**: the file is built on the worker (a few seconds). Recommend: the
   button shows "Preparing..." and the file saves itself when ready, and it also lands in My
   Downloads. Alternative: build it inside the request and save at once (simpler, but breaks the
   "one route, one task" rule from #1236 and ties up the API for a large run).
5. **Email recipients**: who picks them? Recommend: an admin, on the daily reorder run in
   System > Scheduled Tasks, as a list of users. Everyone on the list gets the same link.
6. **"Every Excel"**: include the DataGrid "Export" buttons on the 107 lists? Recommend: no, the
   grid on screen is already the preview of what those export. Every other Excel (queued, sync,
   the purchase request and stock inquiry documents) gets the preview.
7. **SheetJS upgrade**: the npm package is frozen at 0.18.5, which has two published advisories
   and already parses uploaded files in the preview today. Recommend: take the vendor's 0.20.3
   tarball in S3.
8. **Over-cap runs**: today a run over 5,000 rows cannot be exported at all. Recommend: the cap
   counts the filtered rows, so choosing suppliers or categories makes a big run exportable; the
   page says the run is too large until the user narrows it.
