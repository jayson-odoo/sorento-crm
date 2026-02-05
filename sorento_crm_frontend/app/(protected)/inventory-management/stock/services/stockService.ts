import { apiFetch } from '@/lib/api';
import type { Stock, StockDashboard } from '../types/stock.types';
import type { StockLedgerEntry } from '../../stock-ledger/types/stockLedger.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export async function getStockDashboard(): Promise<StockDashboard> {
  const response = await apiFetch('/api/v1/inventory/stock/dashboard');
  if (!response.ok) throw new Error('Failed to fetch stock dashboard');
  return response.json();
}

export async function getStockBalance(params: DataGridApiFetchParams & { warehouse_id?: string; product_id?: string; category_id?: string; status?: string; quantity_operator?: string; quantity_value?: string }): Promise<DataGridApiResponse<Stock>> {
  const { pageIndex, pageSize, sorting, searchQuery, warehouse_id, product_id, category_id, status, quantity_operator, quantity_value } = params;
  // Cap pageSize at 100 (API limit)
  const cappedPageSize = Math.min(pageSize, 100);
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(cappedPageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
    ...(warehouse_id ? { warehouse_id } : {}),
    ...(product_id ? { product_id } : {}),
    ...(category_id ? { category_id } : {}),
    ...(status ? { status } : {}),
    ...(quantity_operator ? { quantity_operator } : {}),
    ...(quantity_value ? { quantity_value } : {}),
  });
  const response = await apiFetch(`/api/v1/inventory/stock/balance?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch stock balance');
  return response.json();
}

export async function getStockDetail(productId: string, warehouseId: string): Promise<Stock | null> {
  const queryParams = new URLSearchParams({
    page: '1',
    limit: '1',
    product_id: productId,
    warehouse_id: warehouseId,
  });
  const response = await apiFetch(`/api/v1/inventory/stock/balance?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch stock detail');
  const result: DataGridApiResponse<Stock> = await response.json();
  return result.data?.[0] ?? null;
}

export async function getStockLedgerByStock(
  productId: string,
  warehouseId: string,
  params: { pageIndex: number; pageSize: number },
): Promise<DataGridApiResponse<StockLedgerEntry>> {
  const queryParams = new URLSearchParams({
    page: String(params.pageIndex + 1),
    limit: String(params.pageSize),
  });
  const response = await apiFetch(
    `/api/v1/inventory/stock/${productId}/${warehouseId}/ledger?${queryParams.toString()}`,
  );
  if (!response.ok) throw new Error('Failed to fetch stock ledger');
  return response.json();
}

export async function getStockAlerts(): Promise<Stock[]> {
  const response = await apiFetch('/api/v1/inventory/stock/alerts');
  if (!response.ok) throw new Error('Failed to fetch stock alerts');
  return response.json();
}

/**
 * Export all stock balance to Excel (uses dedicated export endpoint for better performance)
 */
export async function exportStockBalance(params?: { warehouse_id?: string; category_id?: string; status?: string; quantity_operator?: string; quantity_value?: string }): Promise<Stock[]> {
  const queryParams = new URLSearchParams({
    ...(params?.warehouse_id ? { warehouse_id: params.warehouse_id } : {}),
    ...(params?.quantity_operator ? { quantity_operator: params.quantity_operator } : {}),
    ...(params?.quantity_value ? { quantity_value: params.quantity_value } : {}),
  });

  const response = await apiFetch(`/api/v1/inventory/stock/balance/export?${queryParams.toString()}`);
  if (!response.ok) {
    throw new Error('Failed to fetch stock for export');
  }

  const result = await response.json();
  return result.data || [];
}

/**
 * Bulk import stock from Excel data (queued)
 * Returns job_id for tracking progress
 */
export async function bulkImportStock(
  data: any[],
): Promise<{ job_id: string; status: string; message: string }> {
  const response = await apiFetch('/api/v1/inventory/stock/bulk-import', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ stock: data }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to queue import job' }));
    throw new Error(error.message || 'Failed to queue import job');
  }
  return response.json();
}
