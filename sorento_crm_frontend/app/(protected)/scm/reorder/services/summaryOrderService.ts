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
 * -- ERROR SHAPE -------------------------------------------------------------
 * Every failure is the standard `AppException` envelope the global handler in
 * `app/main.py` serialises (`{ detail | message | error }`, correct HTTP status).
 * It is read with `extractApiError(res, fallback)` and surfaced as an `Error`
 * message, which is what each state renders beside its retry.
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import {
  USE_SUMMARY_ORDER_MOCKS,
  mockOrderSummary,
  mockOrderSummaryDemand,
  mockOrderSummaryLocations,
  mockOrderSummarySuppliers,
  mockRecordOrderDecision,
} from '../lib/summaryOrderMockStore';
import type {
  OrderSummaryDecisionInput,
  OrderSummaryDecisionResult,
  OrderSummaryDemandDrill,
  OrderSummaryDemandKind,
  OrderSummaryLocations,
  OrderSummaryReport,
  OrderSummarySuppliers,
} from '../types/summaryOrder.types';

/** Which report to read. Both are optional; omitted means the current run today. */
export interface OrderSummaryQuery {
  /** Opaque run key. Never rendered. Null reads the newest completed plan. */
  run_id?: string | null;
}

/** The report, one row per product network wide (AC-C2.1). */
export async function getOrderSummary(q: OrderSummaryQuery = {}): Promise<OrderSummaryReport> {
  if (USE_SUMMARY_ORDER_MOCKS) return mockOrderSummary();
  const params = new URLSearchParams();
  if (q.run_id) params.set('run_id', q.run_id);
  // No `as_of`: the report STATES the date it was frozen for, and passing a different one
  // would label a frozen position with a date it does not describe. To read another week,
  // name its run.
  const qs = params.toString();
  const res = await apiFetch(`/api/v1/scm/order-summary${qs ? `?${qs}` : ''}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load the order summary'));
  return (await res.json()) as OrderSummaryReport;
}

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

/** The member locations behind one product row (AC-F08). */
export async function getOrderSummaryLocations(
  productCode: string,
  runId?: string | null,
): Promise<OrderSummaryLocations> {
  if (USE_SUMMARY_ORDER_MOCKS) return mockOrderSummaryLocations(productCode);
  const params = new URLSearchParams();
  if (runId) params.set('run_id', runId);
  const qs = params.toString();
  const res = await apiFetch(
    `/api/v1/scm/order-summary/${encodeURIComponent(productCode)}/locations${qs ? `?${qs}` : ''}`,
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load the member locations'));
  return (await res.json()) as OrderSummaryLocations;
}

/** The supplier candidates for one product (AC-C2.5 / AC-C2.6). */
export async function getOrderSummarySuppliers(
  productCode: string,
): Promise<OrderSummarySuppliers> {
  if (USE_SUMMARY_ORDER_MOCKS) return mockOrderSummarySuppliers(productCode);
  const res = await apiFetch(
    `/api/v1/scm/order-summary/${encodeURIComponent(productCode)}/suppliers`,
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load the supplier candidates'));
  return (await res.json()) as OrderSummarySuppliers;
}

/** Record the chosen quantity and supplier (AC-C2.7 / AC-C2.8). */
export async function recordOrderDecision(
  productCode: string,
  input: OrderSummaryDecisionInput,
): Promise<OrderSummaryDecisionResult> {
  if (USE_SUMMARY_ORDER_MOCKS) return mockRecordOrderDecision(productCode, input);
  const res = await apiFetch(
    `/api/v1/scm/order-summary/${encodeURIComponent(productCode)}/decision`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    },
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to record the decision'));
  return (await res.json()) as OrderSummaryDecisionResult;
}
