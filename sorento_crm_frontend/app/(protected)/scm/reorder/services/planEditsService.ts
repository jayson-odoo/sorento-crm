/**
 * ============================================================================
 * Reorder revamp - the three reads/writes the revamp ADDS
 * ============================================================================
 * Layering: hooks (usePlanEdits / the dialogs' own queries) -> THIS service ->
 * lib/api-client -> backend.
 *
 * Everything else the plan page needs already has an endpoint and is called through
 * `reorderRunService.ts`. These three are the revamp's own:
 *
 *  1) PUT /api/v1/scm/reorder-runs/{run_id}/plan-edits
 *     Save (N) - every drafted edit in one request, one transaction. Each field is
 *     applied by the service that already owned it (`record_plan_row_decision`,
 *     `set_moq_override`, the level amendment, the reorder quantity, the lifecycle
 *     answer), so this and the per-row endpoints can never disagree.
 *
 *  2) GET /api/v1/scm/reorder-runs/{run_id}/spo-history?product_id=<uuid>
 *     Shipping orders bound for the site POOL only (R15), open first then received.
 *
 *  3) GET /api/v1/scm/reorder-runs/{run_id}/purchase-trend?warehouse=<code>
 *     The existing purchase-trend read, narrowed to one destination (R15). Lines with
 *     no destination, or bound for a project bin, are left out.
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { PlanRowPriceMode } from '../types/decisions.types';

/** One row of the bulk save. `rec_id` is a RECOMMENDATION id - a grouped product row is
 *  expanded to one entry per member before it is sent. */
export interface PlanEditRow {
  rec_id: string;
  decision?: {
    kind: 'buy' | 'use_stock' | 'use_po' | 'skip' | 'mixture';
    buy_qty?: number;
    stock_takes?: { location: string; qty: number }[];
    po_qty?: number;
    price_mode?: PlanRowPriceMode;
    supplier_code?: string;
  };
  moq?: number | null;
  level?: number | null;
  reorder_qty?: number | null;
  lifecycle?: 'keep' | 'discontinue' | null;
}

export interface PlanEditsResult {
  /** How many recommendation rows the save touched. */
  saved_rows: number;
  /** How many distinct products those rows belong to (R14) - what Save (N) counted. */
  saved_products: number;
}

/** One shipping order carrying this product to the site pool. */
export interface SpoShipment {
  spo_number: string;
  supplier_name: string | null;
  qty: number;
  received_qty: number;
  eta: string | null;
  arrived_at: string | null;
  status: string;
}

export interface SpoHistoryResponse {
  open: SpoShipment[];
  history: SpoShipment[];
}

/** One purchase-order line raised for this product against the site pool. */
export interface PoHistoryLine {
  po_number: string;
  supplier_name: string | null;
  qty: number;
  unit_cost: number | null;
  currency: string | null;
  issued_at: string | null;
  eta: string | null;
  status: string;
}

export interface PoHistoryResponse {
  history: PoHistoryLine[];
}

/**
 * Save every drafted edit on a run in one request.
 *
 * One transaction on the backend: a failing row rolls the whole batch back, so the pills
 * never read Saved for an edit that did not land.
 */
export async function savePlanEdits(
  runId: string,
  rows: PlanEditRow[],
): Promise<PlanEditsResult> {
  if (!runId) throw new Error('No plan to save against.');
  const res = await apiFetch(
    `/api/v1/scm/reorder-runs/${encodeURIComponent(runId)}/plan-edits`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rows }),
    },
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to save the plan'));
  return res.json();
}

/** The shipping orders behind the SPO cell, for the site pool only (R15). */
export async function getSpoHistory(
  runId: string,
  productId: string,
): Promise<SpoHistoryResponse> {
  if (!runId || !productId) return { open: [], history: [] };
  const qs = new URLSearchParams({ product_id: productId });
  const res = await apiFetch(
    `/api/v1/scm/reorder-runs/${encodeURIComponent(runId)}/spo-history?${qs.toString()}`,
  );
  if (!res.ok) {
    throw new Error(await extractApiError(res, 'Failed to load the shipping orders'));
  }
  const body = (await res.json()) as Partial<SpoHistoryResponse>;
  return { open: body.open ?? [], history: body.history ?? [] };
}

/**
 * The purchase orders behind the PO cell's History tab, destination-filtered (R15).
 *
 * Reads `purchase-trend`, which is keyed by product and carries the recent purchase lines
 * for every product in the plan; `warehouse` narrows those lines to the row's own pool.
 * The imported history names no destination on 12,928 of 12,940 lines, so this tab holds
 * the purchase orders raised in the CRM rather than the old export - the dialog says so
 * where the reader can see it.
 */
export async function getPoHistoryToPool(
  runId: string,
  productId: string,
  warehouseCode: string | null,
): Promise<PoHistoryResponse> {
  if (!runId || !productId || !warehouseCode) return { history: [] };
  const qs = new URLSearchParams({ warehouse: warehouseCode });
  const res = await apiFetch(
    `/api/v1/scm/reorder-runs/${encodeURIComponent(runId)}/purchase-trend?${qs.toString()}`,
  );
  if (!res.ok) {
    throw new Error(await extractApiError(res, 'Failed to load the purchase history'));
  }
  const body = (await res.json()) as {
    products?: Record<
      string,
      {
        lines?: {
          po_number: string;
          supplier_name: string | null;
          qty: number;
          unit_cost: number | null;
          currency: string | null;
          order_date: string | null;
          expected_date: string | null;
          status: string | null;
        }[];
      }
    >;
  };
  const lines = body.products?.[productId]?.lines ?? [];
  return {
    history: lines.map((l) => ({
      po_number: l.po_number,
      supplier_name: l.supplier_name,
      qty: l.qty,
      unit_cost: l.unit_cost,
      currency: l.currency,
      issued_at: l.order_date,
      eta: l.expected_date,
      status: l.status ?? '',
    })),
  };
}
