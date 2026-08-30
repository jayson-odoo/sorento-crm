import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { Customer, CustomerFormData, CustomerDetail } from '../types/customer.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';


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
