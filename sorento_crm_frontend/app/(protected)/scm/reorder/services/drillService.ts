/**
 * ============================================================================
 * SCM M8 - click-to-explain DRILL feature service  (Phase-2, real backend)
 * ============================================================================
 * Layering: hooks (useDrills) → THIS service → lib/api-client → backend.
 *
 * The two heavy plan-grid drills fetch their working lazily (only when a popover
 * opens), keyed off the recommendation, so the plan itself stays lean:
 *
 *  1) Net breakdown (M8-A1)
 *     GET /api/v1/scm/recommendations/{rec_id}/explain-net
 *       → 200 { on_hand, on_order, committed, net,
 *               committed_sos: [{ so_number, qty, customer_name, order_date }] }
 *
 *  2) Days-cover demand (M8-A2)
 *     GET /api/v1/scm/analytics/explain/demand?product_id=&warehouse_id=
 *       → 200 { avg_daily_demand, demand_cv, method,
 *               demand_dos: [{ order_id, do_number, order_date, qty_out }],
 *               buckets: [{ from, to, qty }], ... }
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

/** One open sales-order line behind the committed figure (M8-A1). */
export interface NetCommittedSo {
  so_number: string;
  qty: number;
  customer_name: string | null;
  order_date: string | null;
}

/** Net breakdown for a rec's product×warehouse (M8-A1). */
export interface NetBreakdownResult {
  on_hand: number;
  on_order: number;
  committed: number;
  net: number;
  committed_sos: NetCommittedSo[];
}

/** One delivery order that drove outflow in the demand window (M8-A2). */
export interface DemandDo {
  order_id: string;
  do_number: string;
  order_date: string | null;
  qty_out: number;
}

/** Days-cover demand working (M8-A2). */
export interface DemandExplainResult {
  product_id: string;
  warehouse_id: string | null;
  avg_daily_demand: number;
  demand_cv: number | null;
  method: string;
  method_reason?: string | null;
  demand_dos: DemandDo[];
  buckets: { from: string; to: string; qty: number }[];
}

/** Net-breakdown drill for a recommendation (M8-A1). */
export async function getRecommendationNet(recId: string): Promise<NetBreakdownResult> {
  const res = await apiFetch(
    `/api/v1/scm/recommendations/${encodeURIComponent(recId)}/explain-net`,
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load net breakdown'));
  return (await res.json()) as NetBreakdownResult;
}

/** Days-cover demand drill for a product (+ optional warehouse) (M8-A2). */
export async function getRecommendationDemand(
  productId: string,
  warehouseId: string | null,
): Promise<DemandExplainResult> {
  const params = new URLSearchParams({ product_id: productId });
  if (warehouseId) params.set('warehouse_id', warehouseId);
  const res = await apiFetch(`/api/v1/scm/analytics/explain/demand?${params}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load demand working'));
  return (await res.json()) as DemandExplainResult;
}
