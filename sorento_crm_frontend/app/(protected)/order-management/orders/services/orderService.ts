import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  Order,
  OrderFormData,
  OrderDetail,
  OrderLine,
  OrderLineFormData,
  OrderAnnotationPayload,
} from '../types/order.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

/**
 * Path of the orders neighbours endpoint. Consumed by `useOrderNeighbours`
 * via the generic `useRecordNeighbours` hook.
 *
 * Contract (see docs/plans/PLAN-record-navigation-standardization.md):
 *   GET /api/v1/order-management/orders/neighbours
 *   Query params: id=<uuid|order_number> + the SAME params the list GET accepts
 *                 (query, order_status_id, has_order_lines, sort, dir, ...).
 *                 page/limit are ignored.
 *   Auth: same dependency + module guard as the list GET.
 *   200:  { total: number, index: number|null, prev_id: string|null, next_id: string|null }
 *         - index is 1-based; null when the record is not in the filtered set
 *           (the backend then falls back to the unfiltered, default-sorted set).
 *         - prev_id/next_id wrap circularly; null only when total <= 1.
 */
export const ORDER_NEIGHBOURS_PATH =
  '/api/v1/order-management/orders/neighbours';

export async function getOrders(
  params: DataGridApiFetchParams & {
    customer_id?: string;
    order_status_id?: string;
    has_order_lines?: 'all' | 'yes' | 'no';
  },
): Promise<DataGridApiResponse<Order>> {
  const { pageIndex, pageSize, sorting, searchQuery, customer_id, order_status_id, has_order_lines } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
    ...(customer_id ? { customer_id } : {}),
    ...(order_status_id ? { order_status_id } : {}),
    ...(has_order_lines && has_order_lines !== 'all' ? { has_order_lines } : {}),
  });
  const response = await apiFetch(`/api/v1/order-management/orders?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch delivery orders');
  return response.json();
}

export async function getOrder(id: string): Promise<OrderDetail> {
  const response = await apiFetch(`/api/v1/order-management/orders/${id}`);
  if (!response.ok) throw new Error('Failed to fetch delivery order');
  return response.json();
}

export async function createOrder(data: OrderFormData): Promise<Order> {
  const response = await apiFetch('/api/v1/order-management/orders', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to create delivery order' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function updateOrder(id: string, data: Partial<OrderFormData>): Promise<Order> {
  const response = await apiFetch(`/api/v1/order-management/orders/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to update delivery order' }));
    throw new Error(error.message);
  }
  return response.json();
}

/**
 * Annotate the mirror carve-out (internal note + follow-up flag). Allowed even
 * on AutoCount rows — the ONLY mutation the server permits on synced orders.
 * Only the provided fields are applied; returns the full updated order.
 */
export async function annotateOrder(id: string, data: OrderAnnotationPayload): Promise<OrderDetail> {
  const response = await apiFetch(`/api/v1/order-management/orders/${id}/annotation`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to save note'));
  }
  return response.json();
}

export async function deleteOrder(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/order-management/orders/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to delete delivery order' }));
    throw new Error(error.message);
  }
}

export async function bulkDeleteOrders(ids: string[]): Promise<{ message: string; deleted_count: number }> {
  const response = await apiFetch('/api/v1/order-management/orders/bulk', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to bulk delete delivery orders' }));
    throw new Error(error.message);
  }
  return response.json();
}

/**
 * Export all orders to Excel (fetches all data by paginating through all pages)
 */
export async function exportOrders(params?: {
  customer_id?: string;
  order_status_id?: string;
  has_order_lines?: 'all' | 'yes' | 'no';
}): Promise<Order[]> {
  const allOrders: Order[] = [];
  let page = 1;
  const limit = 100; // Backend maximum limit
  let hasMore = true;

  while (hasMore) {
    const queryParams = new URLSearchParams({
      page: String(page),
      limit: String(limit),
      ...(params?.customer_id ? { customer_id: params.customer_id } : {}),
      ...(params?.order_status_id ? { order_status_id: params.order_status_id } : {}),
      ...(params?.has_order_lines && params.has_order_lines !== 'all'
        ? { has_order_lines: params.has_order_lines }
        : {}),
    });

    const response = await apiFetch(`/api/v1/order-management/orders?${queryParams.toString()}`);
    if (!response.ok) {
      throw new Error('Failed to fetch delivery orders for export');
    }

    const result = await response.json();
    const orders = result.data || [];
    allOrders.push(...orders);

    // Check if there are more pages
    const total = result.pagination?.total || 0;
    const currentPageTotal = page * limit;
    hasMore = currentPageTotal < total;
    page++;
  }

  return allOrders;
}

/**
 * Bulk import orders from Excel data
 */
export async function bulkImportOrders(data: Record<string, unknown>[]): Promise<{ created: number; updated: number; errors: string[] }> {
  const response = await apiFetch('/api/v1/order-management/orders/bulk-import', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ orders: data }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to import delivery orders' }));
    throw new Error(error.message || 'Failed to import delivery orders');
  }
  return response.json();
}

export interface ValidateImportResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
  summary?: Record<string, unknown>;
}

/**
 * Validate order tracking file without importing (same validation as import).
 */
export async function validateOrderTracking(file: File): Promise<ValidateImportResult> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await apiFetch(
    '/api/v1/order-management/orders/import-tracking?validate_only=true',
    { method: 'POST', body: formData },
  );
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Validation failed' }));
    throw new Error(error.message || 'Validation failed');
  }
  return response.json();
}

/**
 * Import order tracking data from Excel file (Master + Overall Tracking sheets)
 */
export async function importOrderTracking(file: File): Promise<{
  job_id: string;
  status: string;
  message: string;
}> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await apiFetch('/api/v1/order-management/orders/import-tracking', {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to queue import job' }));
    throw new Error(error.message || 'Failed to queue import job');
  }

  return response.json();
}

export async function createOrderLine(orderId: string, data: OrderLineFormData): Promise<OrderLine> {
  const response = await apiFetch(`/api/v1/order-management/orders/${orderId}/lines`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || error.message || 'Failed to add delivery order line');
  }
  return response.json();
}

export async function updateOrderLine(orderId: string, lineId: string, data: Partial<OrderLineFormData>): Promise<OrderLine> {
  const response = await apiFetch(`/api/v1/order-management/orders/${orderId}/lines/${lineId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || error.message || 'Failed to update delivery order line');
  }
  return response.json();
}

export async function deleteOrderLine(orderId: string, lineId: string): Promise<void> {
  const response = await apiFetch(`/api/v1/order-management/orders/${orderId}/lines/${lineId}`, { method: 'DELETE' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || error.message || 'Failed to delete delivery order line');
  }
}

export async function bulkDeleteOrderLines(
  orderId: string,
  ids: string[],
): Promise<{ message: string; deleted_count: number }> {
  const response = await apiFetch(`/api/v1/order-management/orders/${orderId}/lines/bulk-delete`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || error.message || 'Failed to bulk delete delivery order lines');
  }
  return response.json();
}

export async function importDeliveryOrderDetail(file: File): Promise<{ job_id: string; status: string; message: string }> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await apiFetch('/api/v1/order-management/orders/import-order-lines', {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || error.message || 'Failed to queue import');
  }
  return response.json();
}

export async function validateDeliveryOrderDetail(file: File): Promise<ValidateImportResult> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await apiFetch('/api/v1/order-management/orders/import-order-lines?validate_only=true', {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Validation failed' }));
    throw new Error(error.detail || error.message || 'Validation failed');
  }
  return response.json();
}
