# PLAN: In-app Excel preview, low stock report first

Status: grilled, owner answers folded in (26 Sep 2026, section 0). S1 built on branch
`claude/low-stock-report-preview-s1-co31pg`, in review (evidence: `evidence/excel-preview-s1/`);
S2 and S3 not started. Track: full (new read route, a new automation trigger, a shared
viewer across about 12 sites; well over 300 lines). No migration, no new permission, no new
ingest surface.
UAC: `excel-preview-26sep-acceptance-criteria.md` (same folder)
Mockup: `excel-preview-26sep-mockup.html` (same folder; open in a browser)
Classification: the low stock report page is part of the SCM module (`scm` router, its module
guard; the page and its view route on `scm.reorder.run`, Download's export on
`scm.dashboard.view`); `SpreadsheetViewer` is core UI (`components/common`), like
`PdfViewer`.
Parents: `scm/PLAN-low-stock-report.md` (the run-bounded workbook), `scm/PLAN-low-stock-export-
split-25sep.md` (#1236, the split). Sibling: #1256 (themed `PdfViewer`, open), whose toolbar and
lazy-loading pattern this plan copies.

## 0. Owner rulings 26 Sep

The owner answered the grill on #1261 (comment of 26 Sep 05:28Z). Each answer is binding and is
folded into the section it changes; the dated line here is the record.

- **Owner ruling 26 Sep, Q1 (the email):** "it is a scheduled task in our system that uses the
  automation". The email is sent by the automation engine, which the `automation_runner`
  scheduled task drives; the plan does not build a second email path. The link in that email
  must open the new page. Section 2F is corrected and section 5 rewritten.
- **Owner ruling 26 Sep, Q2 (finding the page):** ok. A "Low stock report" sidebar item under
  Procurement > Supply Chain opens the newest run, same permission as Reorder Planning.
- **Owner ruling 26 Sep, Q3 (Reorder Planning's action):** ok. Actions > Low stock report Excel
  opens the new page for that run; the split dialog is deleted.
- **Owner ruling 26 Sep, Q4 (Download):** accepted. "Preparing..." while the worker builds the
  file, then it saves on its own, and it is also in My Downloads.
- **Owner ruling 26 Sep, Q5 (recipients):** "we can pick this in automation which is run by
  scheduled task". Recipients are the automation's own `recipient_config` (users, roles, extra
  emails), edited in System > Automations. No new recipient list on the scheduled task.
- **Owner ruling 26 Sep, Q6 (scope):** ok. DataGrid Export buttons stay as they are; every other
  Excel gets the preview.
- **Owner ruling 26 Sep, Q7 (SheetJS):** yes, move to the vendor's 0.20.3 tarball, "make sure no
  regression": every current SheetJS caller (the upload parsers included) is covered by a test
  that runs before and after the bump.
- **Owner ruling 26 Sep, Q8 (big runs):** ok, the cap counts rows after filtering, and "we must
  optimize performance and make the download reasonably as fast as possible": S1 measures the
  export on a 5,000-row run before and after and states both timings in its PR.

Slices re-ordered by the rulings (section 8): S1 is the standalone low stock report page and the
link the automation's email carries; S2 is the generic viewer, the SheetJS bump and My
Downloads; S3 is the remaining sources.

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

All reach the user through My Downloads, so S2 (My Downloads preview) covers every one of them.

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

These are the sites S3 swaps to "preview first". Each already fetches a same-origin blob, so
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
precedent). That is the only new route S3 needs.

### C. Built in the browser

| Site | Library | Notes |
| --- | --- | --- |
| DataGrid toolbar "Export" (`components/ui/data-grid-list-toolbar.tsx:359`, 107 lists pass `exportConfig`) and the all-records export (`components/list/ListQueryExportDialog.tsx:261` over `POST /list-query/export`) | SheetJS via `lib/excel-utils.ts:28` | The grid on screen already IS the preview. Recommended out of scope (grill Q6) |
| Stock balance (`inventory-management/stock/components/StockBalanceGrid.tsx:252-263`) | SheetJS | A grid export, same as above |
| AutoCount pull compare (`PullCompareTab.tsx:182`) | SheetJS | A grid export, same as above |
| Purchase request (`purchase-requests/lib/purchase-request-excel-export.ts:149,268,337,389`, called at `PurchaseRequestDetail.tsx:371-373`, `FormRevisionsTab.tsx:118`) | SheetJS | A detail-page document, not a grid: previewed in S3 |
| Stock inquiry (`stock-inquiries/utils/exportStockInquiryToExcel.ts:135`, called at `StockInquiryDetail.tsx:222`) | exceljs | Same: previewed in S3 |
| Product import template (`products/components/ProductsList.tsx:897-900`) | SheetJS | An empty template: no preview, stays a download |

### D. Delivered outside our UI

| Channel | Where | In scope? |
| --- | --- | --- |
| WhatsApp low stock report (chat route + late push) | `BE/api/v1/scm/low_stock_report.py:536`, `export_tasks.py:1003-1090` | No: the recipient is in WhatsApp, not in the CRM. The file also lands in the linked user's My Downloads, which S2 covers |
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

### F. The daily email: the automation engine (corrected, owner ruling 26 Sep, Q1)

The first draft said the email "does not exist in the code". That was the wrong question: the
owner's email is an **automation**, and automations are rows an admin configures in System >
Automations, run by a scheduled task. The machinery, measured on `origin/main` 46711c61:

| Piece | Where |
| --- | --- |
| The scheduled task that drives every automation | `automation_runner`, seeded by `alembic/versions/174_email_templates_and_automation.py:107`; handler `BE/scheduler/task_scheduler.py:335-337` (`_handler_automation_runner`), registered at `:577` |
| The engine | `BE/services/automation_service.py:317` `evaluate_due` (daily/scheduled rules, `next_run_at` from `run_time` + `timezone`, `:50-80`) and `:272` `dispatch_event` (event rules, fired from domain code) -> `_execute` `:426` |
| The rule | `automations` rows (`BE/models/automation.py:21`): `trigger_type`, `trigger_config`, `email_template_id`, `recipient_config`, `schedule_type` (`manual` or `daily`), `run_time` |
| Who receives it | `recipient_config` (`user_ids`, `role_ids`, `extra_emails`, `one_email`), resolved by `BE/services/automation_recipients.py:19` `resolve_recipients`; normalised at `automation_service.py:383` |
| The email body | the rule's `email_templates` row, rendered per match by `EmailTemplateService` with the trigger's context (`automation_service.py:614` `_send_per_match`), queued as `Notification` + `NotificationDelivery` (`:826` `_enqueue_email`) |
| The trigger registry | `BE/services/automation_triggers.py:62` `register`; 12 types today, `days_before_promotion_end` (:171) to `sponsorship_form_approved` (:656) |
| The daily reorder run | `BE/scheduler/task_scheduler.py:411-450` `_handler_scm_reorder_run`, registered at `:593` |

What the code does NOT hold: a trigger that knows about the reorder run or the low stock report.
None of the 12 registered types carries a run, its date, its low count or a link to it, and no
migration seeds a low stock rule (the seeded rules are the handover, undone, reserve and
sponsorship ones). So the rule the owner runs today is a row in the live database, built on a
trigger that cannot name the run, and its link (if any) is typed into the template by hand. This
repo cannot see or edit that row. What S1 adds is what the rule needs to link to the page: a
trigger `low_stock_report_ready`, fired when the daily run completes, whose context carries
`{{ report.link }}` (section 5). The admin points the existing rule at it and puts the link in
its template; recipients stay on the rule (Q5).

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
preview ALREADY parses user-uploaded attachments with it today. S2 moves the dependency to the
vendor's current tarball (`https://cdn.sheetjs.com/xlsx-0.20.3/xlsx-0.20.3.tgz` in
`package.json`), the vendor's only distribution since 0.18.5. Owner ruling 26 Sep, Q7: yes, with
no regression. Every current `xlsx` importer (the preview, `lib/excel-utils.ts`, the purchase
request export, the product / stock / GRN / price upload parsers; S2 lists them by file:line
before the bump) gets a vitest that parses or writes a real fixture workbook, run green on 0.18.5
first and again on 0.20.3.

## 4. The low stock report page (S1)

### Backend

`low_stock_report_service.py` today builds rows inside `export_low_stock` (:236-345) and counts
groups again in `low_stock_preview` (:347). Refactor into ONE model builder the workbook renders:

```python
def build_low_stock_view(db, *, run_id, include_supplier=True, split="supplier_category",
                         suppliers=None, categories=None) -> dict:
    # {run: {run_id, as_of}, split, columns, rows: [tuple],
    #  sheets: [{title, row_indexes, low}],
    #  facets: {suppliers: [{key, rows, low}], categories: [...]},
    #  counts: {rows, low, sheets}, over_cap, max_rows, filename}
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
- **Speed (owner ruling 26 Sep, Q8: "optimize performance and make the download reasonably as
  fast as possible").** The workbook is written with openpyxl's write-only mode and ONE shared
  set of cell styles (`WriteOnlyCell`), instead of appending rows and then walking every cell
  again to set a new border and alignment on each. Same look: dark bold header, thin borders,
  wrapped text, frozen at A2, the same widths. The view and the export build the model once per
  call; the export task does not read the run twice. S1's PR states the export time on a
  5,000-row run before and after (the build of the model and the write of the file, measured
  separately), and the view route's time and payload on the same run.
- The export route's cap check (AC-7) counts the FILTERED rows. The cheap
  `export_guard_stats` count still answers first; only a run over the cap WITH filters builds
  the model to count what the filters keep, so an unfiltered request stays one COUNT query.

Routes (`BE/api/v1/scm/order_summary.py`, beside the export):

- `GET /scm/order-summary/low-stock-view?run_id=&split=&supplier=&category=` -> `LowStockViewOut`
  (AC-1). `scm.reorder.run`, the page's own gate (review N1 of #1270), JWT only like the
  export (the report carries supplier names).
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
  `LowStockExportDialog.tsx` is deleted (owner ruling 26 Sep, Q3). One surface, not two that can
  drift.
- `SpreadsheetViewer` ships in S1 with the JSON feeder only (sheet tabs, "Go to sheet" over 12
  sheets, frozen header, first column pinned, rows virtualised with `@tanstack/react-virtual`,
  the grid scrolling sideways inside its own container). The SheetJS feeder joins it in S2.

## 5. The daily email: the automation's link (S1, owner rulings 26 Sep, Q1 and Q5)

The email is the automation engine's (section 2F). The plan builds no email event, no recipient
list and no sender of its own; it gives the automation what it cannot have today, a trigger that
knows the run:

- `automation_triggers.register(TriggerSpec(type="low_stock_report_ready", label="Low stock
  report ready", ...))`, event-driven like `complaint_approved` (`:320`): pull mode yields
  nothing, matches come from `AutomationService.dispatch_event`.
- `_handler_scm_reorder_run` (`task_scheduler.py:411`), after the run is funded, calls
  `low_stock_report_service.dispatch_ready(db, run_id)`: builds the counts off the same model
  builder and dispatches ONE match with context
  `report: {link, as_of, date_label, low, rows}`, where `link` is
  `<FRONTEND_BASE_URL>/scm/low-stock-report/<run_id>` (the in-system page; the deep-link-after-
  login layout brings a signed-out reader back to it). Best effort: caught and logged, never
  fails the run.
- Recipients: the automation's own `recipient_config` (owner ruling 26 Sep, Q5). No scheduled-
  task metadata key, no form field.
- The admin, in System > Automations, sets the existing low stock rule's trigger to "Low stock
  report ready" and puts `{{ report.link }}` in its template (subject, for example,
  `Low stock report {{ report.date_label }}: {{ report.low }} low`). A template that cannot carry
  a variable can link `<FRONTEND_BASE_URL>/scm/low-stock-report`, which always opens the newest
  completed run.
- The email carries a link, not the file: the owner's point is to look first.

## 6. My Downloads (S2)

- `DownloadRow.tsx`: for a ready `.xlsx/.xls/.xlsm/.csv/.pdf` row, the row body runs
  `onPreview` (today :133-149 run `onDownload`), title "Preview"; the Download icon runs
  `onDownload`; the separate Eye icon goes (the row IS the preview). Other kinds unchanged.
- `AttachmentPreviewModal`: `ExcelSlide` (:544-715) is replaced by
  `<SpreadsheetViewer loadData={...} fileActions={false} />`; the modal header keeps Download and
  Open. Search and highlight move into the viewer (existing tests move with them). PDFs use
  #1256's `PdfViewer` once it merges; this plan does not depend on it.
- `KIND_LABEL` gains the three missing kinds.

## 7. The remaining sources (S3)

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
| S1 | Standalone low stock report page: model builder + view route + filters on the export (cap on filtered rows, faster writer, timings) + page + `SpreadsheetViewer` (JSON feeder, virtualised) + sidebar item + Actions link with the dialog removed + the `low_stock_report_ready` trigger whose `report.link` the automation's email carries | J-A 1-7 | coder, tests red first -> reviewer + browser |
| S2 | SheetJS feeder with the dependency bump (a regression test per current `xlsx` caller, green before and after), `ExcelSlide` -> `SpreadsheetViewer`, My Downloads row click = preview | J-B | Phase 1 -> 2 -> 3 |
| S3 | `useSpreadsheetPreview` + 7 sync sites + supplier notice byte route + 2 browser-built documents | J-C | coder, one site per commit |

Re-ordered by the owner's rulings of 26 Sep: the email needs no slice of its own (Q1, Q5), so
S1 is the page plus the link the email carries, and can be hand-tested alone. S2 depends on S1
for the viewer component. S3 depends on S2. S1 ships on its own lane branch and PR (the rest of
the lane follows it); this plan PR stays a draft docs PR and is never merged.

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
- **#1256 overlap**: both edit `AttachmentPreviewModal.tsx`; S2 lands after #1256 or merges it in.
- **The live automation row.** The rule that sends the email today is data this repo cannot see.
  Until the admin points it at `low_stock_report_ready`, its email keeps whatever link it has;
  the S1 PR says so and names the two edits (trigger, template link).

## 10. Out of scope

- DataGrid toolbar and list-query exports (the grid is the preview; owner ruling 26 Sep, Q6).
- WhatsApp and supplier email deliveries (not in our UI).
- CSV routes stay downloads in S3 except where a screen already offers them (the viewer reads CSV
  for free once it exists; wiring the three CSV sites is a one-line follow-up per site).
- Editing cells in the preview.

## 11. Grill questions and the owner's answers

Posted on the PR as one comment (26 Sep 05:11Z); answered by the owner at 05:28Z. The ruling is
recorded under each question and in section 0.

1. **The daily email.** Asked whether it is an n8n flow or the intent. *Owner ruling 26 Sep:* it
   is a scheduled task that uses the automation. -> Section 2F corrected, section 5 rewritten: a
   trigger with the run's link, no new email path.
2. **Finding the page besides the email.** Recommended a sidebar item under Procurement > Supply
   Chain opening the newest run, Reorder Planning's permission. *Owner ruling 26 Sep:* ok.
3. **Reorder Planning's Actions > Low stock report Excel.** Recommended: open the page, delete the
   dialog. *Owner ruling 26 Sep:* ok, open the new page.
4. **Download on the page.** Recommended "Preparing...", auto-save, also in My Downloads.
   *Owner ruling 26 Sep:* accepted.
5. **Email recipients.** Recommended a user list on the scheduled task. *Owner ruling 26 Sep:*
   pick them in the automation the scheduled task runs. -> the automation's `recipient_config`.
6. **"Every Excel".** Recommended: not the DataGrid Export buttons. *Owner ruling 26 Sep:* ok.
7. **SheetJS upgrade.** Recommended the vendor's 0.20.3 tarball. *Owner ruling 26 Sep:* yes,
   make sure there is no regression. -> a test per current caller, before and after (S2).
8. **Runs over 5,000 rows.** Recommended counting rows after filtering. *Owner ruling 26 Sep:*
   ok, and optimise so the download is as fast as reasonably possible. -> write-only writer,
   timings before and after in the S1 PR.
