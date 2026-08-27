/**
 * ============================================================================
 * Stock transfers - feature service (`PLAN-scm-cs-planning-uat.md` section E)
 * ============================================================================
 * Layering: UI -> hooks (`useStockTransfers`) -> THIS service -> lib/api-client -> backend.
 *
 * ── CONTRACT ─────────────────────────────────────────────────────────────────
 * Mounted under `require_module_enabled_with_api_key("inventory")`. Reads on
 * `inventory.stock_transfers.view`, every transition on `inventory.stock_transfers.edit`.
 *
 *   GET  /api/v1/inventory/stock-transfers                       (AC-E5)
 *        query: page, limit, sort, dir, query, state, kind, from_warehouse_id,
 *               to_warehouse_id, product_id, sales_order_id, project_sales_order_id,
 *               sales_agent_id
 *        -> ListResponse { data, pagination: { total, page, limit }, empty }
 *   GET  /api/v1/inventory/stock-transfers/{id}
 *   POST /api/v1/inventory/stock-transfers/{id}/approve
 *   POST /api/v1/inventory/stock-transfers/{id}/mark-moved  { autocount_ref }  (required)
 *   POST /api/v1/inventory/stock-transfers/{id}/cancel      { reason }         (required)
 *   POST /api/v1/inventory/stock-transfers/bulk-approve     { ids }
 *        -> { approved, skipped: [{ id, transfer_no, reason }] }
 *
 * There is no create and no delete: a transfer exists because a supply confirmation
 * implied it, and it leaves by being moved or cancelled.
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type {
  BulkApproveResult,
  StockTransfer,
  StockTransferListEnvelope,
  StockTransferListParams,
} from '../types/stockTransfer.types';

const BASE = '/api/v1/inventory/stock-transfers';

export async function listStockTransfers(
  params: StockTransferListParams = {},
): Promise<StockTransferListEnvelope> {
  const search = buildDataGridParams(
    {
      pageIndex: (params.page ?? 1) - 1,
      pageSize: params.limit ?? 25,
      sorting: params.sort ? [{ id: params.sort, desc: params.dir === 'desc' }] : [],
      searchQuery: params.query ?? '',
    },
    {
      state: params.state,
      kind: params.kind,
      from_warehouse_id: params.from_warehouse_id,
      to_warehouse_id: params.to_warehouse_id,
      product_id: params.product_id,
      sales_order_id: params.sales_order_id,
      project_sales_order_id: params.project_sales_order_id,
      sales_agent_id: params.sales_agent_id,
    },
  );
  const response = await apiFetch(`${BASE}?${search.toString()}`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load stock transfers'));
  return response.json();
}

export async function getStockTransfer(transferId: string): Promise<StockTransfer> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(transferId)}`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load the stock transfer'));
  return response.json();
}

export async function approveStockTransfer(transferId: string): Promise<StockTransfer> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(transferId)}/approve`, {
    method: 'POST',
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to approve the transfer'));
  return response.json();
}

export async function markStockTransferMoved(
  transferId: string,
  autocountRef: string,
): Promise<StockTransfer> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(transferId)}/mark-moved`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ autocount_ref: autocountRef }),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to mark the transfer moved'));
  return response.json();
}

export async function cancelStockTransfer(
  transferId: string,
  reason: string,
): Promise<StockTransfer> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(transferId)}/cancel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to cancel the transfer'));
  return response.json();
}

export async function bulkApproveStockTransfers(ids: string[]): Promise<BulkApproveResult> {
  const response = await apiFetch(`${BASE}/bulk-approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to approve the transfers'));
  return response.json();
}
