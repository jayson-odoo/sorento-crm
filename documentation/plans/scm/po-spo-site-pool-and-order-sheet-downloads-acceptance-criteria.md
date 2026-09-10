# UAC - PO / SPO read at the site pool everywhere, and the order sheet lands in My Downloads

Plan: `PLAN-po-spo-site-pool-and-order-sheet-downloads.md` (same folder).
Owner ruling, 10 Sep 2026: "PO & SPO are purely based on site pool location, which majority
is BRW, so be it the cell, the modal, the quantity we display in the exported excel, it should
and must be based on site pool location and should tally." Plus: "our export of the excel and
pdf needs to use My Downloads process, similar to other downloading buttons."

## Journey

The buyer opens a plan (Procurement > Supply Chain > Reorder Planning > a run). Every row
shows an SPO figure and a PO figure. Those two numbers answer one question: how much of this
product is already on its way to a SITE POOL, the stock the buyer may sell from. A project
bin's PO or SPO is that project's, already linked from its Order Inquiry, and never counts.

1. The buyer reads SPO 40 / PO 42 on a row. Clicks SPO: the modal lists the open allocations
   at site-pool warehouses, and their still-to-come quantities sum to 40. Clicks PO: the
   modal lists the open PO lines to site-pool warehouses, summing to 42. History tabs list
   what landed / was bought at those same warehouses.
2. The Suggested qty was sized against those same figures. Nothing at a project bin nets the
   buy down.
3. The buyer picks Actions > Order sheet Excel (or PDF). A toast says the sheet is being
   prepared and will appear in My Downloads. The header badge counts it; the drawer shows it
   as preparing, then ready; the buyer downloads it from there, the same as a complaint PDF.
4. On the sheet, "BRW incoming qty" and "BRW PO qty" print the same numbers the grid's SPO and
   PO cells showed for that product on that run.

Decisions the buyer makes: none new. Everything is derived from the run.

## Site pool - the one rule

`app/services/scm/pool_predicate.py` (`active_site_pool_sql` / `ACTIVE_SITE_POOL_SQL`): a
warehouse that `is_active` and whose `COALESCE(segment, 'dealer') <> 'project'`. On the prod
copy that is the pool heads (BRW, MWH, WH3, DC1, HQ, DISPLAY ...); every `BRW-BB`, `BRW-IR`,
`BRW-SYNT` ... bin is `project`. Product-wide: a product-grain row reads every active
site-pool warehouse, not only the ones in its plan basis, so a warehouse that holds only a PO
line still counts. A location-grain row reads its own warehouse when it is site pool, else 0.

## Phase 2 - backend, test-first

### Slice S1 - the cell, the drill and the netting

- **AC-1 [BE]** Given SPO allocations still to come of 96 at BRW-BB (project bin) and 40 at
  BRW (site pool) for one product, when the run is planned at product grain, then the row's
  `incoming_spo` is 40.
- **AC-2 [BE]** Given open PO lines of 400 to BRW-IR (project bin) and 42 to BRW for one
  product, then the product-grain row's `outstanding_po` is 42.
- **AC-3 [BE]** Given a site-pool warehouse (BRW) that holds ONLY an open PO line for the
  product (no stock row, no SPO, no committed SO), then that PO still counts in the row's
  `outstanding_po` (product-wide read, not plan-basis only).
- **AC-4 [BE]** Given a product whose only supply is 500 SPO at a project bin and retail
  committed of 100 at BRW with 0 on hand, then the plan sizes a Buy (the bin SPO no longer
  nets the retail need to zero). The same product with the 500 SPO at BRW is covered.
- **AC-5 [BE]** Given a location-grain row at BRW-BB (project bin), then its `incoming_spo`
  and `outstanding_po` are 0; the same row at BRW reads BRW's own figures.
- **AC-6 [BE]** The Net drill for a product-grain row (`position_drill`, the on hand /
  on order / PO / committed legs) sums the same site-pool scope, so
  `on_hand + on_order + po_ordered - committed == net` still holds on a product with bin SPO.

### Slice S2 - the two modals read what the cell summed

- **AC-7 [BE]** `GET /reorder-runs/{run}/spo-history?product_id=` Open tab: allocations at
  active site-pool warehouses for the product, product-wide, any grain. The sum of
  `qty - received_qty` over Open rows equals the row's `incoming_spo` (AC-1 data: one row,
  BRW, 40; the BRW-BB allocation is absent from both tabs).
- **AC-8 [BE]** Same endpoint, History tab: landed / fully received / closed allocations at
  site-pool warehouses only.
- **AC-9 [BE]** `GET /reorder-runs/{run}/po-book`: a product-grain row's key `<pid>:` carries
  every open PO line to an active site-pool warehouse for that product; `remaining` sums to
  the row's `outstanding_po` (AC-2 data: one line, BRW, 42). A location-grain row keeps its
  own-warehouse pairing but only when that warehouse is site pool. The P8 project-only
  exclusion (a row with project committed and no retail committed serves no receipts) is
  unchanged - a test asserts it still holds.
- **AC-10 [BE]** `GET /reorder-runs/{run}/purchase-trend` with no `warehouse` param returns
  the product's purchase history to active site-pool warehouses (product-wide); with
  `warehouse=<code>` it keeps today's single-warehouse read.
- **AC-11 [FE]** `PoTabs` on a product-grain row (no pool code) calls the purchase-trend read
  without a warehouse instead of skipping the call; the History tab is no longer 0 by
  construction. `SpoTabs`/`PoTabs` tab labels drop the `to <pool>` suffix when the row has no
  pool code (nothing to name).
- **AC-12 [FE]** Cover "From PO (open N)" on a product-grain row equals the row's PO cell
  (both read the same po-book key).

### Slice S3 - the order sheet tallies with the grid

- **AC-13 [BE]** For every product on a run, the frozen `incoming_spo_qty` equals the run's
  row `incoming_spo` and `po_open_qty` equals `outstanding_po` (one shared read, or a parity
  test over a seeded product with supply at a bin and at BRW).
- **AC-14 [BE]** Existing sheet column tests (`tests/scm/test_order_summary_sheet.py`,
  `test_order_summary_supply_docs.py`) stay green - the sheet's rule did not move.

### Slice S4 - export through My Downloads

- **AC-15 [BE]** `POST /api/v1/scm/order-summary/export` body `{run_id, format}`
  (`pdf|xlsx`): creates a `user_downloads` row (`kind` = `order_sheet_pdf` /
  `order_sheet_xlsx`, `source_entity_type` = `reorder_run`, `source_entity_id` = run id,
  `filename` = `order-sheet-<as_of ddmmyyyy>.<ext>`), enqueues `generate_order_sheet` on the
  `imports` queue, returns the `DownloadResponse` in `pending`. Enqueue failure marks the row
  failed and answers 503.
- **AC-16 [BE]** Guards run BEFORE a row is created, synchronously: unknown format 422,
  malformed / invisible run 404, more than `_MAX_EXPORT_ROWS` rows to order 422 "Narrow the
  plan first" - the existing messages, unchanged.
- **AC-17 [BE]** `generate_order_sheet(download_id, run_id, fmt, user_id)` in
  `app/tasks/export_tasks.py`: `mark_processing`, renders via `export_report`, uploads to
  `exports/order-sheet/{download_id}/{filename}` on the default provider, `mark_ready` with
  the content type's filename. Any exception (WeasyPrint unavailable included) → `mark_failed`
  with the message; never raises into RQ.
- **AC-18 [BE]** The synchronous `GET /api/v1/scm/order-summary/export` is removed; a GET
  answers 405. One path.
- **AC-19 [FE]** Actions > Order sheet PDF / Excel call the POST through a mutation hook; on
  success invalidate `['my-downloads']` and `['entity-downloads', 'reorder_run', runId]` and
  toast "Preparing the order sheet - it will appear in My Downloads." No blob is saved; the
  `saveBlobAs` import leaves `summaryOrderService.ts`.
- **AC-20 [FE]** On error the toast carries `extractApiError`'s message (the 422 "Narrow the
  plan first" text reaches the buyer).
- **AC-21 [FE]** Both menu items disable while a request is in flight (double click = one
  row).

## Phase 3 - browser evidence [E2E]

- **AC-22 [E2E]** Local plan, a product with SPO at a project bin and at BRW: the SPO cell
  shows the BRW figure; the modal's Open rows sum to it; the PO modal likewise. Screenshots
  under `documentation/plans/scm/evidence/po-spo-site-pool/`.
- **AC-23 [E2E]** Actions > Order sheet Excel: toast, header badge increments, drawer row goes
  preparing → ready (worker running), the downloaded workbook opens and its BRW PO qty for that
  product equals the grid's PO cell.

## Out of scope (backlog)

- "Dealer o/s" vs grid "Retail" on the sheet - separate ruling pending
  (`documentation/backlogs/backlog.md`).
- An `EntityDownloadsButton` chip on the plan header.
