import { apiFetch } from '@/lib/api';

/**
 * Complaint ↔ Delivery Order auto-fulfilment — FE service contract.
 * See docs/plans/PLAN-complaint-do-auto-fulfilment.md.
 *
 * PHASE 1 (current): the section is driven by MOCK fixtures via
 * `hooks/useComplaintFulfilmentOrders` + `__mocks__/complaintFulfilmentOrders`.
 * The fetch helper below documents the exact shape the FE expects so Phase 2
 * can wire it onto the real endpoint with no UI change.
 *
 * ── Expected API contract (Phase 2) ──────────────────────────────────────────
 *
 * GET /api/v1/complaints-management/complaints/{id}/fulfilment-orders
 *   Auth: same dependency + module guard as the complaint detail GET.
 *   200: FulfilmentOrder[]  (ordered newest-linked first; [] when none linked)
 *
 *   FulfilmentOrder = {
 *     order_id: string;              // UUID — used ONLY for the row href, never displayed
 *     order_number: string;          // human DO number, e.g. "REPPS2605-0012" (displayed)
 *     status: string;                // DO status CODE: new|pending|approved|processing|
 *                                    //   shipped|delivered|cancelled|completed
 *     status_label: string;          // display label, e.g. "Picked Up / In Transit"
 *     actual_delivery_date: string | null;  // ISO; null when not yet delivered
 *     is_cancelled: boolean;         // cancelled DOs are excluded from the fulfil check
 *     items: FulfilmentOrderItem[];  // line items for the popup
 *   }
 *
 *   FulfilmentOrderItem = {
 *     product_code: string;          // human product code (displayed)
 *     product_type: string | null;
 *     qty: number | string | null;
 *   }
 *
 * NOTE on path: the complaints router is mounted under
 *   /api/v1/complaints-management/complaints/... (see complaintService.ts), so
 *   the contract path above follows that prefix rather than the bare
 *   /api/v1/complaints/{id}/fulfilment-orders sketched in the plan. Flagged in
 *   the Phase-1 handoff notes.
 */

export interface FulfilmentOrderItem {
  product_code: string;
  product_type?: string | null;
  qty?: number | string | null;
}

export interface FulfilmentOrder {
  order_id: string;
  order_number: string;
  status: string;
  status_label: string;
  actual_delivery_date?: string | null;
  is_cancelled: boolean;
  items: FulfilmentOrderItem[];
}

/**
 * Phase 2 wiring — not yet called (the hook serves mocks in Phase 1). Kept here
 * so the request/response contract lives next to its types.
 */
export async function getComplaintFulfilmentOrders(
  complaintId: string,
): Promise<FulfilmentOrder[]> {
  const response = await apiFetch(
    `/api/v1/complaints-management/complaints/${complaintId}/fulfilment-orders`,
  );
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to load fulfilment delivery orders' }));
    throw new Error(
      error.detail || error.message || 'Failed to load fulfilment delivery orders',
    );
  }
  return response.json();
}
