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

/**
 * The distinct class labels categories are grouped by, for a picker that has to
 * offer them (PLAN-price-tag-combos.md D2: System Settings' guarded classes).
 *
 * ---- BACKEND CONTRACT (S2 Phase 2 builds this) ----------------------------
 *  GET /api/v1/master-data/product-categories/class-labels
 *    -> { data: string[] }
 *    Distinct non-null `product_categories.class_label`, sorted. A tiny read
 *    route beside the categories router, on the existing categories permission.
 *
 * PHASE 1: the mock below answers instead. DEBT - deleted in Phase 2, when this
 * body becomes the apiFetch call above.
 */
export async function getProductClassLabels(): Promise<string[]> {
  // --- mock ---
  await new Promise((resolve) => setTimeout(resolve, 150));
  return [
    'Bathroom Furniture',
    'Kitchen Sink',
    'Basin',
    'Mirror',
    'Shower',
    'Tap',
    'Water Closet',
  ];
}
