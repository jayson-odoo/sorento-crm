import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { Form, FormFormData, FormVersion } from '../types/form.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export type FormsListParams = DataGridApiFetchParams & {
  language?: string;
  status?: string;
  purpose?: string;
  form_type?: string;
};


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
    throw new Error(await extractApiError(response, 'Failed to create form'));
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
    throw new Error(await extractApiError(response, 'Failed to update form'));
  }
  return response.json();
}

export async function deleteForm(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/forms-management/forms/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to delete form'));
  }
}

export async function bulkDeleteForms(ids: string[]): Promise<{ message: string; deleted_count: number }> {
  const response = await apiFetch('/api/v1/forms-management/forms/bulk', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to bulk delete forms'));
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
    throw new Error(await extractApiError(response, 'Failed to duplicate form'));
  }
  return response.json();
}

export async function publishForm(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/forms-management/forms/${id}/publish`, { method: 'POST' });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to publish form'));
  }
}

export async function getFormVersions(formId: string): Promise<FormVersion[]> {
  const response = await apiFetch(`/api/v1/forms-management/forms/${formId}/versions`);
  if (!response.ok) throw new Error('Failed to fetch form versions');
  return response.json();
}
