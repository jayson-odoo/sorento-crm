import { apiFetch } from '@/lib/api';
import type { Order } from '../types/order.types';

/**
 * Delivery Order → fulfilled complaints (reverse of the complaint detail
 * "Fulfilment Delivery Orders" section) + the Remarks CS freeze signal.
 * See docs/plans/PLAN-complaint-do-auto-fulfilment.md.
 *
 * PHASE 1 (current): the DO detail "Fulfils complaints" block is driven by MOCK
 * fixtures via `hooks/useOrderFulfilledComplaints` + `__mocks__/orderFulfilledComplaints`.
 * The Remarks CS readonly state is driven by `mockRemarksCsLocked` below until
 * the backend ships `remarks_cs_locked` on the order response.
 *
 * ── Expected API contract (Phase 2) ──────────────────────────────────────────
 *
 * GET /api/v1/order-management/orders/{id}/fulfilled-complaints
 *   Auth: same dependency + module guard as the order detail GET.
 *   200: FulfilledComplaint[]  ([] when this DO is not linked to any complaint)
 *
 *   FulfilledComplaint = {
 *     complaint_id: string;       // UUID — used ONLY for the row href, never displayed
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

/**
 * Phase 2 wiring — not yet called (the hook serves mocks in Phase 1). Kept here
 * so the request/response contract lives next to its types.
 */
export async function getOrderFulfilledComplaints(
  orderId: string,
): Promise<FulfilledComplaint[]> {
  const response = await apiFetch(
    `/api/v1/order-management/orders/${orderId}/fulfilled-complaints`,
  );
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to load fulfilled complaints' }));
    throw new Error(
      error.detail || error.message || 'Failed to load fulfilled complaints',
    );
  }
  return response.json();
}

/**
 * PHASE 1 MOCK — derive the Remarks CS freeze state when the backend hasn't
 * supplied `remarks_cs_locked` yet. Mirrors the real freeze rule (DO delivered
 * AND Remarks CS names a complaint), so the readonly UX is verifiable now and
 * forward-compatible: once the server sends `remarks_cs_locked`, that wins.
 */
export function mockRemarksCsLocked(order?: Order | null): boolean {
  if (!order) return false;
  if (order.remarks_cs_locked != null) return order.remarks_cs_locked;
  return !!order.actual_delivery_date && !!(order.remarks_cs ?? '').trim();
}
