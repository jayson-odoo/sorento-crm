import { apiFetch } from '@/lib/api';
import type { ProductSupplier, ProductSupplierFormData } from '../types/productSupplier.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export async function getProductSuppliers(params: DataGridApiFetchParams & { product_id?: string; supplier_id?: string }): Promise<DataGridApiResponse<ProductSupplier>> {
  const { pageIndex, pageSize, sorting, searchQuery, product_id, supplier_id } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
    ...(product_id ? { product_id } : {}),
    ...(supplier_id ? { supplier_id } : {}),
  });
  const response = await apiFetch(`/api/procurement/product-suppliers?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch product suppliers');
  return response.json();
}

export async function createProductSupplier(data: ProductSupplierFormData): Promise<ProductSupplier> {
  const response = await apiFetch('/api/procurement/product-suppliers', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to create product supplier' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function updateProductSupplier(id: string, data: Partial<ProductSupplierFormData>): Promise<ProductSupplier> {
  const response = await apiFetch(`/api/procurement/product-suppliers/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to update product supplier' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function deleteProductSupplier(id: string): Promise<void> {
  const response = await apiFetch(`/api/procurement/product-suppliers/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to delete product supplier' }));
    throw new Error(error.message);
  }
}

export async function bulkUploadProductSuppliers(file: File): Promise<{ success: number; errors: any[] }> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await apiFetch('/api/procurement/product-suppliers/bulk-upload', {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to upload product suppliers' }));
    throw new Error(error.message);
  }
  return response.json();
}
