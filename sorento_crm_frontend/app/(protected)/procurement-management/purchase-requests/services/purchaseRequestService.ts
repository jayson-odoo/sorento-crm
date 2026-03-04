import { apiFetch } from '@/lib/api';
import type {
  PurchaseRequest,
  PurchaseRequestFormData,
  PurchaseRequestDetail,
  SendApprovalLinkRequest,
  SendApprovalLinkResponse,
} from '../types/purchaseRequest.types';

export interface UserForSelect {
  id: string;
  name: string | null;
  email: string;
}

export async function getUsersForApproverSelect(): Promise<UserForSelect[]> {
  const response = await apiFetch('/api/user-management/users/select');
  if (!response.ok) throw new Error('Failed to fetch users');
  return response.json();
}
import type {
  DataGridApiFetchParams,
  DataGridApiResponse,
} from '@/components/ui/data-grid';

export async function getPurchaseRequests(
  params: DataGridApiFetchParams & { requestType?: string; approvalStatus?: string },
): Promise<DataGridApiResponse<PurchaseRequest>> {
  const { pageIndex, pageSize, sorting, searchQuery, requestType, approvalStatus } = params;
  const sortField = sorting?.[0]?.id || 'request_date';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    sort: sortField,
    dir: sortDirection,
    ...(searchQuery ? { query: searchQuery } : {}),
    ...(requestType ? { request_type: requestType } : {}),
    ...(approvalStatus ? { approval_status: approvalStatus } : {}),
  });
  const response = await apiFetch(
    `/api/v1/procurement/purchase-requests?${queryParams.toString()}`,
  );
  if (!response.ok) throw new Error('Failed to fetch purchase requests');
  return response.json();
}

export async function getPurchaseRequest(id: string): Promise<PurchaseRequestDetail> {
  const response = await apiFetch(`/api/v1/procurement/purchase-requests/${id}`);
  if (!response.ok) throw new Error('Failed to fetch purchase request');
  return response.json();
}

export interface PurchaseRequestNeighbours {
  prev_id: string | null;
  next_id: string | null;
  total_count?: number;
  current_index?: number;
}

export async function getPurchaseRequestNeighbours(
  requestId: string,
  requestType?: string | null,
): Promise<PurchaseRequestNeighbours> {
  const params = new URLSearchParams({ id: requestId });
  if (requestType) params.set('request_type', requestType);
  const response = await apiFetch(
    `/api/v1/procurement/purchase-requests/neighbours?${params.toString()}`,
  );
  if (!response.ok) return { prev_id: null, next_id: null, total_count: 0, current_index: 0 };
  return response.json();
}

function toRequestBody(data: PurchaseRequestFormData) {
  const products = (data.products ?? []).map((p) => ({
    item_code: p.item_code ?? null,
    quantity: p.quantity ?? null,
    remark: p.remark ?? null,
  }));
  return {
    request_type: data.request_type,
    request_number: data.request_number ?? null,
    request_date: data.request_date || null,
    customer_name: data.customer_name || null,
    project_title: data.project_title || null,
    purpose: data.purpose || null,
    expected_delivery_date: data.expected_delivery_date || null,
    expected_po_date: data.expected_po_date ?? data.expected_po_date_text ?? null,
    expected_po_date_text: data.expected_po_date_text || null,
    requested_by: data.requested_by || null,
    requested_at: data.requested_at || null,
    products,
  };
}

export async function createPurchaseRequest(
  data: PurchaseRequestFormData,
): Promise<PurchaseRequest> {
  const response = await apiFetch('/api/v1/procurement/purchase-requests', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(toRequestBody(data)),
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to create purchase request' }));
    throw new Error(error.detail || error.message);
  }
  return response.json();
}

export async function updatePurchaseRequest(
  id: string,
  data: Partial<PurchaseRequestFormData>,
): Promise<PurchaseRequest> {
  const body = toRequestBody(data as PurchaseRequestFormData);
  const response = await apiFetch(`/api/v1/procurement/purchase-requests/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to update purchase request' }));
    throw new Error(error.detail || error.message);
  }
  return response.json();
}

export async function deletePurchaseRequest(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/procurement/purchase-requests/${id}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to delete purchase request' }));
    throw new Error(error.detail || error.message);
  }
}

export interface BulkDeletePurchaseRequestsResponse {
  message: string;
  deleted_count: number;
}

export async function bulkDeletePurchaseRequests(
  ids: string[],
): Promise<BulkDeletePurchaseRequestsResponse> {
  const response = await apiFetch('/api/v1/procurement/purchase-requests/bulk', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to bulk delete' }));
    throw new Error(error.detail || error.message);
  }
  return response.json();
}

export async function sendApprovalLink(
  id: string,
  data: SendApprovalLinkRequest,
): Promise<SendApprovalLinkResponse> {
  const response = await apiFetch(
    `/api/v1/procurement/purchase-requests/${id}/send-approval-link`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        approver_email: data.approver_email ?? undefined,
        approver_user_id: data.approver_user_id ?? undefined,
        expires_hours: data.expires_hours ?? 24,
        send_email: data.send_email ?? false,
        base_url: data.base_url ?? undefined,
      }),
    },
  );
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to create approval link' }));
    throw new Error(error.detail || error.message);
  }
  return response.json();
}

export async function setPendingApproval(id: string): Promise<PurchaseRequest> {
  const response = await apiFetch(
    `/api/v1/procurement/purchase-requests/${id}/set-pending-approval`,
    { method: 'POST' },
  );
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to set pending approval' }));
    throw new Error(error.detail || error.message);
  }
  return response.json();
}

export interface ViewLinkResponse {
  view_token: string;
  view_url: string;
}

export async function getOrCreateViewLink(
  id: string,
  baseUrl?: string,
): Promise<ViewLinkResponse> {
  const response = await apiFetch(
    `/api/v1/procurement/purchase-requests/${id}/view-link`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ base_url: baseUrl ?? undefined }),
    },
  );
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to get view link' }));
    throw new Error(error.detail || error.message);
  }
  return response.json();
}

export interface PurchaseRequestUpdateAndReplyData {
  request_number?: string | null;
  reply_message?: string | null;
  /** Full form payload for update-and-reply (from edit form). */
  formData?: Partial<PurchaseRequestFormData>;
}

export async function updatePurchaseRequestAndReply(
  id: string,
  data: PurchaseRequestUpdateAndReplyData,
): Promise<PurchaseRequest> {
  const body: Record<string, unknown> = { reply_message: data.reply_message ?? null };
  if (data.formData) {
    Object.assign(body, toRequestBody(data.formData as PurchaseRequestFormData));
  } else if (data.request_number !== undefined) {
    body.request_number = data.request_number ?? null;
  }
  const response = await apiFetch(
    `/api/v1/procurement/purchase-requests/${id}/update-and-reply`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  );
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to update and reply' }));
    throw new Error(error.detail || error.message);
  }
  return response.json();
}
