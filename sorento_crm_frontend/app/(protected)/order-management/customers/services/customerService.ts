import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { Customer, CustomerFormData, CustomerDetail } from '../types/customer.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

/**
 * Path of the customers neighbours endpoint. Consumed by `useCustomerNeighbours`
 * via the generic `useRecordNeighbours` hook.
 *
 * Contract (see docs/plans/PLAN-record-navigation-standardization.md):
 *   GET /api/v1/order-management/customers/neighbours
 *   Query params: id=<uuid> + the SAME params the list GET accepts
 *                 (query, sort, dir). page/limit are ignored.
 *   Auth: same dependency + module guard as the list GET.
 *   200:  { total: number, index: number|null, prev_id: string|null, next_id: string|null }
 *         - index is 1-based; null when the record is not in the filtered set
 *           (the backend then falls back to the unfiltered, default-sorted set).
 *         - prev_id/next_id wrap circularly; null only when total <= 1.
 */
export const CUSTOMER_NEIGHBOURS_PATH =
  '/api/v1/order-management/customers/neighbours';

export async function getCustomers(params: DataGridApiFetchParams & { status?: string }): Promise<DataGridApiResponse<Customer>> {
  const { pageIndex, pageSize, sorting, searchQuery, status } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
    ...(status ? { status } : {}),
  });
  const response = await apiFetch(`/api/v1/order-management/customers?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch customers');
  return response.json();
}

export async function getCustomer(id: string): Promise<CustomerDetail> {
  const response = await apiFetch(`/api/v1/order-management/customers/${id}`);
  if (!response.ok) throw new Error('Failed to fetch customer');
  return response.json();
}

export async function createCustomer(data: CustomerFormData): Promise<Customer> {
  const response = await apiFetch('/api/v1/order-management/customers', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to create customer'));
  }
  return response.json();
}

export async function updateCustomer(id: string, data: Partial<CustomerFormData>): Promise<Customer> {
  const response = await apiFetch(`/api/v1/order-management/customers/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to update customer'));
  }
  return response.json();
}

export async function deleteCustomer(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/order-management/customers/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to delete customer'));
  }
}
