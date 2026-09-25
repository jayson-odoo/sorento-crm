import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { ProductCategory, CategoryTreeItem, CategoryFormData } from '../types/category.types';

/**
 * Chatbot stock limits, X / Y (PLAN-chatbot-stock-ask-v2-24sep.md S1):
 *   product_categories.chatbot_max_qty          integer | null  (X: the highest
 *     quantity the assistant may confirm for a product in this category; unset
 *     means the assistant cannot answer any quantity for it, R2)
 *   product_categories.chatbot_eta_offset_days  integer | null  (Y: days added
 *     to a shipment's ETA the assistant quotes; unset means 0 days)
 * Both ride the GET/PUT /api/v1/master-data/product-categories/{id} payload as
 * plain fields; editing either is gated server-side by
 * `master_data.chatbot_stock_limits.edit` (403 on a changed value without it),
 * reading by `.view` (the values are not secret - `.view` gates the FE display
 * only, per the plan's S1 backend seam).
 */

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
 * ---- BACKEND CONTRACT (built, S2 Phase 2) --------------------------------
 *  GET /api/v1/master-data/product-categories/class-labels
 *    -> { data: string[] }
 *    Distinct non-null `product_categories.class_label`, sorted. A tiny read
 *    route beside the categories router, on the existing categories permission.
 */
export async function getProductClassLabels(): Promise<string[]> {
  const response = await apiFetch('/api/v1/master-data/product-categories/class-labels');
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load class labels'));
  }
  const body = (await response.json()) as { data?: string[] };
  return body.data ?? [];
}
