import { apiFetch } from '@/lib/api';
import type { UnitOfMeasure, UOMFormData } from '../types/uom.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export async function getUOMs(params: DataGridApiFetchParams): Promise<DataGridApiResponse<UnitOfMeasure>> {
  const { pageIndex, pageSize, sorting, searchQuery } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
  });
  const response = await apiFetch(`/api/v1/master-data/units-of-measure?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch UOMs');
  return response.json();
}

export async function getUOM(id: string): Promise<UnitOfMeasure> {
  const response = await apiFetch(`/api/v1/master-data/units-of-measure/${id}`);
  if (!response.ok) throw new Error('Failed to fetch UOM');
  return response.json();
}

export async function createUOM(data: UOMFormData): Promise<UnitOfMeasure> {
  const response = await apiFetch('/api/v1/master-data/units-of-measure', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to create UOM' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function updateUOM(id: string, data: Partial<UOMFormData>): Promise<UnitOfMeasure> {
  const response = await apiFetch(`/api/v1/master-data/units-of-measure/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to update UOM' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function deleteUOM(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/master-data/units-of-measure/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to delete UOM' }));
    throw new Error(error.message);
  }
}
