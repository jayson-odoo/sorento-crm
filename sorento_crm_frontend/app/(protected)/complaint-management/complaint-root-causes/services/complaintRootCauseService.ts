import { apiFetch } from '@/lib/api';
import type {
  ComplaintRootCause,
  ComplaintRootCauseFormData,
} from '../types/complaintRootCause.types';
import type {
  DataGridApiFetchParams,
  DataGridApiResponse,
} from '@/components/ui/data-grid';

const BASE = '/api/v1/complaints-management/complaint-root-causes';

async function extractError(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json();
    const detail = body?.detail ?? body?.message ?? body?.error;
    if (typeof detail === 'string' && detail.trim()) return detail;
    if (Array.isArray(detail) && detail.length && typeof detail[0]?.msg === 'string') {
      return detail[0].msg;
    }
  } catch {
    /* ignore */
  }
  return fallback;
}

export async function getComplaintRootCauses(
  params: DataGridApiFetchParams,
): Promise<DataGridApiResponse<ComplaintRootCause>> {
  const { pageIndex, pageSize, sorting, searchQuery } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
  });
  const response = await apiFetch(`${BASE}?${queryParams.toString()}`);
  if (!response.ok) {
    throw new Error(await extractError(response, 'Failed to load complaint root causes'));
  }
  return response.json();
}

export async function getComplaintRootCausesSelect(
  query?: string,
): Promise<{ id: string; name: string }[]> {
  const url = query ? `${BASE}/select?query=${encodeURIComponent(query)}` : `${BASE}/select`;
  const response = await apiFetch(url);
  if (!response.ok) {
    throw new Error(await extractError(response, 'Failed to load complaint root causes'));
  }
  return response.json();
}

export async function getComplaintRootCause(id: string): Promise<ComplaintRootCause> {
  const response = await apiFetch(`${BASE}/${id}`);
  if (!response.ok) {
    throw new Error(await extractError(response, 'Failed to fetch complaint root cause'));
  }
  return response.json();
}

export async function createComplaintRootCause(
  data: ComplaintRootCauseFormData,
): Promise<ComplaintRootCause> {
  const response = await apiFetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    throw new Error(await extractError(response, 'Failed to create complaint root cause'));
  }
  return response.json();
}

export async function updateComplaintRootCause(
  id: string,
  data: Partial<ComplaintRootCauseFormData>,
): Promise<ComplaintRootCause> {
  const response = await apiFetch(`${BASE}/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    throw new Error(await extractError(response, 'Failed to update complaint root cause'));
  }
  return response.json();
}

export async function deleteComplaintRootCause(id: string): Promise<void> {
  const response = await apiFetch(`${BASE}/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    throw new Error(await extractError(response, 'Failed to delete complaint root cause'));
  }
}
