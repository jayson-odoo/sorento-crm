import { apiFetch } from '@/lib/api';
import type { Form, FormFormData, FormVersion } from '../types/form.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export type FormsListParams = DataGridApiFetchParams & {
  language?: string;
  status?: string;
  purpose?: string;
  form_type?: string;
};

/**
 * Path of the forms neighbours endpoint. Consumed by `useFormNeighbours`
 * via the generic `useRecordNeighbours` hook.
 *
 * Contract (see docs/plans/PLAN-record-navigation-standardization.md §7):
 *   GET /api/v1/forms-management/forms/neighbours
 *   Query params: id=<uuid> + the SAME params the list GET accepts
 *                 (query, language, status, form_type, sort, dir). page/limit ignored.
 *   Auth: same dependency + module guard as the list GET.
 *   200:  { total: number, index: number|null, prev_id: string|null, next_id: string|null }
 *         - index is 1-based; null when the record is not in the filtered set
 *           (the backend then falls back to the unfiltered, default-sorted set).
 *         - prev_id/next_id wrap circularly; null only when total <= 1.
 */
export const FORM_NEIGHBOURS_PATH = '/api/v1/forms-management/forms/neighbours';

export async function getForms(params: FormsListParams): Promise<DataGridApiResponse<Form>> {
  const { pageIndex, pageSize, sorting, searchQuery, language, status, purpose, form_type } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
    ...(language ? { language } : {}),
    ...(status ? { status } : {}),
    ...(purpose ? { purpose } : {}),
    ...(form_type ? { form_type } : {}),
  });
  const response = await apiFetch(`/api/v1/forms-management/forms?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch forms');
  return response.json();
}

export async function getForm(id: string): Promise<Form> {
  const response = await apiFetch(`/api/v1/forms-management/forms/${id}`);
  if (!response.ok) throw new Error('Failed to fetch form');
  return response.json();
}

export async function createForm(data: FormFormData): Promise<Form> {
  const response = await apiFetch('/api/v1/forms-management/forms', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to create form' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function updateForm(id: string, data: Partial<FormFormData>): Promise<Form> {
  const response = await apiFetch(`/api/v1/forms-management/forms/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to update form' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function deleteForm(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/forms-management/forms/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to delete form' }));
    throw new Error(error.detail || error.message);
  }
}

export async function bulkDeleteForms(ids: string[]): Promise<{ message: string; deleted_count: number }> {
  const response = await apiFetch('/api/v1/forms-management/forms/bulk', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to bulk delete forms' }));
    throw new Error(error.detail || error.message);
  }
  return response.json();
}

export async function duplicateForm(id: string, newCode: string): Promise<Form> {
  const response = await apiFetch(`/api/v1/forms-management/forms/${id}/duplicate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code: newCode }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to duplicate form' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function publishForm(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/forms-management/forms/${id}/publish`, { method: 'POST' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to publish form' }));
    throw new Error(error.message);
  }
}

export async function getFormVersions(formId: string): Promise<FormVersion[]> {
  const response = await apiFetch(`/api/v1/forms-management/forms/${formId}/versions`);
  if (!response.ok) throw new Error('Failed to fetch form versions');
  return response.json();
}
