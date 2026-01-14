/**
 * Product Service
 * 
 * API service layer for Product CRUD operations
 */

import { apiFetch } from '@/lib/api';
import type {
  Product,
  ProductFormData,
  ProductFilters,
  ProductApiResponse,
  ProductDetail,
  PriceHistory,
} from '../types/product.types';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';

export interface GetProductsParams extends DataGridApiFetchParams {
  category_id?: string;
  brand_id?: string;
  status?: 'active' | 'inactive' | 'all';
  price_min?: number;
  price_max?: number;
  item_type?: string;
}

/**
 * Get products with pagination, sorting, and filtering
 */
export async function getProducts(
  params: GetProductsParams,
): Promise<ProductApiResponse> {
  const {
    pageIndex,
    pageSize,
    sorting,
    searchQuery,
    category_id,
    brand_id,
    status,
    price_min,
    price_max,
    item_type,
  } = params;

  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';

  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
    ...(category_id ? { category_id } : {}),
    ...(brand_id ? { brand_id } : {}),
    ...(status && status !== 'all' ? { status } : {}),
    ...(price_min ? { price_min: String(price_min) } : {}),
    ...(price_max ? { price_max: String(price_max) } : {}),
    ...(item_type ? { item_type } : {}),
  });

  const response = await apiFetch(
    `/api/v1/master-data/products?${queryParams.toString()}`,
    {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    },
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({
      message: 'Failed to fetch products',
    }));
    throw new Error(error.message || 'Failed to fetch products');
  }

  return response.json();
}

/**
 * Get single product by ID
 */
export async function getProduct(id: string): Promise<ProductDetail> {
  const response = await apiFetch(`/api/v1/master-data/products/${id}`, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
    },
    credentials: 'include',
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({
      message: 'Failed to fetch product',
    }));
    throw new Error(error.message || 'Failed to fetch product');
  }

  return response.json();
}

/**
 * Create new product
 */
export async function createProduct(
  data: ProductFormData,
): Promise<Product> {
  const response = await apiFetch('/api/v1/master-data/products', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({
      message: 'Failed to create product',
    }));
    throw new Error(error.message || 'Failed to create product');
  }

  return response.json();
}

/**
 * Update existing product
 */
export async function updateProduct(
  id: string,
  data: Partial<ProductFormData>,
): Promise<Product> {
  const response = await apiFetch(`/api/v1/master-data/products/${id}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({
      message: 'Failed to update product',
    }));
    throw new Error(error.message || 'Failed to update product');
  }

  return response.json();
}

/**
 * Permanently delete product from database
 */
export async function deleteProduct(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/master-data/products/${id}`, {
    method: 'DELETE',
    headers: {
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({
      message: 'Failed to delete product',
    }));
    throw new Error(error.message || 'Failed to delete product');
  }
}

/**
 * Duplicate product
 */
export async function duplicateProduct(
  id: string,
  newProductCode: string,
): Promise<Product> {
  const response = await apiFetch(`/api/v1/master-data/products/${id}/duplicate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ product_code: newProductCode }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({
      message: 'Failed to duplicate product',
    }));
    throw new Error(error.message || 'Failed to duplicate product');
  }

  return response.json();
}

/**
 * Get price history for a product
 */
export async function getPriceHistory(id: string): Promise<PriceHistory[]> {
  const response = await apiFetch(
    `/api/v1/master-data/products/${id}/price-history`,
    {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    },
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({
      message: 'Failed to fetch price history',
    }));
    throw new Error(error.message || 'Failed to fetch price history');
  }

  return response.json();
}

/**
 * Bulk update products (e.g., status change)
 */
export async function bulkUpdateProducts(
  ids: string[],
  updates: Partial<ProductFormData>,
): Promise<void> {
  const response = await apiFetch('/api/v1/master-data/products/bulk', {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ ids, updates }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({
      message: 'Failed to update products',
    }));
    throw new Error(error.message || 'Failed to update products');
  }
}

/**
 * Bulk delete products
 */
export async function bulkDeleteProducts(ids: string[]): Promise<void> {
  const response = await apiFetch('/api/v1/master-data/products/bulk', {
    method: 'DELETE',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ ids }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({
      message: 'Failed to delete products',
    }));
    throw new Error(error.message || 'Failed to delete products');
  }
}

/**
 * Export products to CSV
 */
export async function exportProducts(
  filters?: ProductFilters,
): Promise<Blob> {
  const queryParams = new URLSearchParams();
  if (filters) {
    if (filters.category_id) queryParams.set('category_id', filters.category_id);
    if (filters.brand_id) queryParams.set('brand_id', filters.brand_id);
    if (filters.is_active !== undefined)
      queryParams.set('is_active', String(filters.is_active));
    if (filters.search) queryParams.set('search', filters.search);
    if (filters.price_range?.min)
      queryParams.set('price_min', String(filters.price_range.min));
    if (filters.price_range?.max)
      queryParams.set('price_max', String(filters.price_range.max));
  }

  const response = await apiFetch(
    `/api/v1/master-data/products/export?${queryParams.toString()}`,
    {
      method: 'GET',
      headers: {
        Accept: 'text/csv',
      },
    },
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({
      message: 'Failed to export products',
    }));
    throw new Error(error.message || 'Failed to export products');
  }

  return response.blob();
}
