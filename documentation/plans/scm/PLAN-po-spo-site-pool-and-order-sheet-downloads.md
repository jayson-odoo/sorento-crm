# PLAN - PO / SPO read at the site pool everywhere, and the order sheet lands in My Downloads

Status: building (owner go 10 Sep 2026 via lavish markup: assumptions 1, 2, 3 all confirmed, "good to go").
UAC: `po-spo-site-pool-and-order-sheet-downloads-acceptance-criteria.md` (same folder).
Domain: scm. Lane branch: `feat/po-spo-site-pool-downloads`. One lane, one PR.

## The problem, measured (local 0907 prod copy, plan 00788044 of 10 Sep 10:10)

Row SRTWC8605-SC-RL: grid SPO 96 (all at BRW-BB, a project bin), PO 934; SPO modal
"Open (0) - Nothing on the water", PO modal "Open (0) History (0)". Prod B2155-NL-BLUE: SPO
8,000 / PO 4,000, both modals empty.

Three readers, three scopes, none the site pool:

| Reader | Scope today | Where |
| --- | --- | --- |
| Cell SPO / PO | sum over EVERY plan-basis location, project bins included | `reorder_run_service._planning_rows` row SQL (`np.on_order`, `po.ordered`, ~L926-943), summed per product by `_total()` in `_product_agg_cell` (~L2033-2045) |
| SPO modal | allocations at pool HEAD ids only, resolved off the rec's warehouse / plan-basis pools | `spo_supply.spo_history_for_product` |
| PO modal Open + Cover "From PO" | PO book paired on the rec's OWN `warehouse_id`; product-grain rec has none, so the key `<pid>:` never exists | `po_book_service._PO_BOOK_SQL`, FE `usePlanLines.poFor` |
| PO modal History | purchase-trend for ONE warehouse = the row's `pool_warehouse_code`; product-grain rows carry none, FE skips the call | `purchase_trend_service.purchase_trend_for_run(warehouse_id=)`, FE `getPoHistoryToPool` |
| Sheet "BRW PO qty" / "BRW incoming qty" | active site pool, product-wide | `summary_order_service._po_open_qty_map` / `_incoming_spo_qty_map` - already right |

The netting is also wrong by the same rule: `net = net_position + po_ordered` (~L2117) and
`np.on_order` inside `net_position` count bin supply, while `on_hand` was already gated to the
site pool (R19). A project bin's PO/SPO belongs to its Order Inquiry (P8) and must not net a
retail buy down.

## Assumptions (owner to confirm; the plan proceeds on them)

1. **Site pool = `pool_predicate.active_site_pool_sql`** - active and not `segment=project`.
   On the data that is the pool heads (BRW, MWH, WH3, DC1, HQ, DISPLAY, DEFECT ...). No new
   predicate; the sheet already uses this one.
2. **Product-wide, not plan-basis.** A product-grain row reads every active site-pool
   warehouse the product has supply at, so a warehouse holding only a PO line still counts and
   the modal can never list a document the cell did not sum.
3. **The engine's netting follows.** Bin SPO/PO drop out of `net`, so some rows that read
   "covered by a bin SPO" will now suggest a Buy. Owner said "so be it the cell".

## Design - simplest thing that works

**One read, three callers.** The sheet's two maps already state the rule; promote them to a
shared module and have the engine, the modals and the PO book call the same functions:

- New `app/services/scm/site_pool_supply.py` holding `open_spo_by_product(db, product_ids)`
  and `open_po_by_product(db, product_ids)` - moved verbatim from
  `summary_order_service._incoming_spo_qty_map` / `_po_open_qty_map` (+ `_grouped_supply_map`),
  each row also carrying `warehouse_code`, `expected_date`, `status`, `supplier_name` so a
  modal can list rows and a sheet can print totals off the same result. `summary_order_service`
  imports them back (no behaviour change there, AC-14).
- **Engine (S1):** in `_planning_rows`'s SQL, gate `np.on_order` and `po.ordered` with the same
  `is_dealer_expr` CASE that gates `quantity_on_hand`, and fold that into `net_position_col`.
  Per-location cells then read 0 at a bin (AC-5), `_total()` over cells gives the site-pool
  sum, and `net`/`retail_net` follow with no further change. For AC-3 (a site-pool warehouse
  present only in `po_ordered_v`, absent from `net_position_v`'s keys), add `po_ordered_v` to
  the `keys` UNION of `scm.net_position_v` (new migration, view replace; no data). `explain_net`
  (~L3204) applies the same gate by joining `warehouses` in its two sums (AC-6).
- **SPO modal (S2):** `spo_history_for_product` drops the pool-id resolution and filters on
  `active_site_pool_sql("warehouses")` product-wide, keeping `visible_line_clauses` and the
  open/history split (AC-7, AC-8).
- **PO book (S2):** `_PO_BOOK_SQL` pairs become `(product_id, key_warehouse)`: for a rec with
  `warehouse_id IS NULL` the key is `''` and the lines are every open line to an active
  site-pool warehouse; for a location rec the key is its own warehouse and the line must be
  to it AND that warehouse must be site pool. P8 exclusion untouched (AC-9). FE `poFor` needs
  no change - the `<pid>:` key now exists (AC-12).
- **PO history (S2):** `purchase_trend_for_run(warehouse_id=None)` reads site-pool
  warehouses instead of "any warehouse"; the route keeps `warehouse=` as an optional narrowing.
  FE `getPoHistoryToPool` stops returning early on a null code (AC-10, AC-11).
- **Sheet parity (S3):** one pytest seeding a product with SPO+PO at a bin and at BRW, planning
  a run, freezing the sheet, asserting cell == frozen == modal sums (AC-13).
- **Export (S4):** copy the complaint-PDF chain exactly. `POST /order-summary/export`
  (`app/api/v1/scm/order_summary.py`) runs the existing guards, then
  `DownloadService.create(kind=order_sheet_<fmt>, source_entity_type="reorder_run", ...)` and
  `enqueue_job(generate_order_sheet, ..., queue_name="imports", job_timeout=600)`. Task
  `generate_order_sheet` in `app/tasks/export_tasks.py` mirrors `generate_complaint_pdf`
  line for line (`mark_processing` → `export_report` → upload `exports/order-sheet/...` →
  `mark_ready`; `_record_failure` on any exception). The GET route is deleted (AC-18). FE:
  `exportOrderSheet(runId, format)` in `summaryOrderService.ts` posts; `useExportOrderSheet`
  mutation in the reorder hooks invalidates the two download keys and toasts (AC-19..21);
  `ReorderPlanView.orderSheet` calls the mutation. `saveBlobAs`/`filenameFromContentDisposition`
  imports go.

No registry, no flag, no config. Two new functions in one module, one view migration, one
task, one route swapped GET → POST.

## Slices

| Slice | Scope | Phase |
| --- | --- | --- |
| S4-FE | `useExportOrderSheet` + service + Actions wiring against a mocked POST | Phase 1 (frontend-first, mocks) |
| S1 | engine gate + view migration + `explain_net` | Phase 2, tester-first |
| S2 | `site_pool_supply.py`, SPO modal, PO book, purchase-trend + FE history call | Phase 2 |
| S3 | sheet imports the shared read; parity test | Phase 2 |
| S4-BE | POST route + task; GET removed | Phase 2 |
| S5 | reviewer + security-reviewer (file storage path touched) + browser evidence AC-22/23 | Phase 3 |

Worker restart is required after S4-BE (`app/tasks/*` edit).

## Captain's test list (tester writes these red, one per UAC id)

- AC-1 `test_product_grain_spo_cell_counts_site_pool_only` - seed SPO 96 @BRW-BB, 40 @BRW; plan; `incoming_spo == 40`.
- AC-2 `test_product_grain_po_cell_counts_site_pool_only` - PO 400 @BRW-IR, 42 @BRW; `outstanding_po == 42`.
- AC-3 `test_po_only_site_pool_warehouse_still_counts` - BRW has a PO line and no stock/SPO/SO row; `outstanding_po` includes it.
- AC-4 `test_bin_spo_no_longer_covers_a_retail_need` - 500 SPO @BRW-BB, retail committed 100 @BRW, on hand 0 → a Buy rec; move the SPO to BRW → covered.
- AC-5 `test_location_grain_row_at_a_bin_reads_zero_supply`.
- AC-6 `test_explain_net_legs_sum_to_net_with_bin_spo_present`.
- AC-7 `test_spo_history_open_rows_sum_to_the_cell` - modal Open rows == [BRW 40], BRW-BB absent.
- AC-8 `test_spo_history_history_tab_is_site_pool_only`.
- AC-9 `test_po_book_serves_the_product_grain_key_with_site_pool_lines` + `test_po_book_keeps_p8_project_only_exclusion` + `test_po_book_location_row_at_a_bin_serves_nothing`.
- AC-10 `test_purchase_trend_without_warehouse_reads_site_pool` + `..._with_warehouse_keeps_single_read`.
- AC-11 vitest `PlanRowDialogs.poTabs.test.tsx`: product-grain line → `getPoHistoryToPool` called with null code and the fetch fires; labels carry no "to".
- AC-13 `test_sheet_supply_columns_equal_the_grid_cells` (parity).
- AC-15 `test_export_post_creates_download_row_and_enqueues` (kind, source_entity, filename, queue `imports`, response pending).
- AC-16 `test_export_post_guards_run_before_a_row_exists` (422/404/422, `user_downloads` count unchanged).
- AC-17 `test_generate_order_sheet_marks_ready` + `test_generate_order_sheet_marks_failed_when_render_raises` (patch `export_report`).
- AC-18 `test_export_get_is_gone` (405).
- AC-19..21 vitest `ReorderPlanView.orderSheet.test.tsx` (rewritten): POST called, both query keys invalidated, toast text, items disabled while pending; `summaryOrderService.test.ts`: `exportOrderSheet` posts `{run_id, format}` and no blob API is touched.

## Evidence

`documentation/plans/scm/evidence/po-spo-site-pool/` - AC-22 / AC-23 screenshots.

## Backlog

- Sheet "Dealer o/s" (all open retail SO, all time) vs grid "Retail" (`retail_need`,
  horizon-windowed and netted) - ruling pending, separate lane.
