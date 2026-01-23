import { apiFetch } from '@/lib/api';
import type { Stock, StockDashboard } from '../types/stock.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export async function getStockDashboard(): Promise<StockDashboard> {
  const response = await apiFetch('/api/v1/inventory/stock/dashboard');
  if (!response.ok) throw new Error('Failed to fetch stock dashboard');
  return response.json();
}

export async function getStockBalance(params: DataGridApiFetchParams & { warehouse_id?: string; product_id?: string; category_id?: string; status?: string; quantity_operator?: string; quantity_value?: string }): Promise<DataGridApiResponse<Stock>> {
  const { pageIndex, pageSize, sorting, searchQuery, warehouse_id, product_id, category_id, status, quantity_operator, quantity_value } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
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
 * Bulk import stock from Excel data
 */
export async function bulkImportStock(data: any[]): Promise<{ created: number; updated: number; errors: string[] }> {
  const response = await apiFetch('/api/v1/inventory/stock/bulk-import', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ stock: data }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to import stock' }));
    throw new Error(error.message || 'Failed to import stock');
  }
  return response.json();
}
