import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  StockInquiry,
  StockInquiryFormData,
  StockInquiryDetail,
} from '../types/stockInquiry.types';
import type {
  DataGridApiFetchParams,
  DataGridApiResponse,
} from '@/components/ui/data-grid';

/**
 * Path of the stock-inquiry neighbours endpoint. Consumed by
 * `useStockInquiryNeighbours` via the generic `useRecordNeighbours` hook.
 *
 * Contract:
 *   GET /api/v1/procurement/stock-inquiries/neighbours
 *   Query params: id=<uuid> + the SAME params the list GET accepts
 *                 (query, status, sort, dir). page/limit are ignored.
 *   Auth: same dependency + module guard as the list GET.
 *   200:  { total: number, index: number|null, prev_id: string|null, next_id: string|null }
 *         - index is 1-based; null when the record is not in the filtered set
 *           (the backend then falls back to the unfiltered, default-sorted set).
 *         - prev_id/next_id wrap circularly; null only when total <= 1.
 */
export const STOCK_INQUIRY_NEIGHBOURS_PATH =
  '/api/v1/procurement/stock-inquiries/neighbours';

export async function getStockInquiries(
  params: DataGridApiFetchParams & { statuses?: string[] },
): Promise<DataGridApiResponse<StockInquiry>> {
  const { pageIndex, pageSize, sorting, searchQuery, statuses } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
    ...(statuses && statuses.length ? { status: statuses.join(',') } : {}),
  });
  const response = await apiFetch(
    `/api/v1/procurement/stock-inquiries?${queryParams.toString()}`,
  );
  if (!response.ok) throw new Error('Failed to fetch stock inquiries');
  return response.json();
}

export async function getStockInquiry(id: string): Promise<StockInquiryDetail> {
  const response = await apiFetch(`/api/v1/procurement/stock-inquiries/${id}`);
  if (!response.ok) throw new Error('Failed to fetch stock inquiry');
  return response.json();
}

export async function createStockInquiry(
  data: StockInquiryFormData,
): Promise<StockInquiry> {
  const response = await apiFetch('/api/v1/procurement/stock-inquiries', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to create stock inquiry' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function updateStockInquiry(
  id: string,
  data: Partial<StockInquiryFormData>,
): Promise<StockInquiry> {
  const response = await apiFetch(`/api/v1/procurement/stock-inquiries/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to update stock inquiry' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function updateStockInquiryAndReply(
  id: string,
  data: Partial<StockInquiryFormData>,
): Promise<StockInquiry> {
  const response = await apiFetch(
    `/api/v1/procurement/stock-inquiries/${id}/update-and-reply`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    },
  );
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to update and reply' }));
    throw new Error(error.detail || error.message || 'Failed to update and reply');
  }
  return response.json();
}

export async function deleteStockInquiry(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/procurement/stock-inquiries/${id}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to delete stock inquiry' }));
    throw new Error(error.detail || error.message);
  }
}

export async function bulkDeleteStockInquiries(
  ids: string[],
): Promise<{ message: string; deleted_count: number }> {
  const response = await apiFetch('/api/v1/procurement/stock-inquiries/bulk', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to bulk delete stock inquiries' }));
    throw new Error(error.detail || error.message);
  }
  return response.json();
}

export async function linkStockInquiryAttachment(
  inquiryId: string,
  attachmentId: string,
): Promise<{ message: string; link_id: string }> {
  const response = await apiFetch(
    `/api/v1/procurement/stock-inquiries/${inquiryId}/attachments`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ attachment_id: attachmentId }),
    },
  );
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to link attachment' }));
    throw new Error(error.detail || error.message || 'Failed to link attachment');
  }
  return response.json();
}

export async function deleteStockInquiryAttachment(linkId: string): Promise<void> {
  const response = await apiFetch(
    `/api/v1/procurement/stock-inquiries/attachments/${linkId}`,
    { method: 'DELETE' },
  );
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to unlink attachment' }));
    throw new Error(error.detail || error.message || 'Failed to unlink attachment');
  }
}

export interface ResponseAttachmentUploadResult {
  link_id: string;
  attachment_id: string;
  filename: string;
  size: number;
  url: string;
  content_type: string;
}

/**
 * Upload ONE file as a staff "purchasing response" attachment (its own
 * `response_attachment` type/quota, separate from the contact's own uploads).
 * Called once per file - loop for multiple.
 */
export async function uploadStockInquiryResponseAttachment(
  inquiryId: string,
  file: File,
): Promise<ResponseAttachmentUploadResult> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await apiFetch(
    `/api/v1/procurement/stock-inquiries/${inquiryId}/response-attachments`,
    { method: 'POST', body: formData },
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to upload attachment'));
  }
  return response.json();
}

export async function deleteStockInquiryResponseAttachment(linkId: string): Promise<void> {
  const response = await apiFetch(
    `/api/v1/procurement/stock-inquiries/response-attachments/${linkId}`,
    { method: 'DELETE' },
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to unlink attachment'));
  }
}

export interface ViewLinkResponse {
  view_token: string;
  view_url: string;
}

export async function getOrCreateStockInquiryViewLink(
  inquiryId: string,
  baseUrl?: string,
): Promise<ViewLinkResponse> {
  const response = await apiFetch(
    `/api/v1/procurement/stock-inquiries/${inquiryId}/view-link`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(baseUrl != null ? { base_url: baseUrl } : {}),
    },
  );
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Failed to get view link' }));
    const msg = typeof err.detail === 'string' ? err.detail : err.message || 'Failed to get view link';
    throw new Error(msg);
  }
  return response.json();
}

export async function submitStockInquiryForProjectSales(id: string): Promise<StockInquiry> {
  const response = await apiFetch(
    `/api/v1/procurement/stock-inquiries/${id}/submit-for-project-sales`,
    { method: 'POST' },
  );
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || err.message || 'Failed to submit for project sales');
  }
  return response.json();
}

export async function projectSalesApproveStockInquiry(id: string): Promise<StockInquiry> {
  const response = await apiFetch(
    `/api/v1/procurement/stock-inquiries/${id}/project-sales-approve`,
    { method: 'POST' },
  );
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || err.message || 'Failed to approve');
  }
  return response.json();
}

export async function projectSalesRejectStockInquiry(id: string, reason?: string): Promise<StockInquiry> {
  const response = await apiFetch(
    `/api/v1/procurement/stock-inquiries/${id}/project-sales-reject`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: reason ?? null }),
    },
  );
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || err.message || 'Failed to reject');
  }
  return response.json();
}

export async function purchasingRejectStockInquiry(id: string, reason?: string): Promise<StockInquiry> {
  const response = await apiFetch(
    `/api/v1/procurement/stock-inquiries/${id}/purchasing-reject`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: reason ?? null }),
    },
  );
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || err.message || 'Failed to reject');
  }
  return response.json();
}

export async function reopenStockInquiry(id: string, reason?: string): Promise<StockInquiry> {
  const response = await apiFetch(
    `/api/v1/procurement/stock-inquiries/${id}/reopen`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: reason ?? null }),
    },
  );
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || err.message || 'Failed to reopen');
  }
  return response.json();
}

export interface RespondMessageItem {
  messageId?: number;
  channelMessageId?: string;
  contactId?: number;
  channelId?: number;
  traffic?: string;
  message?: {
    type?: string;
    text?: string;
    title?: string;
    messageTag?: string;
    replies?: string[];
    attachment?: {
      ext?: string;
      fileName?: string;
      size?: string;
      mime?: string;
      mimeType?: string;
      type?: string;
      isPending?: boolean;
      url?: string;
    };
  };
  status?: Array<{ value?: string; timestamp?: number; message?: string }>;
  sender?: { source?: string; userId?: number; teamId?: number };
  replyTo?: {
    messageId?: number;
    channelMessageId?: string;
    message?: {
      type?: string;
      text?: string;
      title?: string;
      attachment?: {
        ext?: string;
        fileName?: string;
        type?: string;
        mime?: string;
        mimeType?: string;
      };
    };
  };
}

export interface RespondConversationResponse {
  items: RespondMessageItem[];
  pagination?: { next?: string; previous?: string };
  error?: string;
  contact?: { name?: string | null; phone?: string | null } | null;
}

export async function getStockInquiryConversation(
  inquiryId: string,
  params?: { limit?: number; cursor?: string },
): Promise<RespondConversationResponse> {
  const sp = new URLSearchParams();
  if (params?.limit != null) sp.set('limit', String(params.limit));
  if (params?.cursor) sp.set('cursor', params.cursor);
  const qs = sp.toString();
  const url = `/api/v1/procurement/stock-inquiries/${inquiryId}/conversation${qs ? `?${qs}` : ''}`;
  const response = await apiFetch(url);
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || err.message || 'Failed to load conversation');
  }
  return response.json();
}
