import { apiFetch } from '@/lib/api';
import type { Warehouse, WarehouseFormData } from '../types/warehouse.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export async function getWarehouses(params: DataGridApiFetchParams): Promise<DataGridApiResponse<Warehouse>> {
  const { pageIndex, pageSize, sorting, searchQuery } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
  });
  const response = await apiFetch(`/api/inventory/warehouses?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch warehouses');
  return response.json();
}

export async function getWarehouse(id: string): Promise<Warehouse> {
  const response = await apiFetch(`/api/inventory/warehouses/${id}`);
  if (!response.ok) throw new Error('Failed to fetch warehouse');
  return response.json();
}

export async function createWarehouse(data: WarehouseFormData): Promise<Warehouse> {
  const response = await apiFetch('/api/inventory/warehouses', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to create warehouse' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function updateWarehouse(id: string, data: Partial<WarehouseFormData>): Promise<Warehouse> {
  const response = await apiFetch(`/api/inventory/warehouses/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to update warehouse' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function deleteWarehouse(id: string): Promise<void> {
  const response = await apiFetch(`/api/inventory/warehouses/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to delete warehouse' }));
    throw new Error(error.message);
  }
}
