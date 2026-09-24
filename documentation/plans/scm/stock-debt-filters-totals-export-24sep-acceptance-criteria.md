# UAC: Stock Debt - filters, totals, cell summary, workbook export, menu move

Plan: `PLAN-stock-debt-filters-totals-export-24sep.md`
Owner rulings: 24 Sep 2026 (R1-R13, two lavish rounds folded in; R14-R19, owner's hand test
on the live stack, folded in below - see "Owner hand-test round" for the rulings themselves)

## Backend list read

- AC-1 (R14) `GET /project-sales/stock-debt?date_to=2026-11-30` drops every demand line with `required_date` after 30 Nov 2026. A product whose only open line is due 5 Dec 2026 is not in debt and, with `only_debt=true`, has no row. `months` on the envelope ends at `2026-11`. `cutoff` is REMOVED (R14), not aliased.
- AC-1b (R14) `date_from=2026-11-01` drops every demand line due BEFORE it (a line due 20 Oct 2026 is dropped); the axis STARTS at `max(current month, date_from's month)`.
- AC-2 (R14) With a `date_from`/`date_to` range, an undated line and an unlocated line still count (`undated`, `unlocated` unchanged). TBA reads 0 when `tba_date_from` is after `date_to`.
- AC-3 (R14) A line due 10 Nov, covered by an SPO arriving 20 Nov, ends `late` and books its shortfall in its own month (R37): November reads -20 with `date_to=2026-11-30` applied, exactly as it does without one - the range prunes DEMAND outside it, it does not change how the walk assigns or which month a covered-but-late line's shortfall lands in.
- AC-4 (R15) `supplier_ids=<S1>&supplier_ids=<S2>` (repeatable) keeps products whose LAST supplier is ANY of the values passed: the supplier on the product's newest purchase-order line (newest by PO issue date, then line created_at; cancelled POs skipped), else the primary-flagged product supplier, else none. `none` is one more value among the others (not a sentinel that excludes them) - `supplier_ids=none&supplier_ids=<S1>` keeps both the no-supplier products and S1's. A product with a newer SPO from another supplier still files under the PO's supplier. `supplier_id` (singular) is REMOVED, not aliased.
- AC-4b (regression guard, security review question closed 24 Sep) A newer purchase-order line belonging to another company must never outrank the caller's own in `_last_supplier_map` - measured green on the current SQLAlchemy version (the scope listener's `with_loader_criteria` reaches into the window subquery); `test_last_supplier_stays_within_company_scope` guards it, not a red-before-green pair.
- AC-5 (R17) Every row carries `supplier_id`, `supplier_name`, `category_code`, `total`. `total` = sum of the row's `months[].balance` + `tba` ONLY - `undated` and `unlocated` are dropped from `total` (R17: the "No date"/"No location" columns leave the screen and the workbook); the row still carries `undated`/`unlocated` themselves, unchanged.
- AC-6 (R17) Envelope carries `totals` = per-month sum over EVERY row of the filtered set (not the page), plus `tba`, `undated`, `unlocated`, `total`. `totals.total` sums months + tba ONLY (R17, same as AC-5). Page 2 returns the same `totals` as page 1.
- AC-7 Envelope carries `suppliers` = distinct `{id, name}` of the filtered set's last suppliers, sorted by name.
- AC-7c (reviewer round; R15) `suppliers` is computed BEFORE the `supplier_ids` filter narrows the set, off every OTHER active filter - so applying `supplier_ids` still lists every supplier the unfiltered set carries (the select can switch supplier without clearing itself first), and every entry carries a real, non-empty `name`.
- AC-7b Envelope carries `sheet_counts` = `{supplier, category, supplier_category}` sheet counts an export of the current filtered set would produce, none-buckets included. Page 2 returns the same values as page 1.
- AC-8 `book=all` (default) spans flagged project bins AND site pools: a line booked at a pool bin and a line booked at a project bin both appear on the same product row, and pool stock never covers the project line nor project stock the pool line (two lines, two bins, stock only at the pool bin: project line short, pool line covered). `book=project` reproduces today's view exactly. `book=retail` shows only pool-booked demand and pool supply; `group` is ignored under `retail`.
- AC-8b (reviewer round) The seal in AC-8 holds even when the project bin carries NO ownership-group suffix at all (so it cannot be a same-group-label accident): with an unsuffixed flagged bin and a site pool, stock at either bin never covers a line booked at the other, in both directions.
- AC-9 `product_name` is `null` when it equals `product_code` (case-sensitive, trimmed).
- AC-10 Every new field is declared on `StockDebtRow` / `StockDebtList` and asserted by name through the route (response_model drops undeclared fields).
- AC-11 (R14) `/stock-debt/{product_id}/cell` accepts `date_from`/`date_to` and `book` and its lines foot with the cell: a line dropped by the range is not listed. `cutoff` is REMOVED, not aliased.

## Backend export

- AC-12 `POST /project-sales/stock-debt/export` with the list params + `split` creates a `user_downloads` row (`kind=stock_debt_xlsx`, `filename=stock-debt-<ddmmyyyy>.xlsx`, owned by the caller), enqueues `generate_stock_debt_xlsx` on the `imports` queue, and answers 201 with the download row; behind `projects.stock_debt.view` (403 without it).
- AC-12b The task marks the row processing, stores the workbook (`exports/stock-debt-xlsx/<download_id>/<filename>`), marks it ready with `row_count` and `sheet_count`; on any exception it marks the row failed with the message and raises nothing further (same contract as `generate_low_stock_report`). The workbook bytes are built by `StockDebtService.export()`, tested directly for AC-13 to AC-17.
- AC-12c (security review, ruled fix-before-merge) `POST /stock-debt/export` is gated on `require_permission` (JWT only), never `require_permission_with_api_key`: an API-key-only principal (no JWT), even one whose act-as user holds `projects.stock_debt.view`, gets 401/403 and no `user_downloads` row is created. The GET list stays reachable by the same key - it is the read.
- AC-13 (R17) `split=none`: one sheet "Stock debt". Header row: Product, Name, Category, Supplier, one per axis month (label `Sep 26` style), TBA, Total. "No date" and "No location" are GONE from the workbook (R17). Last row: `Total` in Product, per-column sums (months + TBA only, R17). Name cell blank when equal to code.
- AC-13b (security review, ruled fix-before-merge) Every text cell (`Product`, `Supplier`, `Name`, `Category`) is written through the same formula-injection guard the other xlsx exports apply (`proforma_invoice_service._xlsx_safe_text`: a leading apostrophe on anything starting `=`/`+`/`-`/`@`) before it reaches openpyxl - a supplier named `=HYPERLINK("x")` or a product code starting with `+` must not reach the workbook as a live formula.
- AC-14 `split=supplier`: one sheet per last supplier name, plus "No supplier" when any row has none; sheets sorted by title; each sheet has its own Total row.
- AC-15 `split=category`: one sheet per `category_code`, "No category" for blanks.
- AC-16 `split=supplier_category`: one sheet per `<supplier> - <category>` pair, title cut to 31 chars with `[]:*?/\` removed; two pairs that collide after cutting get `(2)`.
- AC-17 (R14/R15/R16) Export honours `query`, `only_debt`, `date_from`, `date_to`, `supplier_ids`, `book` exactly as the list does (never `cutoff`, `supplier_id` or `group` - all three retired from the export body too): the rows in the workbook are the rows the screen shows, unpaged.
- AC-18 (reworded, reviewer round) The ROUTE refuses above `MAX_LOW_STOCK_ROWS` rows SYNCHRONOUSLY, before any `user_downloads` row is created and before anything is enqueued: 422 "Narrow the filters first", no row, no enqueue call. (The service-level `StockDebtService.export()` guard, "Narrow the plan first", is the worker's own backstop and stays; the route no longer waits for it.)
- AC-12d (reviewer round) One in-flight stock-debt export per user (`DownloadService.has_in_flight`, `kind=stock_debt_xlsx`), checked before a second `user_downloads` row is created: a second `POST .../export` while the first is `pending`/`processing` answers 409 and creates no second row.

## Frontend filters and totals

- AC-19 The toolbar carries exactly three controls: Search, Filters (with an active count badge), and a primary `Export` button at the right. No refresh button, no switch on the bar.
- AC-19b (R14/R14c/R15/R16, superseding the original wording; R14b's From/To wording superseded in turn) The Filters panel holds, in order: Book (All / Project / Retail, default All), Supplier (`SearchableMultiSelect`, options from `suppliers` plus "No supplier" - R15, multi), Sales order delivery date (shared range picker, typeable - R14c, one `DateRangePicker` control, DD/MM/YYYY typing, replaces R14b's From/To pair and, before that, the plain Cutoff date), Only products in debt (switch, default on). The Ownership group control is GONE (R16). The count badge counts Book when not All, supplier(s), the delivery date range, and "only in debt" when OFF.
- AC-19c Active filters render as chips under the bar, one per filter, each with its own clear; clearing a chip refetches. "Only in debt" chips only when off ("Including covered products"). Two or more suppliers picked together render as ONE chip "Suppliers: N" (R15); a due-date range renders as one chip "Due: 1 Nov 26 to 30 Nov 26" (R14).
- AC-20 (superseded by R16) Book = Retail no longer needs to hide an Ownership group select - the control does not exist any more.
- AC-21 (R17) A `Total` column sits after TBA as the last column (No date/No location are gone, R17), right-aligned, signed, no tone; it equals months + TBA for the row.
- AC-22 (R17) A footer row labelled `Total` shows `totals` for every month, TBA and Total (no No date/No location, R17). It survives paging (same values on page 2).
- AC-23 The product cell shows only the code when `product_name` is null.
- AC-24 Changing any filter resets to page 1 and refetches; the axis (columns) follows the envelope.

## Frontend cell selection

- AC-25 Pointer-down on a value cell and dragging over others selects the rectangle they span; a plain click (no drag) still opens the cell drill.
- AC-11b (R14/R16, owner hand-test follow-up) The board forwards its OWN `dateFrom`, `dateTo` and `book` into the cell drill it opens - never a group, which R16 already retired from the toolbar. A plain click on a value cell with Due date set to a range and Book set to a non-default value calls `getStockDebtCell(productId, month, dateFrom, dateTo, book)` with the board's own `dateFrom`, not an empty string standing in for a retired group param.
- AC-26 Shift+click extends the rectangle from the first selected cell; Cmd/Ctrl+click toggles a single cell in or out.
- AC-27 (R17) Clicking a month header, TBA or Total header selects that whole column on the page (No date/No location are gone, R17).
- AC-27b (R18) The TBA column header reads "TBA" literally, always - the policy's own `tba_month` (e.g. `2029-01`) is display-only, in the header's `title` tooltip, never the visible column text.
- AC-28 With >= 2 cells selected a summary bar shows `N cells`, `Sum`, `Avg`, `Min`, `Max`, signed and tabular; it updates as the selection changes.
- AC-29 Escape, or a click outside the table, clears the selection and hides the bar.
- AC-30 Copy in the bar writes the selected values as tab-separated rows in grid order; pasting into a spreadsheet gives the same rectangle.
- AC-30b (R19) Copy works without `navigator.clipboard` (the owner reaches the stack over http on a LAN hostname, a non-secure context where the Clipboard API does not exist): it falls back to `document.execCommand('copy')` and still toasts success; when neither exists, a non-sticky error toast, never a thrown exception.
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

## Owner hand-test round (R14-R19, 24 Sep 2026, live stack)

Rulings from the owner's own hand test on the deployed lane stack, folded into the AC ids
above rather than kept as a separate list - each AC line already states which ruling
changed it.

- R14 Date RANGE replaces the single cutoff. Params `date_from` and `date_to` (both
  optional, `YYYY-MM-DD`, on the SO line's required date). A line due before `date_from`
  or after `date_to` is dropped; undated lines are kept; the axis runs from
  `max(current month, date_from's month)` to `date_to`'s month (no `date_to` = today's
  rule). `cutoff` is REMOVED, not aliased.
- R14b (owner, 24 Sep, hand test round 2: the range widget's month arrow is dead inside
  the Filters panel and it cannot be typed) SUPERSEDED by R14c, same day, on sight - the
  owner reversed this ruling before it shipped. Due date is TWO typeable date inputs,
  labelled "From" and "To" - the same `DatePicker` component (`@/components/ui/date-picker`,
  DD/MM/YYYY typing plus a calendar button) the single Cutoff field used before R14, not
  the `DateRangePicker` R14 introduced. Chip reads `Due: 1 Nov 26 to 30 Nov 26` with both
  set, `Due: from 1 Nov 26` with only From set, `Due: to 30 Nov 26` with only To set.
  Clearing the chip clears both inputs. The wire is unchanged by this ruling: the service
  still sends `date_from` / `date_to` exactly as R14 defined them.
- R14c (owner, 24 Sep, reversing R14b on sight: "use the same date range component but I
  can type; I don't want two different date fields; call it sales order delivery date")
  ONE range control again - the shared `DateRangePicker` (`components/ui/date-range-picker.tsx`,
  the same one Sales Orders' "Ordered" filter uses), relabelled "Sales order delivery
  date" (not "Due date"). The shared component itself gains a typeable trigger: the
  Popover/Button trigger becomes a text input showing `DD/MM/YYYY - DD/MM/YYYY`
  (placeholder unchanged), with the calendar icon button beside it, unchanged. Typing a
  full `DD/MM/YYYY - DD/MM/YYYY` and blurring or pressing Enter emits the range; typing a
  single `DD/MM/YYYY` emits `from = to` = that day; text that does not parse leaves the
  value unchanged and restores the previous label on blur; the calendar popover still
  works for click selection; Clear still empties both. Every existing caller
  (`SalesOrdersGrid`'s "Ordered" filter, `RegisterProjectDialog`) gets typing for free,
  no prop change - `from`/`to`/`onChange`/`placeholder`/`disabled`/`className`/`id`/
  `'aria-label'` are untouched. Chip on Stock Debt reads `Delivery: 1 Nov 26 to 30 Nov 26`
  (not `Due:`). The wire is unchanged by this ruling too: `date_from` / `date_to`.
- R15 Supplier is a MULTI select. Param `supplier_ids` (repeatable query param; `none`
  allowed among the values). A product matches when its last supplier is in the set (or
  has none and `none` is in the set). Export body takes `supplier_ids: []`. `supplier_id`
  (singular) is REMOVED, not aliased.
- R16 The Ownership group filter LEAVES the screen. No control, no chip, no `group` sent
  by the FE service. Backend `group` param and its own tests stay untouched - it is still
  a valid (if now FE-unreachable) narrowing.
- R17 The "No date" and "No location" columns LEAVE the screen and the workbook. `total` =
  `months` + `TBA` only. The API row still carries `undated` and `unlocated` (unchanged),
  just not folded into `total` and not rendered as columns.
- R18 The TBA column header reads "TBA" (its `title` tooltip may carry the month), never
  the raw `tba_month` key (e.g. `2029-01`).
- R19 Copy works without `navigator.clipboard` (the owner reaches the stack over http on a
  LAN hostname, not a secure context): falls back to `document.execCommand('copy')`.
- R20 (owner, 24 Sep, second red batch on the cell drill dialog) The Demand grid is
  sortable on every column (client-side over the drill's rows, click a header to toggle
  asc/desc) and carries a search box above it that filters rows by sales order number,
  agent or bin (case-insensitive substring). The tab count follows the filter
  ("Demand (12 of 56)"), and searching resets pagination to page 1.
- R21 The Plan button column leaves the Demand grid entirely.
- R22 Demand columns, in order: Sales order, Agent, Bin, Due, Ordered, Delivered,
  Outstanding, Assigned, From, Status. Ordered = `coalesce(qty_required, qty_ordered)` on
  the SO line (same rule as `plan_qty()`/`demand_qty()`, `app/services/scm/demand.py`),
  Delivered = `qty_delivered`, Outstanding = today's `open_qty` (Ordered minus Delivered,
  floored at 0) - unchanged, just relabelled from "Open". The backend cell line gains
  `qty_ordered` and `qty_delivered`; `open_qty` stays.
- R23 (owner, 24 Sep, third red batch) Stock Debt counts SUPPLY as on hand + SPO only.
  Purchase orders are not supply ("got PO doesn't mean got supply"): no PO event enters
  the stock debt walk, free or pinned, so a line covered only by a PO reads Short, its
  month books the shortfall, and the drill's Supply tab lists no PO rows. The fulfilment
  board and ladder are untouched (they still read PO per plan v7 R29) - this is the Stock
  Debt view's own reading. The `SupplyKind` literal keeps `po` for the shared schema, but
  the stock debt service never emits it.
- R24 Both drill grids carry a Total footer row: Demand totals Ordered, Delivered,
  Outstanding, Assigned; Supply totals Qty, Received, Outstanding and Free (R26 splits
  Supply's own Qty into three fields; the Total row sums all four). Totals are over ALL
  rows of the tab (not the page), and follow the search filter on the Demand tab.
  Addendum (same day): the standalone "Uncovered N" / "Free N" footer LINES under each
  grid retire; their numbers move INTO the Total row instead - Demand's Total carries a
  Short total (sum of `short_qty`) in the Status column, Supply's Total carries Free (sum
  of `free_qty`).
- R25 The tab labels show total QUANTITY, not record count: "Demand (5,619)" = sum of
  Outstanding over the tab's rows (filtered when a search is active,
  "Demand (1,200 of 5,619)"); "Supply (1,000)" = sum of Outstanding (R26 renames Supply's
  own incoming figure Qty to Outstanding once it splits from the raw ordered quantity).
  Backend cell envelope gains `demand_total_qty` and `supply_total_qty` so the FE does not
  sum on its own.
- R26 The drill's Supply tab shows, per SPO row, Qty (the SPO line's ordered quantity),
  Received (quantity received so far) and Outstanding (Qty minus Received). The walk
  counts ONLY Outstanding as incoming supply (received goods are already on hand at the
  bin, so counting them again double-counts) - `ProjectSupplyService._spo_rows` (the R7
  lane, "PO qty_received = SPO transfer") already nets this for assignment, so only the
  two new WIRE fields are new; an on hand row shows Qty only, Received/Outstanding blank.
  Supply columns in order: Kind, Document, Bin, Arrival, Qty, Received, Outstanding,
  Assigned to, Note.
- R27 The drill header never repeats the code: the second line (product name) renders
  only when `product_name` is set AND differs from `product_code` (the BE already nulls
  an equal name on LIST rows, AC-9 - the dialog must not reintroduce the repeat).
- R28 WITHDRAWN by owner, 24 Sep: too confusing. The Supply tab stays as it is - only the
  month's own arrivals, "Nothing arrives here" when none. The From column names where a
  line is covered from; that is where a reader learns a pinned document exists, not the
  Supply tab of a month it never lands in.
- R29 (owner, 24 Sep, fourth red batch) Documents are links and lines are named:
  - A supply event carries `spo_number` and `spo_line_number` (from
    `spo_allocations.spo_line_number`) on the wire; the Document cell reads
    "SPO-2026/06-0131 line 4" and links to
    `/procurement-management/spo-allocations/<encodeURIComponent(spo_number)>` (the page
    reads its param raw, so encode `/` as `%2F`), opening in a new tab. On hand rows are
    not links.
  - A demand line's `assigned_source` (free text) is replaced by `assigned_from:
    [{kind, ref, spo_number, spo_line_number, qty, oi_number, oi_id}]`; the From cell
    renders one linked entry per source, "SPO-2026/06-0131 line 4 (100)", or "On hand
    BRW-BB (14)". Addendum, same day: a placement (`order_inquiry_links`, part of an OI
    row's quantity on one document line, the OI row itself pointing at the SO line) means
    a PINNED source names the order inquiry it came through - `oi_number`/`oi_id` on the
    entry, rendered "... via OI-2026/09-0012" with the OI part linking to
    `/project-sales/order-inquiries/<oi_id>` (new tab). A free (walk-assigned) source or
    an on-hand source carries both `null` and renders with no "via".
  - Supply's own "Assigned to" entries carry `line_no` (the SO line's own number) and
    render "SO382618 line 2 (100)"; the Sales order cell on Demand links to
    `/scm/sales-orders/<sales_order_id>` (a new `sales_order_id` field on the demand
    line), new tab.
- R30 (owner, 25 Sep: "I was expecting us to use the same component as OI") supersedes
  R29's RENDERING of documents - the R29 WIRE fields (`assigned_from`, `spo_number`,
  `spo_line_number`, `oi_number`, `oi_id`, `line_no`, `sales_order_id`) all stay, only how
  the dialog draws them changes. The drill renders documents exactly the way the OI lines
  grid does: `OrderInquiryDocumentLink` (`order-inquiries/components/
  OrderInquiryDocumentDialog.tsx`, kind `'spo' | 'po'`, `document`, `poId`; opens the
  document's lines in a dialog in place, testid `document-detail-trigger-<document>`),
  the same cell shape `orderInquiryHeaderLinesColumns.tsx:DocumentCell` uses (dash when
  none).
  - Demand columns, in order: Sales order, Agent, Bin, Due, Ordered, Delivered,
    Outstanding, Assigned, From, SPO, OI, Status. From now holds ONLY on-hand text
    ("On hand BRW-BB (14)") or a dash - the document half moves out. SPO =
    `OrderInquiryDocumentLink` for the FIRST spo entry in `assigned_from`, followed by
    muted " line 4 (100)". OI = the OI number, linking to
    `/project-sales/order-inquiries/<oi_id>` (the PAGE, since no OI dialog exists), a
    dash when `oi_id` is null. No inline "via" anywhere any more.
  - Supply columns unchanged in order, but Document = `OrderInquiryDocumentLink` kind
    `'spo'` plus muted " line N"; on hand rows keep plain text.
  - The Sales order cell keeps its page link (R29, unchanged).
- R31 (owner, 25 Sep) supersedes R30's three Demand columns.
  - R31a Demand grid: ONE column "Covered by" in place of From / SPO / OI. Content:
    "On hand BRW-IB" plain text for on hand (no quantity suffix - R30's had one), the
    `OrderInquiryDocumentLink` (document number only, no "line N (qty)" suffix - R30's
    had one) for an SPO source, both when a line drew from both (on hand text then the
    link), a dash when nothing. The OI column goes entirely; `oi_number`/`oi_id` stay on
    the wire, unused by the drill. Supply's own Document cell drops its muted " line N"
    suffix too - the link alone, matching the OI lines grid's own `DocumentCell` exactly.
  - R31b When the document dialog opens from the drill, it INDICATES which of its lines
    are linked to the SO line that opened it, and offers a one-click jump:
    `OrderInquiryDocumentLink`/`OrderInquiryDocumentDialog` gain an optional
    `highlightLines: number[]` (SPO line numbers) - the dialog marks those rows (a
    "Linked" badge) and shows a "Go to linked line" button in its header that pages the
    first highlighted row into view (reusing `PanelDataGrid`'s own `focusRowId`
    mechanism, already built for exactly this "jump to the page holding a named row"
    case - no new machinery). The OI lines grid keeps passing nothing, unchanged. The SPO
    detail payload (`getOrderInquirySpoDetail`) gains each line's own `spo_line_number`,
    declared on `OrderInquirySpoDetailLine` - it did not carry the field at all before.

## Test list (Phase 2, tester writes first)

pytest `tests/scm/test_stock_debt_routes.py` (extend) and `tests/scm/test_stock_debt_export.py` (new), on the Postgres fixture, seeding their own product / warehouse / SO / SPO chain: AC-1 to AC-18.
vitest `StockDebtClient.test.tsx` (extend), `useCellSelection.test.ts` (new), `stockDebtService.test.ts` (extend), `stockDebtService.real.test.ts` (extend): AC-19 to AC-35 where jsdom can reach; AC-25 to AC-32 with pointer events on the rendered grid; R14-R19 (date range, multi supplier, no group, no undated/unlocated columns, TBA label, copy fallback).
Browser pass (agent-browser, via sidebar, worker running): AC-36, AC-37, AC-38, plus one drag-select and one export round trip (queue, My Downloads shows ready, file opens with the expected sheets).
