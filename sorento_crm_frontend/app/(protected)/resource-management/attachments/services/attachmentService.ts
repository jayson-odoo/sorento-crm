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
  const response = await apiFetch(`/api/v1/resource-management/attachments?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch attachments');
  return response.json();
}

export async function uploadAttachment(
  file: File,
  attachmentTypeId: string,
  entityType?: string,
  entityId?: string
): Promise<Attachment> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('attachment_type_id', attachmentTypeId);
  if (entityType) formData.append('entity_type', entityType);
  if (entityId) formData.append('entity_id', entityId);

  // Debug: Log FormData contents
  console.log('FormData entries:');
  Array.from(formData.entries()).forEach(([key, value]) => {
    console.log(`  ${key}:`, value instanceof File ? `File(${value.name}, ${value.size} bytes)` : value);
  });

  // For FormData, we need to ensure no Content-Type is set
  // The apiFetch function should handle this, but let's be explicit
  const response = await apiFetch('/api/v1/resource-management/attachments', {
    method: 'POST',
    body: formData,
    // Don't set headers here - apiFetch will handle it
    // The browser will automatically set Content-Type: multipart/form-data; boundary=...
  });
  
  console.log('Response status:', response.status);
  console.log('Response headers:', Object.fromEntries(response.headers.entries()));
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to upload attachment' }));
    console.error('Upload error:', error);
    throw new Error(error.detail || error.message || 'Failed to upload attachment');
  }
  return response.json();
}

export async function deleteAttachment(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/resource-management/attachments/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to delete attachment' }));
    throw new Error(error.message);
  }
}

export async function restoreAttachment(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/resource-management/attachments/${id}/restore`, { method: 'PUT' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to restore attachment' }));
    throw new Error(error.message);
  }
}

export async function downloadAttachment(id: string): Promise<Blob> {
  const response = await apiFetch(`/api/v1/resource-management/attachments/${id}/download`);
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to download attachment' }));
    throw new Error(error.message);
  }
  return response.blob();
}

export async function getAttachmentMetadata(id: string): Promise<Attachment> {
  const response = await apiFetch(`/api/v1/resource-management/attachments/${id}/metadata`);
  if (!response.ok) throw new Error('Failed to fetch attachment metadata');
  return response.json();
}

export async function checkDuplicateByHash(hash: string): Promise<Attachment | null> {
  const response = await apiFetch(`/api/v1/resource-management/attachments/hash/${hash}`);
  if (!response.ok) return null;
  return response.json();
}

export async function resubmitAttachmentWebhook(id: string): Promise<{ message: string; integration_log_id: string }> {
  const response = await apiFetch(`/api/v1/resource-management/attachments/${id}/resubmit`, {
    method: 'POST',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to resubmit webhook' }));
    throw new Error(error.detail || error.message || 'Failed to resubmit webhook');
  }
  return response.json();
}
