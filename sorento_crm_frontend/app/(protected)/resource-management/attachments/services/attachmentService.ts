import { apiFetch } from '@/lib/api';
import type { Attachment, AttachmentType } from '../types/attachment.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export async function getAttachments(params: DataGridApiFetchParams & { entity_type?: string; file_type?: string; upload_date_from?: string; upload_date_to?: string; is_deleted?: boolean; virus_status?: string }): Promise<DataGridApiResponse<Attachment>> {
  const { pageIndex, pageSize, sorting, searchQuery, entity_type, file_type, upload_date_from, upload_date_to, is_deleted, virus_status } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
    ...(entity_type ? { entity_type } : {}),
    ...(file_type ? { file_type } : {}),
    ...(upload_date_from ? { upload_date_from } : {}),
    ...(upload_date_to ? { upload_date_to } : {}),
    ...(is_deleted !== undefined ? { is_deleted: String(is_deleted) } : {}),
    ...(virus_status ? { virus_status } : {}),
  });
  const response = await apiFetch(`/api/resource-management/attachments?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch attachments');
  return response.json();
}

export async function uploadAttachment(file: File, entityType: string, entityId: string, description?: string): Promise<Attachment> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('entity_type', entityType);
  formData.append('entity_id', entityId);
  if (description) formData.append('description', description);

  const response = await apiFetch('/api/resource-management/attachments', {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to upload attachment' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function deleteAttachment(id: string): Promise<void> {
  const response = await apiFetch(`/api/resource-management/attachments/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to delete attachment' }));
    throw new Error(error.message);
  }
}

export async function restoreAttachment(id: string): Promise<void> {
  const response = await apiFetch(`/api/resource-management/attachments/${id}/restore`, { method: 'PUT' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to restore attachment' }));
    throw new Error(error.message);
  }
}

export async function downloadAttachment(id: string): Promise<Blob> {
  const response = await apiFetch(`/api/resource-management/attachments/${id}/download`);
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to download attachment' }));
    throw new Error(error.message);
  }
  return response.blob();
}

export async function getAttachmentMetadata(id: string): Promise<Attachment> {
  const response = await apiFetch(`/api/resource-management/attachments/${id}/metadata`);
  if (!response.ok) throw new Error('Failed to fetch attachment metadata');
  return response.json();
}

export async function checkDuplicateByHash(hash: string): Promise<Attachment | null> {
  const response = await apiFetch(`/api/resource-management/attachments/hash/${hash}`);
  if (!response.ok) return null;
  return response.json();
}
