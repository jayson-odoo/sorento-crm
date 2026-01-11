import { apiFetch } from '@/lib/api';
import type { AttachmentType, AttachmentTypeFormData } from '../types/attachmentType.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export async function getAttachmentTypes(params: DataGridApiFetchParams): Promise<DataGridApiResponse<AttachmentType>> {
  const { pageIndex, pageSize, sorting, searchQuery } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
  });
  const response = await apiFetch(`/api/resource-management/attachment-types?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch attachment types');
  return response.json();
}

export async function getAttachmentType(id: string): Promise<AttachmentType> {
  const response = await apiFetch(`/api/resource-management/attachment-types/${id}`);
  if (!response.ok) throw new Error('Failed to fetch attachment type');
  return response.json();
}

export async function createAttachmentType(data: AttachmentTypeFormData): Promise<AttachmentType> {
  const response = await apiFetch('/api/resource-management/attachment-types', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to create attachment type' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function updateAttachmentType(id: string, data: Partial<AttachmentTypeFormData>): Promise<AttachmentType> {
  const response = await apiFetch(`/api/resource-management/attachment-types/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to update attachment type' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function deleteAttachmentType(id: string): Promise<void> {
  const response = await apiFetch(`/api/resource-management/attachment-types/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to delete attachment type' }));
    throw new Error(error.message);
  }
}
