/**
 * ============================================================================
 * SCM Purchasing and Fulfilment - SUMMARY ORDER REPORT service (UAC Group C2/C3)
 * ============================================================================
 * Layering: hooks (useSummaryOrder) -> THIS service -> lib/api-client -> backend.
 *
 * Phase 1: both branches are present. While `USE_SUMMARY_ORDER_MOCKS` (in
 * `lib/summaryOrderMockStore.ts`) is true every function serves the deterministic
 * fixture and NO request is made. The real `apiFetch` + `extractApiError` branch
 * below is written and unreachable, so Phase 2 is a flag flip plus deleting the
 * mock store - not a rewrite of this file.
 *
 * -- PHASE-2 BACKEND CONTRACT ------------------------------------------------
 * Mounted under `require_module_enabled_with_api_key("scm")`, alongside the other
 * flat SCM routes (`/reorder-runs`, `/coverage`, `/recommendations/{id}/explain-net`).
 * No nested `reorder/` segment: nothing else in the domain has one.
 *
 * Params are HUMAN CODES throughout - `product_code`, `supplier_code`, SO numbers,
 * pool codes. `run_id` is the single id on the wire and it is opaque: it says
 * which week's report is being read (AC-C2.9) and is never rendered.
 *
 * 1) The report, one row per product, network wide
 *
 *      GET /api/v1/scm/order-summary
 *          ?run_id=<opaque>          optional; omitted = the newest COMPLETED run
 *
 *      -> 200  OrderSummaryReport    (see `types/summaryOrder.types.ts` - that file
 *                                     is the field-for-field contract and is NOT
 *                                     restated here)
 *      Auth: `scm.dashboard.view` (read-only), matching `explainer.py`.
 *
 *    `run_id` alone is what makes a past week reproducible (AC-C2.9). The report is
 *    FROZEN by the run that produced it, so naming the run returns what the decider
 *    saw rather than a recomputation against today's book - which is why there is no
 *    `as_of` parameter: the response STATES the date it was frozen for, and a caller
 *    passing a different one would only mislabel a fixed position. Both `as_of` and
 *    `generated_at` are null for a run that froze no rows, because inventing today's
 *    date would label a book that was never built.
 *
 *    Stage 2 adds to the same response and changes no key: the report carries the
 *    run's stamped `decision_grain` and `is_legacy` (AC-F01 / AC-F10), and each row
 *    carries `project_buy_qty`, `retail_replenishment_qty`, `unclassified_demand_qty`,
 *    `earliest_project_need_date`, `uom_decimal_places`,
 *    `location_allocations`, and `retail_outstanding` (+ its line count) as the API
 *    name of the stored `dealer_outstanding` column (AC-E03). One row per product,
 *    still: channel is analysis inside the row, never part of row identity.
 *
 *    On a LEGACY run - one created before the front-planning contract - every one of
 *    those channel fields is null and `is_legacy` is true. They are NOT inferred and
 *    NOT backfilled (AC-F10), and the decision route refuses the run entirely.
 *
 *    The report is returned WHOLE and the client paginates, because the sheet it
 *    replaces is read as one book. If the row count makes that untenable (roughly
 *    3,100 products carry a recommendation today), add `page` / `limit` here and
 *    switch the grid to `manualPagination`; the row shape is unaffected either way.
 *
 *    Three nullable fields are load-bearing and must NOT be defaulted to 0 by the
 *    server. `avg_daily_demand` is absent for roughly 38% of the book and
 *    `unit_volume_cbm` for roughly 84% (no recorded dimensions); `max_days_outstanding`
 *    is absent when nothing is outstanding. A zero would be read as "already out of
 *    stock" and "no space needed", both of which are decisions taken on a figure
 *    nobody measured. Send null and the screen names the missing input.
 *
 * 2) The lines behind one aggregate, fetched lazily when its icon is opened
 *
 *      GET /api/v1/scm/order-summary/{product_code}/demand
 *          ?kind=project|retail|unclassified   required
 *                                    (`dealer` accepted as an alias of `retail`)
 *          &run_id=<opaque>          optional; same run as the report
 *
 *      -> 200  OrderSummaryDemandDrill
 *      Auth: `scm.dashboard.view`.
 *
 *    **The server owns the ordering.** `kind=retail` returns lines sorted
 *    worst-first by `days_outstanding` (AC-C2.4); `kind=project` by
 *    `required_date`, nulls last; `kind=unclassified` by `ordered_date`, oldest
 *    first. The client never re-sorts, so the ageing a person reads is the ageing
 *    the server computed.
 *
 *    Project lines carry `line_no`, `warehouse_code` and a HUMAN `decision_ref`
 *    ("Rev 2 / INQ-2026-0188") so Purchasing can trace a Buy back to the decision
 *    that produced it without a UUID crossing the wire (AC-D06 / AC-E07).
 *
 *    `total_qty` must equal the row's aggregate. The row figure is derived from
 *    these lines and never retyped by a person (AC-C2.3).
 *
 * 2b) The member locations behind one product row (AC-F08)
 *
 *      GET /api/v1/scm/order-summary/{product_code}/locations
 *          ?run_id=<opaque>          optional; same run as the report
 *
 *      -> 200  OrderSummaryLocations
 *      Auth: `scm.dashboard.view`.
 *
 *    One row per member location, carrying its Project / Retail / Unclassified
 *    demand split beside the SHARED supply of that product-location - stock,
 *    incoming SPO, PO, reorder level - which is counted ONCE and carries no
 *    channel dimension (AC-F07). `allocated_qty` is that location's share of the
 *    chosen quantity, and the shares sum EXACTLY to `chosen_qty` (AC-F12).
 *
 *    On a legacy run every channel figure is null and `is_legacy` is true; the
 *    breakdown is not inferred or backfilled (AC-F10).
 *
 * 3) The supplier candidates for one product
 *
 *      GET /api/v1/scm/order-summary/{product_code}/suppliers
 *
 *      -> 200  OrderSummarySuppliers
 *      Auth: `scm.dashboard.view`.
 *
 *    `is_stale` is the SERVER's verdict on `last_po_date` against
 *    `stale_after_days` (AC-C2.6), not a client threshold, so the flag cannot
 *    drift between screens. `delivered_line_count` of 0 means the supplier has
 *    never delivered THIS item and must be sent as 0 rather than omitted, because
 *    the screen has to say so instead of letting a low cost make them look cheap
 *    (AC-C2.5). Both costs are ex-works in `currency` (AC-C3.4).
 *
 * 4) Record the order-quantity decision
 *
 *      POST /api/v1/scm/order-summary/{product_code}/decision
 *          { run_id, chosen_qty, supplier_code }
 *
 *      -> 200  OrderSummaryDecisionResult
 *      Auth: `scm.reorder.run` (this one writes).
 *
 *    `chosen_qty` ABOVE the shortfall is valid and must not be rejected or warned
 *    on (AC-C2.7). The server keeps `suggested_qty` beside it and stamps
 *    `decided_by` + `decided_at`, so a larger number is a decision on the record
 *    rather than an untraceable override (AC-C2.8). `decided_by` is a human name;
 *    no user id crosses the wire.
 *
 *    Two refusals are Stage 2's, and they are DIFFERENT statuses because they are
 *    fixed in different places:
 *
 *      422  `chosen_qty` carries more fractional digits than the row's FROZEN
 *           `uom_decimal_places` permits (AC-F12). Fixed by typing a coarser
 *           quantity - `2.5 EA` is refused, `2.5 kg` at 3 places is accepted.
 *      409  the run's stamped `decision_grain` is not `product`, or the run is
 *           legacy (AC-F09 / AC-F10). Fixed by deciding on the grain that owns
 *           the run, or by creating a new run. Not fixable by editing the field,
 *           which is why the screen disables the control rather than letting the
 *           write fail.
 *
 *    The response carries `location_allocations`: the allocator rerun's split of
 *    the accepted quantity back to the frozen location inputs, in the UOM's integer
 *    minor units, summing exactly to `chosen_qty` (AC-F12). No rescaling formula.
 *
 * 5) The sheet, through My Downloads (S4, PLAN-po-spo-site-pool-and-order-sheet-downloads)
 *
 *      POST /api/v1/scm/order-summary/export
 *          { run_id: <opaque>, format: 'pdf' | 'xlsx' }
 *
 *      -> 200  DownloadResponse (`MyDownload`, `status: 'pending'`) - a `user_downloads`
 *              row was created and `generate_order_sheet` enqueued on the `imports` queue.
 *              The sheet itself never crosses this response; it lands in My Downloads
 *              (AC-19) the same way a complaint PDF does.
 *      -> 422  an unrecognised `format`, a malformed/invisible run, or too many rows to
 *              order ("Narrow the plan first") - the SAME messages the old synchronous
 *              export used, unchanged (AC-16, AC-20).
 *      -> 404  the run does not exist / is not visible to this user.
 *      Auth: `scm.dashboard.view`, the same read-only permission as the report itself -
 *      exporting states nothing new, it only prints what (1) already answers.
 *
 *    Same NINE columns the report grid renders (AC-S9.2): Item, On hand, Project qty,
 *    Dealer o/s, Order qty, Delivery, Project / customer, Supplier, Remarks. `Order qty`
 *    is the chosen quantity, blank when nobody has decided one yet - the pen column,
 *    exactly as the printed sheet leaves it. PDF is landscape A4 through
 *    `app.services.pdf_render`; xlsx is an openpyxl workbook built in
 *    `summary_order_service` (`xlsx_renderer`'s fixed table shape did not fit the sheet).
 *
 * 6) The low stock report, through the SAME export endpoint (S4, PLAN-low-stock-report;
 *    split added PLAN-low-stock-export-split-25sep)
 *
 *      POST /api/v1/scm/order-summary/export
 *          { run_id: <opaque>, format: 'low_stock_xlsx', split: 'none' | 'supplier' |
 *            'category' | 'supplier_category' }
 *
 *      -> 200  DownloadResponse (`MyDownload`, `status: 'pending'`) of kind
 *              `low_stock_xlsx`, filename `low-stock-<as_of ddmmyyyy>.xlsx`,
 *              `source_entity_type: 'reorder_run'` - a `user_downloads` row was created
 *              and `generate_low_stock_report` enqueued on the `imports` queue (AC-30).
 *      -> 422  too many rows for this kind ("Narrow the plan first" - its OWN cap,
 *              `MAX_LOW_STOCK_ROWS = 5000` on the "All" sheet, not the order sheet's 2000),
 *              a malformed/invisible run, an unknown `split`, or `split` = "supplier" /
 *              "supplier_category" on a run whose Supplier column is withheld (R5).
 *      -> 409  one export of this kind is already in flight for this user and run
 *              (unchanged by `split` - A6, no per-split guard).
 *      Auth: `scm.dashboard.view`, as the order sheet.
 *
 *    The workbook carries TWO sheets under `split: 'none'` (the default), "Low stock" then
 *    "All", sixteen columns each: Item code, Description, Category, BRW on hand, Reorder
 *    level, Reorder qty, Suggested qty, Suggestion, Order qty, Dealer o/s, Supplier, BRW PO
 *    qty, BRW incoming qty, Last in qty, Last in date, Remarks (AC-31). Neither sheet drops
 *    the rows the plan hides by default, because a covered row can still sit below its raw
 *    level (AC-32/AC-33). Under any other split, every group gets its own pair of sheets -
 *    `"<key> - Low"` then `"<key>"` (R2) - keyed on supplier / category / both.
 *
 *    It is a separate function rather than a third value on `exportOrderSheet`'s union
 *    because the body is what the order sheet's own test strict-equals, and because the
 *    two carry different caps and a different toast.
 *
 *    `GET /api/v1/scm/order-summary/low-stock-preview?run_id=<opaque>` (R4, AC-15b): the
 *    split dialog's own courtesy read, fired once on open, never on page load. Answers
 *    `LowStockPreview { rows, sheet_counts: { supplier, category, supplier_category } }` -
 *    `rows` is the visible row count (the "All" count), each `sheet_counts` entry is the
 *    number of GROUPS that split would write (none-buckets included, pairs only when
 *    present). The dialog doubles a group count into a sheet count locally
 *    (`previewLowStockExport`, R2) rather than asking the server to, so changing the radio
 *    needs no second fetch. A failed read hides the preview line; Export stays enabled -
 *    the preview is a courtesy, not a gate (AC-16b).
 *
 * -- ERROR SHAPE -------------------------------------------------------------
 * Every failure is the standard `AppException` envelope the global handler in
 * `app/main.py` serialises (`{ detail | message | error }`, correct HTTP status).
 * It is read with `extractApiError(res, fallback)` and surfaced as an `Error`
 * message, which is what each state renders beside its retry.
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { ExportSplit } from '@/components/common/export-split';
import type { MyDownload } from '@/services/myDownloadsService';
import {
  USE_SUMMARY_ORDER_MOCKS,
  mockOrderSummaryDemand,
} from '../lib/summaryOrderMockStore';
import type {
  LowStockPreview,
  OrderSummaryDemandDrill,
  OrderSummaryDemandKind,
} from '../types/summaryOrder.types';

// Review fix round 3, finding 6: getOrderSummary / getOrderSummarySuppliers /
// recordOrderDecision / getOrderSummaryLocations (and `OrderSummaryQuery`, which only
// they used) are deleted - the Order summary report page they served is retired (S10,
// round 2). `getOrderSummaryDemand` and `exportOrderSheet` survive: `DemandDrillPopover`
// still opens the first, and the plan's Actions menu still calls the second.
// `ReorderResultsGrid`/`ReorderExplanationDialog`'s own orphaned imports of the removed
// shapes are a separate follow-up, filed by the reviewer - not touched here.

/** The contributing lines behind one aggregate (AC-C2.3 / AC-C2.4). */
export async function getOrderSummaryDemand(
  productCode: string,
  kind: OrderSummaryDemandKind,
  runId?: string | null,
): Promise<OrderSummaryDemandDrill> {
  if (USE_SUMMARY_ORDER_MOCKS) return mockOrderSummaryDemand(productCode, kind);
  const params = new URLSearchParams({ kind });
  if (runId) params.set('run_id', runId);
  const res = await apiFetch(
    `/api/v1/scm/order-summary/${encodeURIComponent(productCode)}/demand?${params}`,
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load the contributing lines'));
  return (await res.json()) as OrderSummaryDemandDrill;
}

/**
 * Starts the sheet export through My Downloads (AC-19/AC-20). No mock branch: the export
 * always makes the real call, PDF/xlsx generation being nothing a fixture can usefully
 * stand in for. Returns the created `MyDownload` row (`status: 'pending'`) - the sheet
 * itself is fetched later, from the My Downloads drawer, once the worker marks it ready.
 */
export async function exportOrderSheet(
  runId: string,
  format: 'pdf' | 'xlsx',
): Promise<MyDownload> {
  const res = await apiFetch('/api/v1/scm/order-summary/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ run_id: runId, format }),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to start the order sheet export'));
  return (await res.json()) as MyDownload;
}

/**
 * Starts the low stock report through My Downloads (PLAN-low-stock-report S4, AC-2; split
 * added PLAN-low-stock-export-split-25sep AC-17). Same endpoint, same pipeline, a different
 * `format` - and no mock branch, for the same reason `exportOrderSheet` has none: a fixture
 * cannot usefully stand in for a workbook the worker renders. Returns the created
 * `MyDownload` row (`status: 'pending'`); the file is fetched later from the drawer, once
 * the worker marks it ready.
 */
export async function exportLowStockReport(
  runId: string,
  split: ExportSplit = 'none',
): Promise<MyDownload> {
  const res = await apiFetch('/api/v1/scm/order-summary/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ run_id: runId, format: 'low_stock_xlsx', split }),
  });
  if (!res.ok) {
    throw new Error(await extractApiError(res, 'Failed to start the low stock report'));
  }
  return (await res.json()) as MyDownload;
}

/**
 * The split dialog's own preview read (R4, AC-15b): fired once when the dialog opens,
 * never on page load. `USE_SUMMARY_ORDER_MOCKS` stays declared for this one function's own
 * sake (Phase 1, PLAN-low-stock-export-split-25sep) even with the flag off elsewhere in
 * this domain - a group count is a number a fixture can usefully stand in for, unlike a
 * rendered workbook, which is why this function gets a mock branch and the exports above
 * do not.
 */
export async function getLowStockPreview(runId: string): Promise<LowStockPreview> {
  if (USE_SUMMARY_ORDER_MOCKS) {
    return { rows: 833, sheet_counts: { supplier: 14, category: 9, supplier_category: 31 } };
  }
  const params = new URLSearchParams({ run_id: runId });
  const res = await apiFetch(`/api/v1/scm/order-summary/low-stock-preview?${params}`);
  if (!res.ok) {
    throw new Error(await extractApiError(res, 'Failed to load the export preview'));
  }
  return (await res.json()) as LowStockPreview;
}

/**
 * `previewLowStockExport(preview, split)` - the dialog's "N rows, M sheets" line (AC-16b),
 * recomputed locally on every radio change so the radio never triggers a second fetch.
 * `sheets` doubles the group count into the workbook's own sheet count (R2: every group is
 * a `"<key> - Low"` then `"<key>"` pair) - `none` is always 2 ("Low stock", "All"), exactly
 * as the unsplit workbook. `undefined` (loading, or a failed preview the caller already
 * chose not to show) reads as zero of both.
 */
export function previewLowStockExport(
  preview: LowStockPreview | undefined,
  split: ExportSplit,
): { rows: number; sheets: number } {
  if (!preview) return { rows: 0, sheets: 0 };
  const rows = preview.rows;
  if (split === 'none') return { rows, sheets: 2 };
  return { rows, sheets: preview.sheet_counts[split] * 2 };
}

/**
 * Starts the OI worksheet export through My Downloads (Lane C, PLAN-order-sheet-oi-
 * reports-22sep.md, AC-C1/AC-C2). Same endpoint, same pipeline, a third `format` - the
 * run's OWN Start Plan scope of live OI Buy rows, not the order sheet's rows. No mock
 * branch, for the same reason `exportOrderSheet`/`exportLowStockReport` have none: a
 * fixture cannot usefully stand in for a workbook the worker renders. Returns the created
 * `MyDownload` row (`status: 'pending'`); the file is fetched later from the drawer, once
 * the worker marks it ready.
 */
export async function exportOiWorksheet(runId: string): Promise<MyDownload> {
  const res = await apiFetch('/api/v1/scm/order-summary/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ run_id: runId, format: 'oi_worksheet' }),
  });
  if (!res.ok) {
    throw new Error(await extractApiError(res, 'Failed to start the OI worksheet export'));
  }
  return (await res.json()) as MyDownload;
}
