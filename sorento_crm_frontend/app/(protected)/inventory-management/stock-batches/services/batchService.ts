import { apiFetch } from '@/lib/api';
import type { StockBatch, BatchFormData } from '../types/batch.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export async function getStockBatches(params: DataGridApiFetchParams & { warehouse_id?: string; product_id?: string; status?: string }): Promise<DataGridApiResponse<StockBatch>> {
  const { pageIndex, pageSize, sorting, searchQuery, warehouse_id, product_id, status } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
    ...(warehouse_id ? { warehouse_id } : {}),
    ...(product_id ? { product_id } : {}),
    ...(status ? { status } : {}),
  });
  const response = await apiFetch(`/api/v1/inventory/stock-batches?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch stock batches');
  return response.json();
}

export async function getStockBatch(id: string): Promise<StockBatch> {
  const response = await apiFetch(`/api/v1/inventory/stock-batches/${id}`);
  if (!response.ok) throw new Error('Failed to fetch stock batch');
  return response.json();
}

export async function createStockBatch(data: BatchFormData): Promise<StockBatch> {
  const response = await apiFetch('/api/v1/inventory/stock-batches', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to create stock batch' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function updateStockBatch(id: string, data: Partial<BatchFormData>): Promise<StockBatch> {
  const response = await apiFetch(`/api/v1/inventory/stock-batches/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to update stock batch' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function deleteStockBatch(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/inventory/stock-batches/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to delete stock batch' }));
    throw new Error(error.message);
  }
}

export async function bulkAddSerialNumbers(batchId: string, serialNumbers: string[]): Promise<void> {
  const response = await apiFetch(`/api/v1/inventory/stock-batches/${batchId}/serials/bulk`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ serial_numbers: serialNumbers }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to add serial numbers' }));
    throw new Error(error.message);
  }
}
