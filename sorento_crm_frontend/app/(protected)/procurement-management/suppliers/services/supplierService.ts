import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { Supplier, SupplierFormData, SupplierDetail } from '../types/supplier.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export type SuppliersListParams = DataGridApiFetchParams & {
  country?: string;
  city?: string;
  payment_terms_days?: number;
  status?: string;
};


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

/** One supplier as a `SearchableSelect` option: name on the row, code still searchable. */
export interface SupplierSelectOption {
  value: string;
  label: string;
  searchText: string;
}

/**
 * Suppliers for a select, SEARCHED ON THE SERVER.
 *
 * `/select` ilikes code + name and caps at 100 rows, so a bare call is only ever a first
 * page. With 194 suppliers on file, a picker that loaded that page once and filtered it in
 * the browser said "No supplier found." for every factory past row 100 - JINBAICHUAN among
 * them - while the same endpoint returned it the moment the query was passed through.
 *
 * Pass this to `SearchableSelect`'s `fetchOptions`, which debounces and re-queries as the
 * user types. The label is the factory's NAME alone (R18) and the code rides in `searchText`,
 * so typing a code still finds it.
 */
export async function searchSuppliersForSelect(query: string): Promise<SupplierSelectOption[]> {
  const qs = query.trim() ? `?query=${encodeURIComponent(query.trim())}` : '';
  const response = await apiFetch(`/api/v1/procurement/suppliers/select${qs}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load suppliers'));
  }
  const rows = (await response.json()) as Array<{
    id: string;
    supplier_code: string | null;
    supplier_name: string | null;
  }>;
  return rows.map((s) => ({
    value: s.id,
    label: s.supplier_name ?? s.supplier_code ?? '',
    searchText: `${s.supplier_code ?? ''} ${s.supplier_name ?? ''}`.trim(),
  }));
}
