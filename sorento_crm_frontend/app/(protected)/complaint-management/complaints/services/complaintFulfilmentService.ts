import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

/**
 * Complaint ↔ Delivery Order auto-fulfilment - FE service contract.
 * See docs/plans/PLAN-complaint-do-auto-fulfilment.md.
 *
 * The "Fulfilment Delivery Orders" section is served by
 * `hooks/useComplaintFulfilmentOrders` → `getComplaintFulfilmentOrders`.
 *
 * ── API contract ─────────────────────────────────────────────────────────────
 *
 * GET /api/v1/complaints-management/complaints/{id}/fulfilment-orders
 *   Auth: same dependency + module guard as the complaint detail GET.
 *   200: FulfilmentOrder[]  (ordered newest-linked first; [] when none linked)
 *
 *   FulfilmentOrder = {
 *     order_id: string;              // UUID - used ONLY for the row href, never displayed
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

export async function getComplaintFulfilmentOrders(
  complaintId: string,
): Promise<FulfilmentOrder[]> {
  const response = await apiFetch(
    `/api/v1/complaints-management/complaints/${complaintId}/fulfilment-orders`,
  );
  if (!response.ok) {
    throw new Error(
      await extractApiError(response, 'Failed to load fulfilment delivery orders'),
    );
  }
  return response.json();
}
