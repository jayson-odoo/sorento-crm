/**
 * ============================================================================
 * Reorder revamp - the three reads/writes the revamp ADDS (Phase 1: mocks)
 * ============================================================================
 * Layering: hooks (usePlanEdits / usePlanSupplyHistory) -> THIS service ->
 * lib/api-client -> backend.
 *
 * Everything else the plan page needs already has an endpoint and is called through
 * `reorderRunService.ts`. These three do not exist yet; Phase 1 builds the UI against a
 * deterministic local mock so the interaction can be settled before any backend code is
 * written (PRINCIPLES.md, phase order). Each mock is marked `PHASE 2` at its call site and
 * the real contract is written out above it, so swapping it is a one-function change.
 *
 * Contracts to build in Phase 2 (PLAN-scm-reorder-revamp.md section 5):
 *
 *  1) PUT /api/v1/scm/reorder-runs/{run_id}/plan-edits
 *     body: { rows: [{ rec_id, decision?, moq?, level?, reorder_qty?, lifecycle? }] }
 *     One transaction over the existing service functions (`record_plan_row_decision`,
 *     `set_moq_override`, the level amend, `record_lifecycle_decision`). 404 for a rec
 *     outside the run, 409 on a legacy run. Returns the refreshed rows.
 *
 *  2) GET /api/v1/scm/reorder-runs/{run_id}/spo-history?product_id=<uuid>
 *     Shipping orders bound for the BRW POOL location only (R15), open first then
 *     received. -> { open: SpoShipment[], history: SpoShipment[] }
 *
 *  3) GET /api/v1/scm/reorder-runs/{run_id}/purchase-trend?warehouse=<code>
 *     The existing purchase-trend read, filtered to one destination (R15). Lines with no
 *     destination, or bound for a project location, are left out.
 * ============================================================================
 */
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
 * PHASE 2: replace with `PUT /api/v1/scm/reorder-runs/{run_id}/plan-edits` (contract 1
 * above). The mock resolves after a tick so the toolbar's pending state is real, and
 * reports the same two counts the endpoint will.
 */
export async function savePlanEdits(
  runId: string,
  rows: PlanEditRow[],
): Promise<PlanEditsResult> {
  // PHASE 2: replace with the real call.
  await new Promise((resolve) => setTimeout(resolve, 0));
  if (!runId) throw new Error('No plan to save against.');
  return {
    saved_rows: rows.length,
    saved_products: new Set(rows.map((r) => r.rec_id)).size,
  };
}

/**
 * The shipping orders behind the SPO cell.
 *
 * PHASE 2: replace with `GET /api/v1/scm/reorder-runs/{run_id}/spo-history?product_id=`
 * (contract 2 above). The mock returns an empty book, which is what most products have and
 * is the state the dialog's own empty message is written for.
 */
export async function getSpoHistory(
  runId: string,
  productId: string,
): Promise<SpoHistoryResponse> {
  // PHASE 2: replace with the real call.
  await new Promise((resolve) => setTimeout(resolve, 0));
  if (!runId || !productId) return { open: [], history: [] };
  return { open: [], history: [] };
}

/**
 * The purchase orders behind the PO cell's History tab, destination-filtered (R15).
 *
 * PHASE 2: replace with `GET /api/v1/scm/reorder-runs/{run_id}/purchase-trend?warehouse=`
 * (contract 3 above). The imported history names no destination on 12,928 of 12,940 lines,
 * so this tab holds the purchase orders raised in the CRM rather than the old export - the
 * dialog says so where the reader can see it.
 */
export async function getPoHistoryToPool(
  runId: string,
  productId: string,
  warehouseCode: string | null,
): Promise<PoHistoryResponse> {
  // PHASE 2: replace with the real call.
  await new Promise((resolve) => setTimeout(resolve, 0));
  if (!runId || !productId || !warehouseCode) return { history: [] };
  return { history: [] };
}
