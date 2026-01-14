import { apiFetch } from '@/lib/api';
import type { Order, OrderFormData, OrderDetail } from '../types/order.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export async function getOrders(params: DataGridApiFetchParams & { customer_id?: string; order_status_id?: string }): Promise<DataGridApiResponse<Order>> {
  const { pageIndex, pageSize, sorting, searchQuery, customer_id, order_status_id } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
    ...(customer_id ? { customer_id } : {}),
    ...(order_status_id ? { order_status_id } : {}),
  });
  const response = await apiFetch(`/api/v1/order-management/orders?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch orders');
  return response.json();
}

export async function getOrder(id: string): Promise<OrderDetail> {
  const response = await apiFetch(`/api/v1/order-management/orders/${id}`);
  if (!response.ok) throw new Error('Failed to fetch order');
  return response.json();
}

export async function createOrder(data: OrderFormData): Promise<Order> {
  const response = await apiFetch('/api/v1/order-management/orders', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to create order' }));
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
    const error = await response.json().catch(() => ({ message: 'Failed to update order' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function deleteOrder(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/order-management/orders/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to delete order' }));
    throw new Error(error.message);
  }
}
