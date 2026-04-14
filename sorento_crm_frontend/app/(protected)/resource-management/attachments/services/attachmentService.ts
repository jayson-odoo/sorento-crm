import { apiFetch } from '@/lib/api';
import type { Attachment, AttachmentType } from '../types/attachment.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export async function getAttachments(params: DataGridApiFetchParams & { entity_type?: string; file_type?: string; upload_date_from?: string; upload_date_to?: string; is_deleted?: boolean; virus_status?: string; directory_id?: string | null; resolve_signed_urls?: boolean }): Promise<DataGridApiResponse<Attachment>> {
  const { pageIndex, pageSize, sorting, searchQuery, entity_type, file_type, upload_date_from, upload_date_to, is_deleted, virus_status, directory_id, resolve_signed_urls } = params;
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
    ...(directory_id != null && directory_id !== '' ? { directory_id } : {}),
    ...(resolve_signed_urls !== undefined ? { resolve_signed_urls: String(resolve_signed_urls) } : {}),
  });
  const response = await apiFetch(`/api/v1/resource-management/attachments?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch attachments');
  return response.json();
}

export async function uploadAttachment(
  file: File,
  options: {
    attachmentTypeId?: string | null;
    entityType?: string;
    entityId?: string;
    accessLevels?: string[];
    directoryId?: string | null;
  }
): Promise<Attachment> {
  const { attachmentTypeId, entityType, entityId, accessLevels, directoryId } = options;
  const formData = new FormData();
  formData.append('file', file);
  if (attachmentTypeId) formData.append('attachment_type_id', attachmentTypeId);
  if (entityType) formData.append('entity_type', entityType);
  if (entityId) formData.append('entity_id', entityId);
  if (directoryId) formData.append('directory_id', directoryId);
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

/**
 * Get the current Stock_List attachment (the one non-archived with type Stock_List). Returns null if none.
 */
export async function getCurrentStockListAttachment(): Promise<Attachment | null> {
  const response = await apiFetch('/api/v1/resource-management/attachments/current-stock-list');
  if (response.status === 404) return null;
  if (!response.ok) throw new Error('Failed to fetch Stock List attachment');
  return response.json();
}

/**
 * Replace the Stock_List attachment. Archives any existing one with type Stock_List, then uploads the new file (for n8n AI agent).
 */
export async function replaceLatestStockList(file: File): Promise<Attachment> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await apiFetch('/api/v1/resource-management/attachments/replace-latest-stock-list', {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const contentType = response.headers.get('content-type') || '';
    let message = 'Failed to save Stock List attachment';
    try {
      if (contentType.includes('application/json')) {
        const error = await response.json();
        const detail = error.detail;
        message = typeof detail === 'string' ? detail : message;
      }
    } catch {
      // ignore
    }
    throw new Error(message);
  }
  return response.json();
}

export interface BulkImportJobStarted {
  message: string;
  job_id: string;
  id: string;
}

export interface JobStatusResponse {
  job_id: string;
  status: string;
  progress?: {
    total: number;
    processed: number;
    successful: number;
    failed: number;
    skipped: number;
    percentage: number;
  };
  result?: {
    message?: string;
    directories_created?: number;
    attachments_created?: number;
    attachments?: Array<{ id: string; path: string }>;
    errors?: string[];
  };
  error?: string;
}

export async function bulkImportAttachments(
  zipFile: File,
  attachmentTypeId: string,
  accessLevels?: string[],
  parentDirectoryId?: string | null
): Promise<BulkImportJobStarted> {
  const formData = new FormData();
  formData.append('file', zipFile);
  formData.append('attachment_type_id', attachmentTypeId);
  if (accessLevels && accessLevels.length > 0) {
    formData.append('access_levels', JSON.stringify(accessLevels));
  }
  if (parentDirectoryId) {
    formData.append('parent_directory_id', parentDirectoryId);
  }

  const response = await apiFetch('/api/v1/resource-management/attachments/bulk-import', {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const contentType = response.headers.get('content-type') || '';
    let message = 'Bulk import failed';
    try {
      if (contentType.includes('application/json')) {
        const error = await response.json();
        const detail = error.detail;
        message = typeof detail === 'string' ? detail : error.message ?? message;
      }
    } catch {
      // ignore
    }
    throw new Error(message);
  }
  return response.json();
}

export async function getJobStatus(jobId: string): Promise<JobStatusResponse> {
  const response = await apiFetch(`/api/v1/system/jobs/${jobId}/status`);
  if (!response.ok) throw new Error('Failed to fetch job status');
  return response.json();
}

export async function updateAttachment(
  attachmentId: string,
  data: { directory_id?: string | null; description?: string | null; access_levels?: string[] | null }
): Promise<Attachment> {
  const response = await apiFetch(`/api/v1/resource-management/attachments/${attachmentId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to update attachment' }));
    const message = typeof error.detail === 'string' ? error.detail : error.message ?? 'Failed to update attachment';
    throw new Error(message);
  }
  return response.json();
}

export async function deleteAttachment(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/resource-management/attachments/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to delete attachment' }));
    throw new Error(error.detail ?? error.message ?? 'Failed to delete attachment');
  }
}

export async function archiveAttachment(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/resource-management/attachments/${id}/archive`, { method: 'POST' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to archive attachment' }));
    throw new Error(error.detail ?? error.message ?? 'Failed to archive attachment');
  }
}

export async function bulkArchiveAttachments(ids: string[]): Promise<{ message: string; archived_count: number }> {
  const response = await apiFetch('/api/v1/resource-management/attachments/bulk-archive', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ attachment_ids: ids }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail ?? error.message ?? 'Failed to archive attachments');
  }
  return response.json();
}

export type AccessPropagationKind = 'product' | 'promotion' | 'form' | 'packing_list';

export interface AccessPropagationTarget {
  kind: AccessPropagationKind;
  entity_id: string;
  code: string;
  name?: string | null;
}

export async function previewBulkAccessLevels(body: {
  attachment_ids?: string[];
  directory_id?: string;
}): Promise<{ attachment_count: number; targets: AccessPropagationTarget[] }> {
  const response = await apiFetch('/api/v1/resource-management/attachments/bulk-access-levels/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Preview failed' }));
    const d = error.detail;
    const message =
      typeof d === 'string'
        ? d
        : typeof d === 'object' && d && 'message' in d
          ? String((d as { message?: string }).message)
          : error.message ?? 'Preview failed';
    throw new Error(message);
  }
  return response.json();
}

export async function applyBulkAccessLevels(body: {
  attachment_ids?: string[];
  directory_id?: string;
  access_levels: string[];
  propagate_to_linked: boolean;
}): Promise<{ updated_attachments: number; propagated?: Record<string, number> | null }> {
  const response = await apiFetch('/api/v1/resource-management/attachments/bulk-access-levels/apply', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Apply failed' }));
    const d = error.detail;
    const message =
      typeof d === 'string'
        ? d
        : typeof d === 'object' && d && 'message' in d
          ? String((d as { message?: string }).message)
          : error.message ?? 'Apply failed';
    throw new Error(message);
  }
  return response.json();
}

export async function reorderAttachments(
  attachmentIds: string[],
  directoryId?: string | null
): Promise<{ message: string; attachment_ids: string[] }> {
  const response = await apiFetch('/api/v1/resource-management/attachments/reorder', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ attachment_ids: attachmentIds, directory_id: directoryId ?? null }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to reorder' }));
    const message = typeof error.detail === 'string' ? error.detail : error.message ?? 'Failed to reorder';
    throw new Error(message);
  }
  return response.json();
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

export async function bulkRestoreAttachments(ids: string[]): Promise<{ restored_count: number }> {
  const results = await Promise.allSettled(ids.map((id) => restoreAttachment(id)));
  const restored = results.filter((r) => r.status === 'fulfilled').length;
  return { restored_count: restored };
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

export async function getAttachmentPreviewUrl(id: string): Promise<string> {
  const response = await apiFetch(`/api/v1/resource-management/attachments/${id}/preview-url`);
  if (!response.ok) throw new Error('Failed to fetch attachment preview URL');
  const data = await response.json();
  return data.preview_url;
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

export async function linkAttachmentToPackingList(attachmentId: string, packingListId: string): Promise<{ message: string; link_id: string }> {
  const response = await apiFetch(`/api/v1/resource-management/attachments/${attachmentId}/link-packing-list`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ packing_list_id: packingListId }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to link' }));
    throw new Error(typeof error.detail === 'string' ? error.detail : error.message ?? 'Failed to link to packing list');
  }
  return response.json();
}

export async function deleteAttachmentLink(linkId: string, entityType: string): Promise<void> {
  const response = await apiFetch(
    `/api/v1/resource-management/attachments/links/${linkId}?entity_type=${encodeURIComponent(entityType)}`,
    { method: 'DELETE' }
  );
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to unlink' }));
    throw new Error(typeof error.detail === 'string' ? error.detail : error.message ?? 'Failed to unlink');
  }
}

/** Unlink a packing list from an attachment when the link is only via the packing list's attachment_id (no link_id). */
export async function unlinkPackingListFromAttachment(attachmentId: string, packingListId: string): Promise<void> {
  const response = await apiFetch(
    `/api/v1/resource-management/attachments/${attachmentId}/unlink-packing-list`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ packing_list_id: packingListId }),
    }
  );
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to unlink' }));
    throw new Error(typeof error.detail === 'string' ? error.detail : error.message ?? 'Failed to unlink packing list');
  }
}
