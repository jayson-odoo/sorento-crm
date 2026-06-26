import { apiFetch } from '@/lib/api';
import type { Supplier, SupplierFormData, SupplierDetail } from '../types/supplier.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export type SuppliersListParams = DataGridApiFetchParams & {
  country?: string;
  city?: string;
  payment_terms_days?: number;
  status?: string;
};

/**
 * Path of the suppliers neighbours endpoint. Consumed by `useSupplierNeighbours`
 * via the generic `useRecordNeighbours` hook.
 *
 * Contract (see docs/plans/PLAN-record-navigation-standardization.md):
 *   GET /api/v1/procurement/suppliers/neighbours
 *   Query params: id=<uuid> + the SAME params the list GET accepts
 *                 (query, sort, dir). page/limit are ignored.
 *   Auth: same dependency + module guard as the list GET.
 *   200:  { total: number, index: number|null, prev_id: string|null, next_id: string|null }
 *         - index is 1-based; null when the record is not in the filtered set
 *           (the backend then falls back to the unfiltered, default-sorted set).
 *         - prev_id/next_id wrap circularly; null only when total <= 1.
 */
export const SUPPLIER_NEIGHBOURS_PATH = '/api/v1/procurement/suppliers/neighbours';

export async function getSuppliers(params: SuppliersListParams): Promise<DataGridApiResponse<Supplier>> {
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
