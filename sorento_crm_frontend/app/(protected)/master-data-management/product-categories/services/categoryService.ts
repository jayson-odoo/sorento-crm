import { apiFetch } from '@/lib/api';
import type { ProductCategory, CategoryTreeItem, CategoryFormData } from '../types/category.types';

export async function getCategoriesTree(): Promise<CategoryTreeItem[]> {
  const response = await apiFetch('/api/v1/master-data/product-categories/tree', {
    method: 'GET',
  });

  if (!response.ok) {
    throw new Error('Failed to fetch categories');
  }

  return response.json();
}

export async function getCategory(id: string): Promise<ProductCategory> {
  const response = await apiFetch(`/api/v1/master-data/product-categories/${id}`, {
    method: 'GET',
  });

  if (!response.ok) {
    throw new Error('Failed to fetch category');
  }

  return response.json();
}

export async function createCategory(data: CategoryFormData): Promise<ProductCategory> {
  const response = await apiFetch('/api/v1/master-data/product-categories', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to create category' }));
    throw new Error(error.message || 'Failed to create category');
  }

  return response.json();
}

export async function updateCategory(id: string, data: Partial<CategoryFormData>): Promise<ProductCategory> {
  const response = await apiFetch(`/api/v1/master-data/product-categories/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to update category' }));
    throw new Error(error.message || 'Failed to update category');
  }

  return response.json();
}

export async function deleteCategory(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/master-data/product-categories/${id}`, {
    method: 'DELETE',
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    const message =
      (typeof error.detail === 'object' && error.detail?.message) ||
      error.message ||
      'Failed to delete category';
    throw new Error(message);
  }
}

export async function moveCategory(id: string, parentId: string | null, displayOrder: number): Promise<void> {
  const response = await apiFetch(`/api/v1/master-data/product-categories/${id}/move`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ parent_category_id: parentId, display_order: displayOrder }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to move category' }));
    throw new Error(error.message || 'Failed to move category');
  }
}
