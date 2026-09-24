# PLAN: Stock Debt - cutoff + supplier + retail filters, totals, Excel-style cell summary, workbook export, menu move

Status: in progress, Phase 3 verified, PR #1165 (24 Sep 2026). Track: feature (three-phase). Lane branch: `feat/stock-debt-filters-export`, worktree `sorento_crm-stock-debt`. Plan created 24 Sep 2026, grilled + two lavish rounds same day.
UAC: `stock-debt-filters-totals-export-24sep-acceptance-criteria.md`
Domain: scm (Stock Debt view, `/project-sales/stock-debt`)
Parent: `PLAN-scm-borrow-ladder-v7-stock-debt.md` S2 (the view this extends; its rulings R14, R22, R23, R28, R37 stand)

## Why

Owner, 24 Sep 2026, reading the live view at `fe-sorento.foundryx.my/project-sales/stock-debt`:
the page states debt per month but gives no total, no way to narrow to a supplier or a date
window, and no way to take it away as a workbook a buyer can walk supplier by supplier. The
same asks (split by supplier / product type on export) are coming for the low stock report;
that is the SECOND case and the trigger to lift the export splitter, not part of this lane.

## Measured facts (primary checkout, `origin/main` 2280975f9, 24 Sep 2026)

| fact | where |
| --- | --- |
| Cell = the month's OWN balance (not cumulative): free supply dated in the month minus what the lines due in it went short of (R37) | `app/schemas/stock_debt.py:StockDebtMonth`, `supply_assignment.assign` |
| Tone: green when balance >= 0; red when negative and the month starts before `today + lead`; amber when negative and later than that. TBA / No date / No location carry no tone | `supply_assignment.tone_for:340-349`, `StockDebtClient.tsx:43-55` |
| Demand read = open sales-order lines (`is_open_demand()`: line open, not COVERED, qty > 0) booked at bins flagged `fulfilment_planning`, plus unlocated lines. NOT order inquiries. Own stock is netted by the walk before anything is called debt | `stock_debt_service._demand`, `planning_predicate.py`, `demand.py:175` |
| Site pools (dealer / retail bins) are OUT of the view's span; the ladder already runs them as one extra group `POOL_GROUP` inside the same `assign()` | plan v7 3.4 ruling 30 Aug; `supply_assignment.py:131`, `project_supply_service._site_pool_warehouses:2211` |
| Span is chosen once in `_warehouses(group)`; every read below takes that dict | `stock_debt_service.py:271-287` |
| List is server-paginated (`page`, `limit` <= MAX_PAGE_LIMIT); axis (`months`, `tba_month`, `groups`) rides on the envelope for the whole filtered set | `stock_debt.py` route, `list()` at `stock_debt_service.py:107-153` |
| Product name is rendered as a second line whenever it is non-null; on the live book it equals the code on most rows | `StockDebtClient.tsx:185-197`; owner screenshot 24 Sep |
| `products.item_type` is NULL on all 15,326 rows; category (`product_categories.category_code`) is populated | psql, local prod copy 24 Sep |
| `product_suppliers.is_primary_supplier` is a MANUAL flag (set on the Product-Suppliers screen, `procurement_service.py:6968`); nothing flips it on a purchase. 3,443 products have no supplier row; 1,640 have two or more | model `procurement.py:96-122`; psql 24 Sep |
| "Last in" = newest visible `spo_allocations` line per product by `coalesce(expected_date, issue_date, created_at) DESC, created_at DESC`; that line carries `supplier_id` | `spo_last_receipt_service.last_in_map:272`, `procurement.py:514` |
| Existing xlsx export pattern, request-thread, direct bytes: `Response(body, media_type=WORKLIST_XLSX, headers={"Content-Disposition": content_disposition(filename)})`; FE `saveBlobAs(blob, name)` | `api/v1/projects/order_inquiries.py:468-500`, `project-sales/_shared/services/fileDownload.ts:19` |
| One styled openpyxl sheet writer already shared by two workbooks | `summary_order_service.write_sheet:1589` |
| `DataGridTable` renders a footer row when a column declares `footer` | `components/ui/data-grid-table.tsx:895-907` |
| DataGrid has no cell selection of any kind | grep `components/ui/data-grid*.tsx`, 24 Sep |
| Corrected 24 Sep (coder, Phase 1): Stock Debt appears in `MENU_SIDEBAR` (`:238`) and in the unmounted `MENU_SIDEBAR_COMPACT` (`:1892`); `MENU_MEGA` has no entry at all. Only `MENU_SIDEBAR` is rendered - `Demo1Layout` (the app's one mounted layout) reads it everywhere, and never renders the `MegaMenu`/`Demo6`/`Demo10` components the other two exports serve. The Procurement > Supply Chain submenu (Reorder Planning, Loading Plan, Order Inquiries, Purchase Orders, Proforma Invoices) is at `:302-330` | `config/menu.config.tsx`; `app/(protected)/layout.tsx`; `app/components/layouts/demo1/components/sidebar-menu.tsx` |

## Rulings (owner, 24 Sep 2026)

- R1 Retail ships NOW, COMBINED with project (lavish round, 24 Sep: "each PO line is tagged to each SO line, so the distinction is there, they should be combined"). Default span = flagged project bins PLUS the site pools, the exact span the ladder assigns over. A `book` filter narrows: `all` (default) / `project` / `retail`.
- R2 Cutoff date DROPS demand due after it. Not folded into TBA, not shown at all.
- R3 Supplier filter keys on the LAST supplier, not the primary flag. Owner: "always should be based on last supplier"; lavish round: "we should look at PO, not SPO". Last supplier = the supplier on the product's newest PURCHASE ORDER line. Primary is manual today, so it is the fallback only.
- R4 "Product type" = product category (`category_code`).
- R5 Export split options: none / supplier / category / supplier x category; one sheet each; every sheet carries a row Total column and a Total footer row.
- R6 Stock Debt MOVES to Procurement > Supply Chain (beside Reorder Planning). It leaves Project Demand. Both menu trees.
- R7 Totals must be agile: a user picks any rectangle of cells (a date window, a set of products) and reads Count / Sum / Avg / Min / Max, like Excel. A fixed Total column and Total row are still wanted, the selection is on top of them.
- R8 Product name is hidden when it equals the product code.
- R9 The Total column INCLUDES TBA, No date and No location (lavish round). Footer row is the whole filtered set.
- R10 Export runs as a worker job onto My Downloads, reusing the low stock report's pipeline (lavish round: "worker job with stored attachment like low stock"; "reuse as much as possible").
- R11 Cutoff is the SALES ORDER cutoff, on the SO line's required (delivery) date (lavish round 2, O1 answered).
- R12 Export is a primary CTA labelled "Export", nothing longer (lavish round 2).
- R13 The toolbar must get SIMPLER, not busier (lavish round 2: "too many UI components already"). Three controls on the bar: Search, Filters, Export. Every filter, including "Only products in debt", lives inside the Filters panel; active filters read as chips under the bar, as `DataGridListToolbar` already renders them.

Owner's hand-test round, live stack, 24 Sep 2026 (folded into the AC ids in the UAC rather than kept separately - each AC line there already states which ruling changed it):

- R14 Date RANGE replaces the single cutoff. Params `date_from` and `date_to` (both optional, `YYYY-MM-DD`, on the SO line's required date). A line due before `date_from` or after `date_to` is dropped; undated lines are kept; the axis runs from `max(current month, date_from's month)` to `date_to`'s month (no `date_to` = today's rule). `cutoff` is REMOVED, not aliased.
- R15 Supplier is a MULTI select. Param `supplier_ids` (repeatable query param; `none` allowed among the values). A product matches when its last supplier is in the set (or has none and `none` is in the set). Export body takes `supplier_ids: []`. `supplier_id` (singular) is REMOVED, not aliased.
- R16 The Ownership group filter LEAVES the screen. No control, no chip, no `group` sent by the FE service. Backend `group` param and its own tests stay untouched - it is still a valid (if now FE-unreachable) narrowing.
- R17 The "No date" and "No location" columns LEAVE the screen and the workbook. `total` = `months` + `TBA` only. The API row still carries `undated` and `unlocated` (unchanged), just not folded into `total` and not rendered as columns.
- R18 The TBA column header reads "TBA" (its `title` tooltip may carry the month), never the raw `tba_month` key (e.g. `2029-01`).
- R19 Copy works without `navigator.clipboard` (the owner reaches the stack over http on a LAN hostname, not a secure context): falls back to `document.execCommand('copy')`.

## Assumptions stated, not ruled

- A1 (ruled R3) "Last supplier" = `purchase_orders.supplier_id` of the product's newest PO line, newest by `purchase_orders.issue_date DESC NULLS LAST, purchase_order_lines.created_at DESC` (no coalesce - a PO with no `issue_date` sorts last, it does not borrow its own `created_at` to compete with a dated one), cancelled POs skipped (a cancelled line is not); falling back to the primary-flagged product supplier, else "No supplier".
- A2 Cutoff also ends the AXIS: months after the cutoff month are not drawn. Supply landing after the cutoff still counts for lines due on or before it - a line due 10 Nov, covered by an SPO landing 20 Nov, still ends `late` under `cutoff=2026-11-30`, and November still reads -20 (R37 books the shortfall in the line's own month regardless of it being eventually covered, exactly as it would with no cutoff at all - see `test_supply_arriving_after_the_debt_is_spare_in_its_own_month`).
- A3 Undated and unlocated demand are NOT dropped by the cutoff (they have no date to test). TBA is dropped when `tba_date_from` is after the cutoff, because every TBA line is dated on or after it.
- A4 (ruled R1) Combined span. `assign()` already seals `POOL_GROUP` from every project group in both directions, and `_assignments` already passes the pool set to `_supply` and `_demand`, so adding the pool warehouses to `_warehouses()` is the whole change: a product's month balance becomes project groups plus pool, each covered only by its own supply and its own placement links.
- A5 (ruled R9) The Total column = sum of month cells + TBA + No date + No location. Each keeps its own column too.
- A6 Footer totals are for the WHOLE filtered set, computed server-side on the envelope, not the page. A page total would change as the reader pages.
- A7 Cell selection is built inside the Stock Debt screen (its own hook), not in `DataGrid`. The low stock report is the named second case; when it arrives the hook is lifted. One event does not need a registry.
- A8 (ruled R10) Export = `DownloadService.create(kind="stock_debt_xlsx")` + `enqueue_job(generate_stock_debt_xlsx, ...)` on the `imports` queue, task in `app/tasks/export_tasks.py` shaped like `generate_low_stock_report` (mark_processing, build bytes, store under `exports/stock-debt-xlsx/<download_id>/<filename>`, mark_ready, `_record_failure` on error). FE: a hook shaped like `useExportLowStockReport` returning the `MyDownload` row, toast "Export queued, find it in My Downloads". Worker must be running (CLAUDE.md dev-session rule).

## Design

### Backend (one service, one route file)

`GET /api/v1/project-sales/stock-debt` gains params, all optional and additive to `query`, `group`, `only_debt`, `page`, `limit` (R14/R15 owner round supersedes the original `cutoff`/`supplier_id` pair below - REMOVED, not aliased):

| param | type | meaning |
| --- | --- | --- |
| `date_from` | `YYYY-MM-DD` | drop demand lines with `required_date < date_from` (R14); axis starts at `max(current month, month_key(date_from))` |
| `date_to` | `YYYY-MM-DD` | drop demand lines with `required_date > date_to` (R14); axis ends at `month_key(date_to)` |
| `supplier_ids` | uuid, repeatable | keep products whose last supplier (A1) is ANY of these values; `none` is one more value among the others, not a sentinel (R15) |
| `book` | `all` (default) / `project` / `retail` | `all` = flagged project bins + site pools (the ladder's span); `project` = flagged bins only (today's view); `retail` = site pools only. `group` applies to the project half only |

Envelope gains:

- `totals`: `{ months: { "2026-09": -812.0, ... }, tba, undated, unlocated, total }` over the whole filtered set (A6). `total` sums `months` + `tba` ONLY (R17 supersedes A5 - `undated`/`unlocated` no longer fold in).
- Each row gains `total` (R17: months + tba only), `supplier_id`, `supplier_name`, `category_code`.
- `suppliers: [{id, name}]` the distinct last suppliers of the filtered set, for the toolbar select (same reason `groups` rides here).
- `sheet_counts: {supplier, category, supplier_category}` the exact export sheet counts for the current filtered set (none-buckets included), for the export popover's preview (AC-7b).

`product_name` is returned as `None` when it equals `product_code` (R8, done once at the source so the export and the grid agree).

`POST /api/v1/project-sales/stock-debt/export` takes every list param except `page` / `limit` (`date_from`/`date_to`/`supplier_ids`, never `cutoff`/`supplier_id`/`group`), plus `split` in `none | supplier | category | supplier_category`. Creates a `user_downloads` row (`kind=stock_debt_xlsx`, filename `stock-debt-<ddmmyyyy>.xlsx`), enqueues `generate_stock_debt_xlsx(download_id, user_id, params)` on `imports`, returns the download row (201) the way the low stock export route does. The task builds the workbook through `StockDebtService.export()` and stores it via the same storage + `mark_ready` path. One sheet per split key, sheet title = supplier name / category code / `<supplier> - <category>` (openpyxl title limit 31 chars, sanitised; "No supplier" / "No category" for blanks), sorted by title. Columns: Product, Name (blank when equal), Category, Supplier, one column per axis month, TBA, Total (R17: "No date"/"No location" are GONE from the workbook). Last row = Total footer. Written with `write_sheet` (existing). Refused at 422 above the low stock report's `MAX_LOW_STOCK_ROWS`, same reason.

Where the pieces go in `stock_debt_service.py`:

- `_warehouses(group, book)`: `all` = flagged bins (narrowed by `group`) + `ProjectSupplyService._site_pool_warehouses()`; `project` = flagged bins only; `retail` = pools only.
- `_demand(..., date_from, date_to)`: `SalesOrderLine.required_date >= date_from` and `<= date_to`, each `OR required_date IS NULL` (R14).
- `_last_supplier_map(product_ids)`: newest PO line per product (A1), then primary flag, else None. Two reads for the whole set, window function, never per product.
- `list()`: filter rows by supplier (multi, R15) after assignment, then axis, then totals (R17: months + tba only), then page.
- `export()`: `list()` with `limit=None`, grouped by split key, one `write_sheet` per group. Returns `(bytes, content_type, filename, {"rows": n, "sheets": m})` like `export_low_stock`.

Cell drill (`/cell`) takes `date_from`, `date_to` (R14, replacing `cutoff`) and `book` so the drill foots with the cell that opened it.

### Frontend (Stock Debt screen only)

- Toolbar (R13): `Search` | `Filters` (count badge) | spacer | `Export` (primary). The refresh icon button and the "Only products in debt" switch leave the bar. Filters panel, top to bottom (R14/R15/R16 owner round supersedes the original list): Book (All / Project / Retail, default All), Supplier (`SearchableMultiSelect`, options from envelope `suppliers` plus "No supplier", R15), Due date (`DateRangePicker`, clearable, R14 - replaces the single Cutoff date), Only products in debt (switch, default on). The Ownership group control is GONE (R16) - no control, no chip, no `group` on the wire. Active filters render as the toolbar's existing summary chips, each with its own clear; two or more suppliers render as ONE chip "Suppliers: N"; a due-date range renders as one chip; "Only in debt" shows as a chip only when it is OFF (the default is not a filter the reader needs told about). Refresh happens on window focus through react-query as it does today; no button.
- Columns (R17 supersedes the original list): `Total` after TBA as the LAST column - "No date" and "No location" are GONE from the screen entirely (the row still carries `undated`/`unlocated` on the wire, unchanged, just not rendered). Every month column, TBA and Total declare `footer` reading from `totals`. Footer row labelled "Total" in the product column. The TBA header reads "TBA" literally (R18) - the policy's own `tba_month` is display-only, in the header's `title` tooltip.
- Product cell: name line only when `product_name` is set (BE already nulls equals; FE keeps the guard).
- Cell selection (`hooks/useCellSelection.ts`, local to the screen):
  - pointer down on a value cell + drag past 4px = rectangle select over (row index, column key) across the visible page; plain click still opens the drill (R28 stays).
  - Shift+click extends the rectangle from the anchor; Cmd/Ctrl+click toggles one cell.
  - click on a month header selects that column on the page; click on the `Total` header selects the Total column.
  - Escape or a click outside the table clears.
  - Selected cells get a ring (`ring-1 ring-primary`), tone class kept.
  - A floating summary bar at the bottom of the card while >= 2 cells are selected: `N cells · Sum · Avg · Min · Max`, tabular, signed. Copy button puts the selected values on the clipboard as tab-separated rows (paste into Excel); off a non-secure context (`navigator.clipboard` absent) it falls back to a hidden textarea + `document.execCommand('copy')` (R19), toasting an error only when neither exists.
- `Export` primary button at the right of the toolbar (R12) opens a small popover: split radio (None / Supplier / Category / Supplier x Category), a one-line count ("212 rows, 14 sheets"), and an Export button. Calls the export route with the current filters; on 201 toasts "Export queued, find it in My Downloads" with the drawer link the low stock export uses; disabled while a request is in flight; error via non-sticky toast. The file is downloaded from My Downloads once the worker marks it ready.
- Menu: move the Stock Debt entry in `MENU_SIDEBAR` only (the tree `Demo1Layout` renders) out of Project Demand into Procurement > Supply Chain, after Reorder Planning. Breadcrumb on the page follows the menu.

### Phase order

1. Phase 1 (FE against mocks): filters, Total column + footer, cell selection + summary bar, export popover, menu move, name-equals-code guard. Mock envelope carries `totals`, `suppliers`, `total`.
2. Phase 2 (tester first, then coder): BE params, totals, last supplier map, retail span, export route. Test list in the UAC.
3. Phase 3: reviewer + security-reviewer (new export surface behind the same permission; `supplier_name` is behind `projects.stock_debt.view` only, same exposure as the drill's SPO refs today) + browser pass via sidebar.

## Out of scope

- Low stock report export splitter (second case; lift `split` + the sheet grouping then).
- Cell selection in `DataGrid` proper (same trigger).
- Persisting filters or selection across reloads.
- A per-product "which supplier" override on this screen; the Product-Suppliers screen owns that.

## Open (owner, one line each)

- none. O1 (cutoff field) answered as required date, R11. O2 (toolbar) answered, R13.
