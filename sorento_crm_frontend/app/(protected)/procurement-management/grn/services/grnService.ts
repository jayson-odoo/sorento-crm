import { apiFetch } from '@/lib/api';
import type { GRN, GRNDetail, GRNFormData } from '../types/grn.types';
import type {
  DataGridApiFetchParams,
  DataGridApiResponse,
} from '@/components/ui/data-grid';

export async function getGRNs(
  params: DataGridApiFetchParams & {
    picking_status?: string;
    inspection_status?: string;
    spo_allocation_id?: string;
  },
): Promise<DataGridApiResponse<GRN>> {
  const {
    pageIndex,
    pageSize,
    sorting,
    searchQuery,
    picking_status,
    inspection_status,
    spo_allocation_id,
  } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
    ...(picking_status ? { picking_status } : {}),
    ...(inspection_status ? { inspection_status } : {}),
    ...(spo_allocation_id ? { spo_allocation_id } : {}),
  });
  const response = await apiFetch(
    `/api/v1/procurement/grn?${queryParams.toString()}`,
  );
  if (!response.ok) throw new Error('Failed to fetch GRN');
  return response.json();
}

export async function getGRN(id: string): Promise<GRNDetail> {
  const response = await apiFetch(`/api/v1/procurement/grn/${id}`);
  if (!response.ok) throw new Error('Failed to fetch GRN');
  return response.json();
}

export async function createGRN(data: GRNFormData): Promise<GRN> {
  const response = await apiFetch('/api/v1/procurement/grn', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to create GRN' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function updateGRN(
  id: string,
  data: Partial<GRNFormData>,
): Promise<GRN> {
  const response = await apiFetch(`/api/v1/procurement/grn/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to update GRN' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function deleteGRN(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/procurement/grn/${id}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to delete GRN' }));
    throw new Error(error.message);
  }
}
