import { apiFetch } from '@/lib/api';
import type {
  SPOAllocation,
  SPOAllocationDetail,
  SPOAllocationFormData,
  ShipmentWithAllocationsGroup,
} from '../types/spoAllocation.types';
import type {
  DataGridApiFetchParams,
  DataGridApiResponse,
} from '@/components/ui/data-grid';

export type GroupedByShipmentParams = {
  page?: number;
  limit?: number;
  query?: string;
  warehouse_id?: string;
  receipt_status?: string;
  sort?: string;
  dir?: string;
};

export async function getSPOAllocationsGroupedByShipment(
  params: GroupedByShipmentParams = {},
): Promise<{
  data: ShipmentWithAllocationsGroup[];
  pagination: { total: number; page: number; limit: number };
  empty: boolean;
}> {
  const {
    page = 1,
    limit = 50,
    query,
    warehouse_id,
    receipt_status,
    sort = 'shipment_number',
    dir = 'asc',
  } = params;
  const searchParams = new URLSearchParams({
    page: String(page),
    limit: String(limit),
    ...(sort ? { sort } : {}),
    ...(dir ? { dir } : {}),
    ...(query ? { query } : {}),
    ...(warehouse_id ? { warehouse_id } : {}),
    ...(receipt_status ? { receipt_status } : {}),
  });
  const response = await apiFetch(
    `/api/v1/procurement/spo-allocations/grouped-by-shipment?${searchParams.toString()}`,
  );
  if (!response.ok) throw new Error('Failed to fetch SPO allocations grouped by shipment');
  return response.json();
}

export async function getSPOAllocations(
  params: DataGridApiFetchParams & {
    shipment_id?: string;
    warehouse_id?: string;
    receipt_status?: string;
  },
): Promise<DataGridApiResponse<SPOAllocation>> {
  const {
    pageIndex,
    pageSize,
    sorting,
    searchQuery,
    shipment_id,
    warehouse_id,
    receipt_status,
  } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
    ...(shipment_id ? { shipment_id } : {}),
    ...(warehouse_id ? { warehouse_id } : {}),
    ...(receipt_status ? { receipt_status } : {}),
  });
  const response = await apiFetch(
    `/api/v1/procurement/spo-allocations?${queryParams.toString()}`,
  );
  if (!response.ok) throw new Error('Failed to fetch SPO allocations');
  return response.json();
}

export async function getSPOAllocation(
  id: string,
): Promise<SPOAllocationDetail> {
  const response = await apiFetch(`/api/v1/procurement/spo-allocations/${id}`);
  if (!response.ok) throw new Error('Failed to fetch SPO allocation');
  return response.json();
}

export async function createSPOAllocation(
  data: SPOAllocationFormData,
): Promise<SPOAllocation> {
  const response = await apiFetch('/api/v1/procurement/spo-allocations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to create SPO allocation' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function updateSPOAllocation(
  id: string,
  data: Partial<SPOAllocationFormData>,
): Promise<SPOAllocation> {
  const response = await apiFetch(`/api/v1/procurement/spo-allocations/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to update SPO allocation' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function deleteSPOAllocation(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/procurement/spo-allocations/${id}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to delete SPO allocation' }));
    throw new Error(error.message);
  }
}
