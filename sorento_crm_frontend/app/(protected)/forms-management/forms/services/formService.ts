import { apiFetch } from '@/lib/api';
import type { Form, FormFormData, FormVersion } from '../types/form.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export async function getForms(params: DataGridApiFetchParams & { language?: string; status?: string; purpose?: string }): Promise<DataGridApiResponse<Form>> {
  const { pageIndex, pageSize, sorting, searchQuery, language, status, purpose } = params;
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
  });
  const response = await apiFetch(`/api/forms-management/forms?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch forms');
  return response.json();
}

export async function getForm(id: string): Promise<Form> {
  const response = await apiFetch(`/api/forms-management/forms/${id}`);
  if (!response.ok) throw new Error('Failed to fetch form');
  return response.json();
}

export async function createForm(data: FormFormData): Promise<Form> {
  const response = await apiFetch('/api/forms-management/forms', {
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
  const response = await apiFetch(`/api/forms-management/forms/${id}`, {
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
  const response = await apiFetch(`/api/forms-management/forms/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to delete form' }));
    throw new Error(error.message);
  }
}

export async function duplicateForm(id: string, newCode: string): Promise<Form> {
  const response = await apiFetch(`/api/forms-management/forms/${id}/duplicate`, {
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
  const response = await apiFetch(`/api/forms-management/forms/${id}/publish`, { method: 'POST' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to publish form' }));
    throw new Error(error.message);
  }
}

export async function getFormVersions(formId: string): Promise<FormVersion[]> {
  const response = await apiFetch(`/api/forms-management/forms/${formId}/versions`);
  if (!response.ok) throw new Error('Failed to fetch form versions');
  return response.json();
}
