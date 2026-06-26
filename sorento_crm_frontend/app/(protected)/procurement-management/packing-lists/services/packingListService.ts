import { apiFetch } from '@/lib/api';
import type {
  PackingList,
  PackingListDetail,
  PackingListFormData,
} from '../types/packingList.types';
import type {
  DataGridApiFetchParams,
  DataGridApiResponse,
} from '@/components/ui/data-grid';

export type PackingListsListParams = DataGridApiFetchParams & {
  supplier_id?: string;
  shipment_status?: string;
};

/**
 * Path of the packing-lists neighbours endpoint. Consumed by `usePackingListNeighbours`
 * via the generic `useRecordNeighbours` hook.
 *
 * Contract (see docs/plans/PLAN-record-navigation-standardization.md):
 *   GET /api/v1/procurement/packing-lists/neighbours
 *   Query params: id=<uuid> + the SAME params the list GET accepts
 *                 (query, supplier_id, shipment_status, sort, dir). page/limit ignored.
 *   Auth: same dependency + module guard as the list GET.
 *   200:  { total: number, index: number|null, prev_id: string|null, next_id: string|null }
 *         - index is 1-based; null when the record is not in the filtered set
 *           (the backend then falls back to the unfiltered, default-sorted set).
 *         - prev_id/next_id wrap circularly; null only when total <= 1.
 */
export const PACKING_LIST_NEIGHBOURS_PATH =
  '/api/v1/procurement/packing-lists/neighbours';

export async function getPackingLists(
  params: PackingListsListParams,
): Promise<DataGridApiResponse<PackingList>> {
  const {
    pageIndex,
    pageSize,
    sorting,
    searchQuery,
    supplier_id,
    shipment_status,
  } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
    ...(supplier_id ? { supplier_id } : {}),
    ...(shipment_status ? { shipment_status } : {}),
  });
  const response = await apiFetch(
    `/api/v1/procurement/packing-lists?${queryParams.toString()}`,
  );
  if (!response.ok) throw new Error('Failed to fetch packing lists');
  return response.json();
}

export async function getPackingList(id: string): Promise<PackingListDetail> {
  const response = await apiFetch(`/api/v1/procurement/packing-lists/${id}`);
  if (!response.ok) throw new Error('Failed to fetch packing list');
  return response.json();
}

export async function createPackingList(
  data: PackingListFormData,
): Promise<PackingList> {
  const response = await apiFetch('/api/v1/procurement/packing-lists', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to create packing list' }));
    throw new Error(error.detail ?? error.message ?? 'Failed to create packing list');
  }
  return response.json();
}

export async function updatePackingList(
  id: string,
  data: Partial<PackingListFormData>,
): Promise<PackingList> {
  const response = await apiFetch(`/api/v1/procurement/packing-lists/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to update packing list' }));
    throw new Error(error.detail ?? error.message ?? 'Failed to update packing list');
  }
  return response.json();
}

export async function deletePackingList(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/procurement/packing-lists/${id}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to delete packing list' }));
    throw new Error(error.message);
  }
}

export async function bulkDeletePackingLists(
  ids: string[],
): Promise<{ message: string; deleted_count: number }> {
  const response = await apiFetch('/api/v1/procurement/packing-lists/bulk', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to bulk delete packing lists' }));
    throw new Error(error.detail ?? error.message ?? 'Failed to bulk delete packing lists');
  }
  return response.json();
}
