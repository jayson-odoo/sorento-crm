/**
 * ============================================================================
 * PURCHASE ORDERS — real API binding + M4 Slice B draft→confirm→GR flow
 * ============================================================================
 * Mounted under `require_module_enabled_with_api_key("scm")` at
 * `/api/v1/scm/purchase-orders`, gated on `scm.dashboard.view` (writes use
 * `scm.reorder.run`). The PO feeds "on-order" / "incoming" into the
 * net-position views. No UUIDs surfaced — PO by po_number.
 *
 * At M1 the list was READ-ONLY. M4 Slice B adds the draft→confirm→GR flow:
 *   - draft POs (status `draft_recommendation`) are drafted from accepted
 *     recommendations and are NOT on-order (M4-D5);
 *   - bulk Confirm flips them to `active` — only then do they count as on-order;
 *   - create-GR stamps received qty on an active PO (GR = `picking_headers`,
 *     `picking_type='goods_received'`).
 *
 * PHASE 1 (now): `USE_SLICE_B_MOCKS = true` routes the list + confirm + GR
 * through the shared in-memory mock store (`lib/copilotMockStore.ts`) so the
 * whole loop runs with no backend. Phase 2 flips the flag to false.
 *
 * ── ENDPOINTS ───────────────────────────────────────────────────────────────
 *   GET  /purchase-orders   list (page/limit/sort/dir/query/status/supplier);
 *                           includes `draft_recommendation` rows (M4-D6).
 *   GET  /purchase-orders/{id}   single PO (header + lines) for the detail page.
 *   POST /purchase-orders/bulk-confirm   body { ids: string[] }
 *        → 200 { confirmed_count } · flips draft_recommendation → active (M4-D6).
 *        The backend ASSIGNS THE CANONICAL `PO-YYYY-####` NUMBER at confirm time
 *        via the PO numbering rule (see alembic 274 "Numbering rules for
 *        sales_order/purchase_order"); the draft's `PO-DRAFT-####` is provisional
 *        only. The response/refetch reflects each PO's new number.
 *   POST /purchase-orders/{id}/create-gr
 *        → 200 { gr_reference } · creates a goods receipt from an active PO,
 *          stamping received qty (M4-D6). Not available on drafts.
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { DataGridApiResponse } from '@/components/ui/data-grid';
import type { PurchaseOrder } from '../types/scm.types';
import {
  USE_SLICE_B_MOCKS,
  mockConfirmPurchaseOrders,
  mockCreateGr,
  mockGetPurchaseOrder,
  mockListPurchaseOrders,
} from '../lib/copilotMockStore';

const BASE = '/api/v1/scm/purchase-orders';

export interface PurchaseOrderListQuery {
  pageIndex: number;
  pageSize: number;
  sortField?: string;
  sortDir?: 'asc' | 'desc';
  searchQuery?: string;
  status?: string | null;
  supplier?: string | null;
}

/** Client-side list slice over the mock store (search + status filter + paging). */
function mockPurchaseOrderList(
  params: PurchaseOrderListQuery,
): DataGridApiResponse<PurchaseOrder> {
  let rows = mockListPurchaseOrders();
  const q = params.searchQuery?.trim().toLowerCase();
  if (q) {
    rows = rows.filter(
      (p) =>
        p.po_number.toLowerCase().includes(q) || p.supplier_name.toLowerCase().includes(q),
    );
  }
  if (params.status) rows = rows.filter((p) => p.status === params.status);
  const total = rows.length;
  const start = params.pageIndex * params.pageSize;
  const data = rows.slice(start, start + params.pageSize);
  return {
    data,
    empty: total === 0,
    pagination: { page: params.pageIndex + 1, total },
  };
}

export async function getPurchaseOrders(
  params: PurchaseOrderListQuery,
): Promise<DataGridApiResponse<PurchaseOrder>> {
  if (USE_SLICE_B_MOCKS) return mockPurchaseOrderList(params);
  const sorting = params.sortField
    ? [{ id: params.sortField, desc: params.sortDir === 'desc' }]
    : undefined;
  const sp = buildDataGridParams(
    {
      pageIndex: params.pageIndex,
      pageSize: params.pageSize,
      sorting,
      searchQuery: params.searchQuery,
    },
    { status: params.status ?? undefined, supplier: params.supplier ?? undefined },
  );
  const res = await apiFetch(`${BASE}?${sp.toString()}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load purchase orders'));
  return res.json();
}

/** Single PO by stable id — drives the detail page. GET /purchase-orders/{id}. */
export async function getPurchaseOrder(id: string): Promise<PurchaseOrder | null> {
  if (USE_SLICE_B_MOCKS) return mockGetPurchaseOrder(id);
  const res = await apiFetch(`${BASE}/${encodeURIComponent(id)}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load purchase order'));
  return (await res.json()) as PurchaseOrder;
}

/** Confirm draft POs → active (M4-D6). Returns how many were confirmed. */
export async function bulkConfirmPurchaseOrders(ids: string[]): Promise<{ confirmed_count: number }> {
  if (USE_SLICE_B_MOCKS) return { confirmed_count: mockConfirmPurchaseOrders(ids) };
  const res = await apiFetch(`${BASE}/bulk-confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to confirm purchase orders'));
  return (await res.json()) as { confirmed_count: number };
}

/** Create a goods receipt from an active PO (M4-D6). Returns the GR reference. */
export async function createGrFromPurchaseOrder(id: string): Promise<{ gr_reference: string }> {
  if (USE_SLICE_B_MOCKS) {
    const res = mockCreateGr(id);
    if (!res) throw new Error('A goods receipt can only be created from an active purchase order.');
    return res;
  }
  const res = await apiFetch(`${BASE}/${encodeURIComponent(id)}/create-gr`, { method: 'POST' });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to create goods receipt'));
  return (await res.json()) as { gr_reference: string };
}
