import { apiFetch } from '@/lib/api';
import type { OrderStatus, OrderStatusFormData, OrderStatusDetail } from '../types/orderStatus.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export async function getOrderStatuses(params: DataGridApiFetchParams): Promise<DataGridApiResponse<OrderStatus>> {
  const { pageIndex, pageSize, sorting, searchQuery } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
  });
  const response = await apiFetch(`/api/v1/order-management/order-statuses?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch order statuses');
  return response.json();
}

export async function getOrderStatus(id: string): Promise<OrderStatusDetail> {
  const response = await apiFetch(`/api/v1/order-management/order-statuses/${id}`);
  if (!response.ok) throw new Error('Failed to fetch order status');
  return response.json();
}

export async function createOrderStatus(data: OrderStatusFormData): Promise<OrderStatus> {
  const response = await apiFetch('/api/v1/order-management/order-statuses', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to create order status' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function updateOrderStatus(id: string, data: Partial<OrderStatusFormData>): Promise<OrderStatus> {
  const response = await apiFetch(`/api/v1/order-management/order-statuses/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to update order status' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function deleteOrderStatus(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/order-management/order-statuses/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to delete order status' }));
    throw new Error(error.message);
  }
}
