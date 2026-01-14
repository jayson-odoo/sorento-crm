import { apiFetch } from '@/lib/api';
import type { Supplier, SupplierFormData, SupplierDetail } from '../types/supplier.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export async function getSuppliers(params: DataGridApiFetchParams & { country?: string; city?: string; payment_terms_days?: number; status?: string }): Promise<DataGridApiResponse<Supplier>> {
  const { pageIndex, pageSize, sorting, searchQuery, country, city, payment_terms_days, status } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
    ...(country ? { country } : {}),
    ...(city ? { city } : {}),
    ...(payment_terms_days ? { payment_terms_days: String(payment_terms_days) } : {}),
    ...(status ? { status } : {}),
  });
  const response = await apiFetch(`/api/v1/procurement/suppliers?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch suppliers');
  return response.json();
}

export async function getSupplier(id: string): Promise<SupplierDetail> {
  const response = await apiFetch(`/api/v1/procurement/suppliers/${id}`);
  if (!response.ok) throw new Error('Failed to fetch supplier');
  return response.json();
}

export async function createSupplier(data: SupplierFormData): Promise<Supplier> {
  const response = await apiFetch('/api/v1/procurement/suppliers', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to create supplier' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function updateSupplier(id: string, data: Partial<SupplierFormData>): Promise<Supplier> {
  const response = await apiFetch(`/api/v1/procurement/suppliers/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to update supplier' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function deleteSupplier(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/procurement/suppliers/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to delete supplier' }));
    throw new Error(error.message);
  }
}
