# UAC: Stock Debt - filters, totals, cell summary, workbook export, menu move

Plan: `PLAN-stock-debt-filters-totals-export-24sep.md`
Owner rulings: 24 Sep 2026 (R1-R13, two lavish rounds folded in)

## Backend list read

- AC-1 `GET /project-sales/stock-debt?cutoff=2026-11-30` drops every demand line with `required_date` after 30 Nov 2026. A product whose only open line is due 5 Dec 2026 is not in debt and, with `only_debt=true`, has no row. `months` on the envelope ends at `2026-11`.
- AC-2 With a cutoff, an undated line and an unlocated line still count (`undated`, `unlocated` unchanged). TBA reads 0 when `tba_date_from` is after the cutoff.
- AC-3 A line due 10 Nov, covered by an SPO arriving 20 Nov, ends `late` and books its shortfall in its own month (R37): November reads -20 with `cutoff=2026-11-30` applied, exactly as it does without one - the cutoff prunes DEMAND due after it, it does not change how the walk assigns or which month a covered-but-late line's shortfall lands in.
- AC-4 `supplier_id=<S>` keeps only products whose LAST supplier is S: the supplier on the product's newest purchase-order line (newest by PO issue date, then line created_at; cancelled POs skipped), else the primary-flagged product supplier, else none. `supplier_id=none` keeps only products with neither. A product with a newer SPO from another supplier still files under the PO's supplier.
- AC-4b (regression guard, security review question closed 24 Sep) A newer purchase-order line belonging to another company must never outrank the caller's own in `_last_supplier_map` - measured green on the current SQLAlchemy version (the scope listener's `with_loader_criteria` reaches into the window subquery); `test_last_supplier_stays_within_company_scope` guards it, not a red-before-green pair.
- AC-5 Every row carries `supplier_id`, `supplier_name`, `category_code`, `total`. `total` = sum of the row's `months[].balance` + `tba` + `undated` + `unlocated`.
- AC-6 Envelope carries `totals` = per-month sum over EVERY row of the filtered set (not the page), plus `tba`, `undated`, `unlocated`, `total`. Page 2 returns the same `totals` as page 1.
- AC-7 Envelope carries `suppliers` = distinct `{id, name}` of the filtered set's last suppliers, sorted by name.
- AC-7c (reviewer round) `suppliers` is computed BEFORE the `supplier_id` filter narrows the set, off every OTHER active filter - so applying `supplier_id` still lists every supplier the unfiltered set carries (the select can switch supplier without clearing itself first), and every entry carries a real, non-empty `name`.
- AC-7b Envelope carries `sheet_counts` = `{supplier, category, supplier_category}` sheet counts an export of the current filtered set would produce, none-buckets included. Page 2 returns the same values as page 1.
- AC-8 `book=all` (default) spans flagged project bins AND site pools: a line booked at a pool bin and a line booked at a project bin both appear on the same product row, and pool stock never covers the project line nor project stock the pool line (two lines, two bins, stock only at the pool bin: project line short, pool line covered). `book=project` reproduces today's view exactly. `book=retail` shows only pool-booked demand and pool supply; `group` is ignored under `retail`.
- AC-8b (reviewer round) The seal in AC-8 holds even when the project bin carries NO ownership-group suffix at all (so it cannot be a same-group-label accident): with an unsuffixed flagged bin and a site pool, stock at either bin never covers a line booked at the other, in both directions.
- AC-9 `product_name` is `null` when it equals `product_code` (case-sensitive, trimmed).
- AC-10 Every new field is declared on `StockDebtRow` / `StockDebtList` and asserted by name through the route (response_model drops undeclared fields).
- AC-11 `/stock-debt/{product_id}/cell` accepts `cutoff` and `book` and its lines foot with the cell: a line dropped by the cutoff is not listed.

## Backend export

- AC-12 `POST /project-sales/stock-debt/export` with the list params + `split` creates a `user_downloads` row (`kind=stock_debt_xlsx`, `filename=stock-debt-<ddmmyyyy>.xlsx`, owned by the caller), enqueues `generate_stock_debt_xlsx` on the `imports` queue, and answers 201 with the download row; behind `projects.stock_debt.view` (403 without it).
- AC-12b The task marks the row processing, stores the workbook (`exports/stock-debt-xlsx/<download_id>/<filename>`), marks it ready with `row_count` and `sheet_count`; on any exception it marks the row failed with the message and raises nothing further (same contract as `generate_low_stock_report`). The workbook bytes are built by `StockDebtService.export()`, tested directly for AC-13 to AC-17.
- AC-12c (security review, ruled fix-before-merge) `POST /stock-debt/export` is gated on `require_permission` (JWT only), never `require_permission_with_api_key`: an API-key-only principal (no JWT), even one whose act-as user holds `projects.stock_debt.view`, gets 401/403 and no `user_downloads` row is created. The GET list stays reachable by the same key - it is the read.
- AC-13 `split=none`: one sheet "Stock debt". Header row: Product, Name, Category, Supplier, one per axis month (label `Sep 26` style), TBA, No date, No location, Total. Last row: `Total` in Product, per-column sums. Name cell blank when equal to code.
- AC-13b (security review, ruled fix-before-merge) Every text cell (`Product`, `Supplier`, `Name`, `Category`) is written through the same formula-injection guard the other xlsx exports apply (`proforma_invoice_service._xlsx_safe_text`: a leading apostrophe on anything starting `=`/`+`/`-`/`@`) before it reaches openpyxl - a supplier named `=HYPERLINK("x")` or a product code starting with `+` must not reach the workbook as a live formula.
- AC-14 `split=supplier`: one sheet per last supplier name, plus "No supplier" when any row has none; sheets sorted by title; each sheet has its own Total row.
- AC-15 `split=category`: one sheet per `category_code`, "No category" for blanks.
- AC-16 `split=supplier_category`: one sheet per `<supplier> - <category>` pair, title cut to 31 chars with `[]:*?/\` removed; two pairs that collide after cutting get `(2)`.
- AC-17 Export honours `query`, `group`, `only_debt`, `cutoff`, `supplier_id`, `book` exactly as the list does: the rows in the workbook are the rows the screen shows, unpaged.
- AC-18 (reworded, reviewer round) The ROUTE refuses above `MAX_LOW_STOCK_ROWS` rows SYNCHRONOUSLY, before any `user_downloads` row is created and before anything is enqueued: 422 "Narrow the filters first", no row, no enqueue call. (The service-level `StockDebtService.export()` guard, "Narrow the plan first", is the worker's own backstop and stays; the route no longer waits for it.)
- AC-12d (reviewer round) One in-flight stock-debt export per user (`DownloadService.has_in_flight`, `kind=stock_debt_xlsx`), checked before a second `user_downloads` row is created: a second `POST .../export` while the first is `pending`/`processing` answers 409 and creates no second row.

## Frontend filters and totals

- AC-19 The toolbar carries exactly three controls: Search, Filters (with an active count badge), and a primary `Export` button at the right. No refresh button, no switch on the bar.
- AC-19b The Filters panel holds, in order: Book (All / Project / Retail, default All), Ownership group, Supplier (`SearchableSelect`, clearable, options from `suppliers` plus "No supplier"), Cutoff date (clearable), Only products in debt (switch, default on). The count badge counts Book when not All, group, supplier, cutoff, and "only in debt" when OFF.
- AC-19c Active filters render as chips under the bar, one per filter, each with its own clear; clearing a chip refetches. "Only in debt" chips only when off ("Including covered products").
- AC-20 Book = Retail hides the Ownership group select and clears it.
- AC-21 A `Total` column sits after No location as the last column, right-aligned, signed, no tone; it equals months + TBA + No date + No location for the row.
- AC-22 A footer row labelled `Total` shows `totals` for every month, TBA, No date, No location and Total. It survives paging (same values on page 2).
- AC-23 The product cell shows only the code when `product_name` is null.
- AC-24 Changing any filter resets to page 1 and refetches; the axis (columns) follows the envelope.

## Frontend cell selection

- AC-25 Pointer-down on a value cell and dragging over others selects the rectangle they span; a plain click (no drag) still opens the cell drill.
- AC-26 Shift+click extends the rectangle from the first selected cell; Cmd/Ctrl+click toggles a single cell in or out.
- AC-27 Clicking a month header, TBA, No date, No location or Total header selects that whole column on the page.
- AC-28 With >= 2 cells selected a summary bar shows `N cells`, `Sum`, `Avg`, `Min`, `Max`, signed and tabular; it updates as the selection changes.
- AC-29 Escape, or a click outside the table, clears the selection and hides the bar.
- AC-30 Copy in the bar writes the selected values as tab-separated rows in grid order; pasting into a spreadsheet gives the same rectangle.
- AC-31 Selected cells carry a visible ring and keep their tone; the drill dialog does not open on drag release.
- AC-32 Selection is keyboard-reachable: with focus on a cell, Shift+Arrow grows the rectangle.

## Frontend export

- AC-33 The primary `Export` button opens a popover with split options None / Supplier / Category / Supplier x Category, a line stating rows and resulting sheet count for the current filters, and an Export button.
- AC-34 Export calls the export route with the current filters and the chosen split; on 201 a toast says the export is queued and points at My Downloads (same toast the low stock export uses); the button is disabled while the request is in flight; the file appears in My Downloads and downloads from there once ready.
- AC-35 A failed request shows a non-sticky error toast with the server message; no download row is left in the drawer.

## Menu

- AC-36 Stock Debt is listed under Procurement > Supply Chain, after Reorder Planning, in `MENU_SIDEBAR` (the only tree `Demo1Layout` renders; `MENU_SIDEBAR_COMPACT` and `MENU_MEGA` are unmounted template code and are left untouched), with the same path and permission; it no longer appears under Supply Chain > Project Demand.
- AC-37 Navigating from `/` by sidebar clicks (Procurement > Supply Chain > Stock Debt) lands on the page; breadcrumb reads Procurement > Supply Chain > Stock Debt.

## Layout

- AC-38 At 375px the toolbar wraps, the summary bar stays within the viewport, and the export popover fits; at 1280px nothing clips.

## Test list (Phase 2, tester writes first)

pytest `tests/scm/test_stock_debt_routes.py` (extend) and `tests/scm/test_stock_debt_export.py` (new), on the Postgres fixture, seeding their own product / warehouse / SO / SPO chain: AC-1 to AC-18.
vitest `StockDebtClient.test.tsx` (extend), `useCellSelection.test.ts` (new), `stockDebtService.test.ts` (extend): AC-19 to AC-35 where jsdom can reach; AC-25 to AC-32 with pointer events on the rendered grid.
Browser pass (agent-browser, via sidebar, worker running): AC-36, AC-37, AC-38, plus one drag-select and one export round trip (queue, My Downloads shows ready, file opens with the expected sheets).
