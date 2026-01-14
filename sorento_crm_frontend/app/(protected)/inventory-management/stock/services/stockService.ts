import { apiFetch } from '@/lib/api';
import type { Stock, StockDashboard } from '../types/stock.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export async function getStockDashboard(): Promise<StockDashboard> {
  const response = await apiFetch('/api/v1/inventory/stock/dashboard');
  if (!response.ok) throw new Error('Failed to fetch stock dashboard');
  return response.json();
}

export async function getStockBalance(params: DataGridApiFetchParams & { warehouse_id?: string; category_id?: string; status?: string }): Promise<DataGridApiResponse<Stock>> {
  const { pageIndex, pageSize, sorting, searchQuery, warehouse_id, category_id, status } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
    ...(warehouse_id ? { warehouse_id } : {}),
    ...(category_id ? { category_id } : {}),
    ...(status ? { status } : {}),
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
