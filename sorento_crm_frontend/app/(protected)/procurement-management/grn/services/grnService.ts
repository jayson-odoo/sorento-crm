import { apiFetch } from '@/lib/api';
import type { GRN, GRNDetail, GRNFormData } from '../types/grn.types';
import type {
  DataGridApiFetchParams,
  DataGridApiResponse,
} from '@/components/ui/data-grid';

/**
 * `PickingLineResponse` carries `spo_number_raw: string | null` - the SPO number
 * the imported sheet stated for that line, unnormalised, null when the sheet
 * named no single SPO. Sent by GET /api/v1/procurement/grn/{id} and by
 * GET /api/v1/procurement/picking-lines, whose `query` also matches on it.
 * See `documentation/plans/purchasing/PLAN-grn-spo-forward-matching.md`.
 */

export type GRNListParams = DataGridApiFetchParams & {
  picking_status?: string;
  inspection_status?: string;
  spo_allocation_id?: string;
};

/**
 * Path of the GRN neighbours endpoint. Consumed by `useGRNNeighbours` via the
 * generic `useRecordNeighbours` hook.
 *
 * Contract (see docs/plans/PLAN-record-navigation-standardization.md §7):
 *   GET /api/v1/procurement/grn/neighbours
 *   Query params: id=<uuid|picking_number> + the SAME params the list GET accepts
 *                 (query, picking_status, inspection_status, sort, dir).
 *                 page/limit are sent but ignored.
 *   Auth: same dependency + module guard as the list GET.
 *   200:  { total: number, index: number|null, prev_id: string|null, next_id: string|null }
 *       - index is 1-based; null when the record is not in the filtered set
 *           (the backend then falls back to the unfiltered, default-sorted set).
 *       - prev_id/next_id wrap circularly; null only when total <= 1.
 */
export const GRN_NEIGHBOURS_PATH = '/api/v1/procurement/grn/neighbours';

export async function getGRNs(
  params: GRNListParams,
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
    throw new Error(error.detail || error.message);
  }
}

export async function bulkDeleteGRNs(
  ids: string[],
): Promise<{ message: string; deleted_count: number }> {
  const response = await apiFetch('/api/v1/procurement/grn/bulk', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to bulk delete GRNs' }));
    throw new Error(error.detail || error.message);
  }
  return response.json();
}

export interface GRNImportResult {
  message: string;
  job_id: string;
  id: string;
}

export interface ValidateImportResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
  summary?: Record<string, unknown>;
}

export async function validateGRNListing(file: File): Promise<ValidateImportResult> {
  const form = new FormData();
  form.append('file', file);
  const response = await apiFetch(
    '/api/v1/procurement/grn/import-listing?validate_only=true',
    { method: 'POST', body: form },
  );
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Validation failed' }));
    throw new Error(err.detail ?? 'GRN listing validation failed');
  }
  return response.json();
}

export async function validateGRNLines(file: File): Promise<ValidateImportResult> {
  const form = new FormData();
  form.append('file', file);
  const response = await apiFetch(
    '/api/v1/procurement/grn/import-lines?validate_only=true',
    { method: 'POST', body: form },
  );
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Validation failed' }));
    throw new Error(err.detail ?? 'GRN lines validation failed');
  }
  return response.json();
}

export async function importGRNListing(file: File): Promise<GRNImportResult> {
  const form = new FormData();
  form.append('file', file);
  const response = await apiFetch('/api/v1/procurement/grn/import-listing', {
    method: 'POST',
    body: form,
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Import failed' }));
    throw new Error(err.detail ?? 'GRN listing import failed');
  }
  return response.json();
}

export async function importGRNLines(file: File): Promise<GRNImportResult> {
  const form = new FormData();
  form.append('file', file);
  const response = await apiFetch('/api/v1/procurement/grn/import-lines', {
    method: 'POST',
    body: form,
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Import failed' }));
    throw new Error(err.detail ?? 'GRN lines import failed');
  }
  return response.json();
}
