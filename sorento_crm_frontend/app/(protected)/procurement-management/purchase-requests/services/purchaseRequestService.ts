import { apiFetch } from '@/lib/api';
import type {
  PurchaseRequest,
  PurchaseRequestFormData,
  PurchaseRequestDetail,
} from '../types/purchaseRequest.types';
import type {
  DataGridApiFetchParams,
  DataGridApiResponse,
} from '@/components/ui/data-grid';

export async function getPurchaseRequests(
  params: DataGridApiFetchParams & { requestType?: string },
): Promise<DataGridApiResponse<PurchaseRequest>> {
  const { pageIndex, pageSize, sorting, searchQuery, requestType } = params;
  const sortField = sorting?.[0]?.id || 'request_date';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    sort: sortField,
    dir: sortDirection,
    ...(searchQuery ? { query: searchQuery } : {}),
    ...(requestType ? { request_type: requestType } : {}),
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

function toRequestBody(data: PurchaseRequestFormData) {
  const products = (data.products ?? []).map((p) => ({
    item_code: p.item_code ?? null,
    quantity: p.quantity ?? null,
    remark: p.remark ?? null,
  }));
  return {
    request_type: data.request_type,
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
