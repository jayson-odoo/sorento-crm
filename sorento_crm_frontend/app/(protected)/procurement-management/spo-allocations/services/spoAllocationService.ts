import { apiFetch } from '@/lib/api';
import type {
  SPOAllocation,
  SPOAllocationDetail,
  SPOAllocationFormData,
  ShipmentWithAllocationsGroup,
  SPOWithAllocationsGroup,
} from '../types/spoAllocation.types';
import type {
  DataGridApiFetchParams,
  DataGridApiResponse,
} from '@/components/ui/data-grid';

export type GroupedByShipmentParams = {
  page?: number;
  limit?: number;
  query?: string;
  product_code?: string;
  warehouse_id?: string;
  receipt_status?: string;
  sort?: string;
  dir?: string;
};

export type GroupedBySPONumberParams = {
  page?: number;
  limit?: number;
  query?: string;
  product_code?: string;
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
    product_code,
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
    ...(product_code ? { product_code } : {}),
    ...(warehouse_id ? { warehouse_id } : {}),
    ...(receipt_status ? { receipt_status } : {}),
  });
  const response = await apiFetch(
    `/api/v1/procurement/spo-allocations/grouped-by-shipment?${searchParams.toString()}`,
  );
  if (!response.ok) throw new Error('Failed to fetch SPO allocations grouped by shipment');
  return response.json();
}

export async function getSPOAllocationsGroupedBySPONumber(
  params: GroupedBySPONumberParams = {},
): Promise<{
  data: SPOWithAllocationsGroup[];
  pagination: { total: number; page: number; limit: number };
  empty: boolean;
}> {
  const {
    page = 1,
    limit = 50,
    query,
    product_code,
    warehouse_id,
    receipt_status,
    sort = 'spo_number',
    dir = 'asc',
  } = params;
  const searchParams = new URLSearchParams({
    page: String(page),
    limit: String(limit),
    ...(sort ? { sort } : {}),
    ...(dir ? { dir } : {}),
    ...(query ? { query } : {}),
    ...(product_code ? { product_code } : {}),
    ...(warehouse_id ? { warehouse_id } : {}),
    ...(receipt_status ? { receipt_status } : {}),
  });
  const response = await apiFetch(
    `/api/v1/procurement/spo-allocations/grouped-by-spo-number?${searchParams.toString()}`,
  );
  if (!response.ok) throw new Error('Failed to fetch SPO allocations grouped by SPO number');
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

export async function bulkDeleteSPOAllocations(
  ids: string[],
): Promise<{ message: string; deleted_count: number }> {
  const response = await apiFetch('/api/v1/procurement/spo-allocations/bulk', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to bulk delete SPO allocations' }));
    throw new Error(error.message);
  }
  return response.json();
}

export type SPOImportResult = {
  job_ids: string[];
  message: string;
};

export interface ValidateImportResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
  summary?: Record<string, unknown>;
}

/**
 * Validate one or more SPO files without importing (same validation as import).
 * Errors/warnings are aggregated across all files; multi-file messages are
 * prefixed with the filename so the source is clear.
 */
export async function validateSPOAllocations(
  files: File | File[],
): Promise<ValidateImportResult> {
  const list = Array.isArray(files) ? files : [files];
  const formData = new FormData();
  for (const file of list) {
    formData.append('files', file);
  }
  const response = await apiFetch(
    '/api/v1/procurement/spo-allocations/import?validate_only=true',
    { method: 'POST', body: formData },
  );
  if (!response.ok) {
    const err = await response
      .json()
      .catch(() => ({ detail: 'Validation failed' }));
    throw new Error(err.detail ?? 'SPO validation failed');
  }
  return response.json();
}

/**
 * Import SPO allocations from one or more Excel files.
 * Filename = SPO number (e.g. SPO-2025.10-0050.xlsx).
 * One import job per file; processed in background. Track progress in Import Jobs; notification when done.
 */
export async function importSPOAllocations(files: File[]): Promise<SPOImportResult> {
  if (!files?.length) {
    throw new Error('At least one file is required.');
  }
  const formData = new FormData();
  for (const file of files) {
    formData.append('files', file);
  }
  const response = await apiFetch('/api/v1/procurement/spo-allocations/import', {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to import SPO allocations' }));
    throw new Error(error.detail ?? error.message ?? 'Failed to import SPO allocations');
  }
  return response.json();
}
