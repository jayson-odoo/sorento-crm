import { apiFetch } from '@/lib/api';
import type { ProductAttachment, ProductAttachmentFormData } from '../types/productAttachment.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export async function getProductAttachments(params: DataGridApiFetchParams & { product_id?: string; attachment_id?: string }): Promise<DataGridApiResponse<ProductAttachment>> {
  const { pageIndex, pageSize, sorting, searchQuery, product_id, attachment_id } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
    ...(product_id ? { product_id } : {}),
    ...(attachment_id ? { attachment_id } : {}),
  });
  const response = await apiFetch(`/api/v1/master-data/product-attachments?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch product attachments');
  return response.json();
}

export async function getProductAttachment(id: string): Promise<ProductAttachment> {
  const response = await apiFetch(`/api/v1/master-data/product-attachments/${id}`);
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to fetch product attachment' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function createProductAttachment(data: ProductAttachmentFormData): Promise<ProductAttachment> {
  const response = await apiFetch('/api/v1/master-data/product-attachments', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to create product attachment' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function updateProductAttachment(id: string, data: Partial<ProductAttachmentFormData>): Promise<ProductAttachment> {
  const response = await apiFetch(`/api/v1/master-data/product-attachments/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to update product attachment' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function deleteProductAttachment(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/master-data/product-attachments/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to delete product attachment' }));
    throw new Error(error.message);
  }
}

export async function getProductAttachmentsByProduct(productId: string): Promise<ProductAttachment[]> {
  const response = await apiFetch(`/api/v1/master-data/product-attachments/product/${productId}`);
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to fetch product attachments' }));
    throw new Error(error.message || 'Failed to fetch product attachments');
  }
  return response.json();
}
