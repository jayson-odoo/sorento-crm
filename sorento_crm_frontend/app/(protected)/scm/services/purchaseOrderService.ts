/**
 * ============================================================================
 * PURCHASE ORDERS — real API binding (Phase 2 / M1 CP2b; read-only at M1)
 * ============================================================================
 * Mounted under `require_module_enabled_with_api_key("scm")` at
 * `/api/v1/scm/purchase-orders`, gated on `scm.dashboard.view`. The PO feeds
 * "on-order" / "incoming" into the net-position views. At M1 the list is
 * READ-ONLY — create / confirm / receive land in M4. No UUIDs surfaced — PO by
 * po_number.
 *
 *   GET /purchase-orders   list (page/limit/sort/dir/query/status/supplier)
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { DataGridApiResponse } from '@/components/ui/data-grid';
import type { PurchaseOrder } from '../types/scm.types';

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

export async function getPurchaseOrders(
  params: PurchaseOrderListQuery,
): Promise<DataGridApiResponse<PurchaseOrder>> {
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
