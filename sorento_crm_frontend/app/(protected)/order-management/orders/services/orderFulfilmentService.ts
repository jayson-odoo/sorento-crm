import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

/**
 * Delivery Order → fulfilled complaints (reverse of the complaint detail
 * "Fulfilment Delivery Orders" section) + the Remarks CS freeze signal.
 * See docs/plans/PLAN-complaint-do-auto-fulfilment.md.
 *
 * The DO detail "Fulfils complaints" block is served by
 * `hooks/useOrderFulfilledComplaints` → `getOrderFulfilledComplaints`. The
 * Remarks CS readonly state is driven by the backend `remarks_cs_locked` flag on
 * the order response.
 *
 * ── API contract ─────────────────────────────────────────────────────────────
 *
 * GET /api/v1/order-management/orders/{id}/fulfilled-complaints
 *   Auth: same dependency + module guard as the order detail GET.
 *   200: FulfilledComplaint[]  ([] when this DO is not linked to any complaint)
 *
 *   FulfilledComplaint = {
 *     complaint_id: string;       // UUID - used ONLY for the row href, never displayed
 *     complaint_number: string;   // human complaint number, e.g. "CMP26-0042" (displayed)
 *   }
 *
 * GET /api/v1/order-management/orders/{id}  (existing) gains:
 *     remarks_cs_locked: boolean   // true ⇒ FE renders Remarks CS readonly
 *
 * NOTE on path: the orders router is mounted under
 *   /api/v1/order-management/orders/... (see orderService.ts), so the contract
 *   path follows that prefix rather than the bare /api/v1/orders/{id}/...
 *   sketched in the plan. Flagged in the Phase-1 handoff notes.
 */

export interface FulfilledComplaint {
  complaint_id: string;
  complaint_number: string;
}

export async function getOrderFulfilledComplaints(
  orderId: string,
): Promise<FulfilledComplaint[]> {
  const response = await apiFetch(
    `/api/v1/order-management/orders/${orderId}/fulfilled-complaints`,
  );
  if (!response.ok) {
    throw new Error(
      await extractApiError(response, 'Failed to load fulfilled complaints'),
    );
  }
  return response.json();
}
