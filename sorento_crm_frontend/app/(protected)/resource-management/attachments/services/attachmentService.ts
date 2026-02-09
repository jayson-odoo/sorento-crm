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
  entityId?: string,
  accessLevels?: string[]
): Promise<Attachment> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('attachment_type_id', attachmentTypeId);
  if (entityType) formData.append('entity_type', entityType);
  if (entityId) formData.append('entity_id', entityId);
  if (accessLevels && accessLevels.length > 0) {
    formData.append('access_levels', JSON.stringify(accessLevels));
  }

  const response = await apiFetch('/api/v1/resource-management/attachments', {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const contentType = response.headers.get('content-type') || '';
    let message = 'Failed to upload attachment';
    try {
      if (contentType.includes('application/json')) {
        const error = await response.json();
        // FastAPI uses "detail" (string or array of validation errors)
        const detail = error.detail;
        if (typeof detail === 'string') {
          message = detail;
        } else if (Array.isArray(detail) && detail.length > 0) {
          const first = detail[0];
          message = typeof first === 'string' ? first : (first?.msg || first?.message || JSON.stringify(first));
        } else if (error.message) {
          message = error.message;
        }
      } else {
        const text = await response.text();
        if (text) message = text.slice(0, 200);
      }
    } catch {
      // ignore parse errors, use default message
    }
    if (response.status === 401) {
      message = message || 'Not signed in or session expired. Please sign in again.';
    } else if (response.status === 413) {
      message =
        'File too large. The server limits upload size (often 1MB by default). Try a smaller file or ask your admin to increase nginx client_max_body_size.';
    } else if (response.status >= 500) {
      message = message || 'Server error. Try again or contact support.';
    }
    throw new Error(message);
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

export async function bulkDeleteAttachments(ids: string[]): Promise<{ message: string; deleted_count: number }> {
  const response = await apiFetch('/api/v1/resource-management/attachments/bulk-delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ attachment_ids: ids }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to delete attachments' }));
    throw new Error(error.message ?? error.detail ?? 'Failed to delete attachments');
  }
  return response.json();
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
