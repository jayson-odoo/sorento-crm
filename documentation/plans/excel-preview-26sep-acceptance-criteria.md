# UAC: In-app Excel preview, low stock report first

Plan: `PLAN-excel-preview-26sep.md`
Owner words: 26 Sep 2026 (the brief) and the 01:40Z clarification (binding): the email link
lands on a standalone low stock report page, never the reorder planning screen; the page is
the Excel preview of the plan; split by supplier / category, default both; filter suppliers and
categories; Download gives that Excel.

Owner rulings 26 Sep (answers to the grill on #1261, 05:28Z, binding; plan section 0):
Q1 the email is the automation engine's, driven by a scheduled task, and its link opens this
page; Q2 sidebar item, ok; Q3 Actions item opens the page, dialog removed, ok; Q4 Preparing...
then auto-save and My Downloads, accepted; Q5 recipients are picked on the automation; Q6
DataGrid Export excluded, ok; Q7 SheetJS 0.20.3 tarball with no regression; Q8 cap on filtered
rows, and the download as fast as reasonably possible. Slices re-ordered: S1 page + email link,
S2 viewer + SheetJS + My Downloads, S3 remaining sources.

Owner hand test 26 Sep ~08:45Z (binding, supersedes Q2 and the matching parts of AC-10 to AC-12,
AC-16b and AC-18): no "N low of M" in the supplier / category options; no "Go to sheet"
dropdown; the sheet list is searched from a "..." on the tab strip itself, Excel style; a
product code search in its place; no sidebar item, the report is reached from a plan
(Reorder planning > Actions) and a "Back to Reorder planning" button returns to that plan.

Tags: `[BE]` backend, `[FE]` frontend, `[E2E]` browser pass via sidebar, `[T]` a named test.

## Journey

### J-A The daily low stock email (buyer, every morning)

1. The daily reorder run finishes on the scheduler (already happens: `_handler_scm_reorder_run`)
   and fires the automation trigger "Low stock report ready" with the run's date, low count and
   link. Recipients are the ones the admin picked on the automation (owner ruling 26 Sep, Q5).
   Nothing is asked of anyone.
2. The buyer gets the automation's email: its template names the date and the low count and
   carries one link, "Open the low stock report".
3. The buyer clicks it. If not signed in, they sign in and land back on the same page
   (the existing deep-link-after-login).
4. First screen: the **Low stock report** page for THAT run. Title and date in the header. No
   reorder planning grid, no planning actions. The body is the workbook, already split by
   supplier and category (the default), shown as sheets in our own grid style: tabs across the
   top, frozen header row, the first sheet open.
5. The one decision the buyer may make: narrow it. Split (Supplier and category / Supplier /
   Category / None) and two searchable multi-selects, Suppliers and Categories. Every change
   redraws the sheets at once. A count line reads "N rows, M sheets".
6. Download. The button shows progress while the file is built, the file saves itself when
   ready, and it is also in My Downloads.
7. They hold the exact workbook they looked at: same sheets, same rows, same order.

### J-B Any Excel in My Downloads (any user)

1. The user opens My Downloads and clicks an Excel row.
2. The file opens in the preview: sheet tabs, frozen header, every row scrollable, our styles.
3. Download is a separate, explicit button (and the row's own download icon). Nothing is saved
   unless they press it.

### J-C Every other Excel the system hands over (any user)

1. The user presses an Excel export anywhere (proforma invoice, loading plan, SPO worksheet, OI
   export, amendment change list, AutoCount pull, purchase request, stock inquiry).
2. The workbook opens in the same preview instead of saving straight away.
3. Download in the preview saves it. Queued exports keep landing in My Downloads, where J-B
   applies.

## Phase S1: Low stock report page and the email's link (J-A steps 1-7)

### Backend

- AC-1 [BE] `GET /scm/order-summary/low-stock-view?run_id=&split=&supplier=&category=`
  answers `{run: {as_of, label}, columns: [..], rows: [[..]], sheets: [{title, row_indexes}],
  facets: {suppliers: [{key, rows, low}], categories: [{key, rows, low}]}, counts: {rows, low,
  sheets}, filename}`. `supplier` and `category` repeat (multi); omitted = all. Behind
  `scm.reorder.run` (JWT only; the page's own gate, review N1 of #1270); 404 on a malformed or
  invisible run;
  `run_id` omitted = newest completed run. Every field declared on `LowStockViewOut` and asserted
  by name through the route. (J-A 4)
- AC-2 [BE] The view and the export are ONE builder. `export_low_stock` renders the sheet model
  returned by `build_low_stock_view(...)`; no second row builder, no second split. For the same
  `(run_id, split, suppliers, categories)` the workbook's sheet titles equal `sheets[].title` in
  order, and every sheet's cell values equal the view's rows at `row_indexes` in order. [T]
  `test_view_and_workbook_agree` over all four splits and one filtered case. (J-A 7)
- AC-3 [BE] Default split on the view is `supplier_category` when `split` is omitted
  (owner: "default is split by both"). The export route's own default stays `none` for API
  callers; the page always sends its split explicitly.
- AC-4 [BE] Filters apply BEFORE the split: a row is kept when its supplier key is in
  `supplier` (or `supplier` is empty) AND its category key is in `category` (or empty). Keys
  are the split keys, blanks included as "No supplier" / "No category". A key the run does not
  hold is ignored, not an error.
- AC-5 [BE] `facets` are over the WHOLE run, not the filtered rows, each with its row and low
  count, sorted by key case-insensitive. The page can therefore always show every choice.
- AC-6 [BE] `POST /scm/order-summary/export` with `format: low_stock_xlsx` accepts optional
  `suppliers: string[]` and `categories: string[]`, forwards them to
  `generate_low_stock_report`, and the task forwards them to `export_low_stock`. Sent with any
  other format -> 422 "filters apply to the low stock report only", no download row.
- AC-7 [BE] The row cap (`MAX_LOW_STOCK_ROWS`, 5000) is checked on the FILTERED row count, in the
  export and in the view alike (a filter can bring an oversized run under the cap). Over the cap
  the view still answers 200 with `counts.rows` and `rows: []` plus `over_cap: true`; the export
  answers 422 as today.
- AC-8 [BE] Unchanged: the in-flight 409 per user / run / kind; the chat route (no split, no
  filters); `include_supplier=False` refuses a supplier split (R5 of the split plan). The
  existing `tests/scm/test_low_stock_report.py` and split tests stay green unchanged.
- AC-9 [BE] Payload: each row travels once; `sheets` carry indexes, not copies. [T] a 5000-row
  run answers in under 1 s locally and under 1.5 MB uncompressed.
- AC-9b [BE] Speed (owner ruling 26 Sep, Q8). The workbook is written in openpyxl write-only
  mode with one shared style set; the file looks the same (header fill and font, thin borders,
  wrapped text, frozen at A2, the same widths) [T] `test_workbook_style_unchanged`. The S1 PR
  states the export time for a 5,000-row run before and after, the model build and the file
  write measured separately.

### Frontend

- AC-10 [FE] Route `/scm/low-stock-report/[runId]`: always the plan named in the URL.
  `/scm/low-stock-report` names no plan and redirects to `/scm/reorder` (an old bookmark;
  hand test 26 Sep, W5). `PageHeader` title "Low stock report", the run's date as the subtitle,
  and in its actions "Back to Reorder planning" (`BackToList`, as "Back to purchase orders" on
  the purchase order page) to `/scm/reorder/<run id>` (W6). No
  reorder planning grid, actions or budget on the page. (J-A 4)
- AC-11 [FE] Toolbar, left to right, wrapping as whole groups at 375px: Split (pill toggle,
  `Tabs variant="default"`: Supplier and category / Supplier / Category / None, Supplier and
  category selected on load), Suppliers (`SearchableMultiSelect`, clearable, plain names: no
  "N low of M", hand test 26 Sep, W1), Categories (same), the count line "N rows, M sheets", Download (primary
  button, right). (J-A 5)
- AC-12 [FE] The body is the shared `SpreadsheetViewer` fed from the view response: sheet tabs
  (`TabsList variant="line"`, scrolling, never wrapping, its left / right chevrons kept) with a
  "..." at the strip's end that opens a searchable list of every sheet; picking one opens it and
  the strip scrolls to it (Excel's sheet list, W3). No separate "Go to sheet" dropdown (W2).
  Under the strip, a "Search product code" box filters the open sheet's rows by item code or
  description, the "N rows" label following (W4). Frozen header row, rows virtualised, numbers right-aligned
  and tabular, the first sheet open. An empty ` - Low` sheet shows "Nothing low here". (J-A 4)
- AC-13 [FE] Changing split or a filter refetches the view (debounced 250 ms, previous rows kept
  on screen dimmed until the new ones arrive); the open sheet stays open when a sheet with the
  same title still exists, else the first sheet opens.
- AC-14 [FE] Download posts the export with the page's current split, suppliers and categories.
  The button reads "Preparing..." with a spinner while the download row is pending, the file
  then saves through `/downloads/{id}/file` with no second click, and a toast says it is also in
  My Downloads. A 422 / 409 toasts the extracted message and the button returns to Download.
  (J-A 6)
- AC-15 [FE] States: loading (grid-shaped `SectionSkeleton`), empty run ("No products on this
  plan", Download disabled), over cap ("N rows is over the
  5,000 row limit. Narrow by supplier or category." with Download disabled), error (extracted
  message + Retry), 403 (the standard no-access page).
- AC-16 [FE] Reorder Planning's Actions > "Low stock report Excel" navigates to
  `/scm/low-stock-report/<run id>` for that run. `LowStockExportDialog` and
  `GET /low-stock-preview` are removed (the page replaces both). (Owner ruling 26 Sep, Q3.)
- AC-16b [FE] No sidebar item: the report is opened from a plan (Reorder planning > Actions)
  or the daily email's run link. (Hand test 26 Sep, W5, superseding Q2's sidebar item.)
- AC-17 [FE] No UUID rendered (the run shows as its date), no feature explanation text, usable
  at 375px and 1280px.
- AC-18 [E2E] From `/`, sidebar: Procurement > Supply Chain > Reorder Planning, a plan,
  Actions > Low stock report Excel opens that plan's report; choose Supplier, pick two suppliers, the sheets become four; Download; the saved file's
  sheet titles and first rows match the screen. Second pass: open the email link for a named run
  while signed out, sign in, land on that run's page.

### The email's link (J-A steps 1-2; owner rulings 26 Sep, Q1 and Q5)

- AC-19 [BE] A new automation trigger `low_stock_report_ready` ("Low stock report ready") in
  `automation_triggers`, event-driven (pull mode yields nothing), listed by
  `GET /system/automation/triggers/catalog` so the admin can pick it in System > Automations. No migration.
- AC-20 [BE] When `_handler_scm_reorder_run` has funded the run it dispatches the trigger ONCE
  with context `report: {link, as_of, date_label, low, rows}`; every enabled
  automation on that trigger sends its own template to its own `recipient_config`. No enabled
  automation = nothing sent, no error. No new recipient list anywhere (Q5).
- AC-21 [BE] `report.link` is `<FRONTEND_BASE_URL>/scm/low-stock-report/<run_id>` (the in-system
  page; a relative path when the base is unset, like the other trigger links). `low` and `rows`
  are the workbook's own counts for the default view (whole run, no filters).
- AC-22 [BE] Best effort: a failure to count or dispatch is logged and never fails the run. [T]
  `test_daily_run_dispatches_low_stock_report_ready`, `test_trigger_context_link_is_internal_page`,
  `test_dispatch_failure_does_not_fail_run`, `test_trigger_is_listed`.
- AC-23 retired (owner ruling 26 Sep, Q5): no recipients field on the scheduled task form.

## Phase S2: Generic preview, SheetJS bump, My Downloads (J-B)

- AC-24 [FE] `components/common/SpreadsheetViewer` (lazy, like `PdfViewer`): props
  `{workbook | loadData, fileName, title, fileActions, className}`; `workbook` is the normalised
  model `{sheets: [{title, columns?, rows}]}`; `loadData` reads bytes and parses them with SheetJS
  into the same model. Toolbar matches `PdfViewer` (#1256): ghost icon `Button`s, sheet label,
  row count, search, Download, Open in new tab; `fileActions={false}` inside a chrome that
  already has them.
- AC-25 [FE] Parsing: SheetJS loads only on first use (dynamic `import`), never in a page's
  initial chunk; the declared-range trap stays fixed (scan cap per sheet, the reason in
  `AttachmentPreviewModal.tsx:511-527`); only the open sheet is converted. Display cap rises from
  200 rows to 50,000 per sheet (virtualised), 60 columns; beyond either, a footnote names what was
  cut and Download is the way to the rest. Files over 25 MB show "Too large to preview here" +
  Download.
- AC-26 [FE] `AttachmentPreviewModal`'s `ExcelSlide` is replaced by `SpreadsheetViewer
  fileActions={false}`; its search and highlight behaviour is kept (existing tests stay green or
  move with it).
- AC-27 [FE] My Downloads: clicking a ready Excel, CSV or PDF row (the row body) opens the
  preview; the row's Download icon saves the file; the tooltip reads "Preview", not "Click to
  download". Other kinds keep click-to-download. `KIND_LABEL` gains the missing kinds
  (`order_inquiry_xlsx`, `order_inquiry_worklist_xlsx`, `oi_worksheet_xlsx`).
- AC-28 [FE] Keyboard: Enter on a focused row opens the preview; Escape closes it; no motion on
  a keyboard-opened preview (M2-01).
- AC-29b [FE] SheetJS moves to the vendor's 0.20.3 tarball (owner ruling 26 Sep, Q7: "make sure
  no regression"). Before the bump every current `xlsx` importer is listed by file:line and has a
  vitest that reads or writes a real fixture workbook through it; the same tests pass on 0.18.5
  and on 0.20.3.
- AC-29 [E2E] My Downloads > click the low stock row > preview shows its sheets > Download saves
  the same file; at 375px and 1280px.

## Phase S3: The remaining Excel sources (J-C)

- AC-30 [FE] A shared `useSpreadsheetPreview()` hook opens the preview modal from
  `() => Promise<Blob>` plus a filename; Download saves that blob (`saveBlobAs`). Each sync site in
  plan section 2 table B calls it instead of saving directly.
- AC-31 [FE] The browser-built detail exports (purchase request, stock inquiry) write their
  workbook to an `ArrayBuffer` and open the same preview; Download writes the same bytes.
- AC-32 [FE] DataGrid toolbar "Export Excel" and the list-query export are unchanged (the grid on
  screen is already the preview). (Owner ruling 26 Sep, Q6.)
- AC-33 [FE] Queued exports keep their "will appear in My Downloads" toast; the preview is
  reached from My Downloads (S2). No per-site change.
- AC-34 [E2E] One pass per swapped site: press its Excel action, the preview opens with the right
  sheets, Download saves a file whose first sheet matches.

## Test list

Backend (`tests/scm/test_low_stock_report.py`, `tests/scm/test_low_stock_view.py`,
`tests/scm/test_low_stock_report_ready_trigger.py`):

1. `test_view_default_split_is_supplier_category` (AC-3)
2. `test_view_and_workbook_agree` (AC-2, parametrised over 4 splits + 1 filtered case)
3. `test_view_filters_apply_before_split_blank_buckets_selectable` (AC-4)
4. `test_view_facets_are_whole_run_with_counts` (AC-5)
5. `test_view_route_404_invisible_run_fields_declared` (AC-1)
6. `test_view_over_cap_answers_counts_without_rows` (AC-7)
7. `test_export_route_forwards_filters_to_task` (AC-6)
8. `test_export_route_rejects_filters_on_other_formats` (AC-6)
9. `test_cap_checked_on_filtered_rows` (AC-7)
10. `test_view_payload_rows_travel_once` (AC-9)
11. The four trigger tests named in AC-22 (AC-19..AC-21)
11b. `test_workbook_style_unchanged` (AC-9b)

Frontend (vitest):

12. `LowStockReportPage.test.tsx`: default split pill, filters send repeated params, count line,
    over-cap disables Download, error + Retry, no UUID (AC-10..AC-17)
13. `useLowStockDownload.test.ts`: pending -> saves via `/file` -> toast; 409 toast (AC-14)
14. `SpreadsheetViewer.test.tsx`: tabs, no "Go to sheet", the strip's "..." sheet search,
    the row search, frozen header class, virtualised
    row count in DOM stays bounded on 50,000 rows, footnote on cut, `fileActions` off (AC-12,
    AC-24, AC-25)
15. `parseWorkbook.test.ts`: declared-range trap (a sheet claiming 1,048,000 rows scans the cap
    only), only the open sheet converted (AC-25)
16. `DownloadRow.test.tsx`: Excel row click opens preview, icon downloads, PDF too, other kinds
    download (AC-27, AC-28)
17. `ReorderPlanView.lowStock.test.tsx` rewritten: the item navigates to the page (AC-16)
18. `menu.config.test.ts`: no Low stock report item (AC-16b); `low-stock-report/page.test.tsx`:
    the bare route redirects to Reorder planning (AC-10)
18b. One regression vitest per current SheetJS caller, green on 0.18.5 and 0.20.3 (AC-29b)
19. One vitest per S3 site: its action opens the preview, not a save (AC-30, AC-31)
