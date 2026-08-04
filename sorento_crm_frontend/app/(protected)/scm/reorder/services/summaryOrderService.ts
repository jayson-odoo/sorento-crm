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
 *          ?run_id=<opaque>          optional; omitted = the current run
 *          &as_of=<YYYY-MM-DD>       optional; omitted = today
 *
 *      -> 200  OrderSummaryReport    (see `types/summaryOrder.types.ts` - that file
 *                                     is the field-for-field contract and is NOT
 *                                     restated here)
 *      Auth: `scm.dashboard.view` (read-only), matching `explainer.py`.
 *
 *    `run_id` + `as_of` together are what make a past week reproducible (AC-C2.9):
 *    the same pair must return what the decider saw, not a recomputation against
 *    today's book.
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
 *          ?kind=project|dealer      required
 *          &run_id=<opaque>          optional; same run as the report
 *
 *      -> 200  OrderSummaryDemandDrill
 *      Auth: `scm.dashboard.view`.
 *
 *    **The server owns the ordering.** `kind=dealer` returns lines sorted
 *    worst-first by `days_outstanding` (AC-C2.4); `kind=project` by
 *    `required_date`, nulls last. The client never re-sorts, so the ageing a
 *    person reads is the ageing the server computed.
 *
 *    `total_qty` must equal the row's aggregate. The row figure is derived from
 *    these lines and never retyped by a person (AC-C2.3).
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
  mockOrderSummarySuppliers,
  mockRecordOrderDecision,
} from '../lib/summaryOrderMockStore';
import type {
  OrderSummaryDecisionInput,
  OrderSummaryDecisionResult,
  OrderSummaryDemandDrill,
  OrderSummaryDemandKind,
  OrderSummaryReport,
  OrderSummarySuppliers,
} from '../types/summaryOrder.types';

/** Which report to read. Both are optional; omitted means the current run today. */
export interface OrderSummaryQuery {
  /** Opaque run key. Never rendered. */
  run_id?: string | null;
  /** ISO date (YYYY-MM-DD) to state the position as of. */
  as_of?: string | null;
}

/** The report, one row per product network wide (AC-C2.1). */
export async function getOrderSummary(q: OrderSummaryQuery = {}): Promise<OrderSummaryReport> {
  if (USE_SUMMARY_ORDER_MOCKS) return mockOrderSummary();
  const params = new URLSearchParams();
  if (q.run_id) params.set('run_id', q.run_id);
  if (q.as_of) params.set('as_of', q.as_of);
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
