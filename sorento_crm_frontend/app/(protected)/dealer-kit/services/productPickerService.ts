/**
 * The product list the collection picker hand-picks from.
 *
 * Reuses the existing `master-data/products/select` endpoint rather than adding
 * a Dealer-Kit-only one: it is already company-scoped, already the list every
 * other picker in the app shows, and a second endpoint would be a second place
 * for "which products exist" to drift.
 *
 * CONTRACT: GET /api/v1/master-data/products/select -> { data: ProductRow[] }
 */

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

export interface PickerProduct {
  id: string;
  code: string;
  name: string;
  category: string;
  brand: string;
  price: string;
  isDiscontinued: boolean;
}

interface ProductSelectRow {
  id: string;
  product_code: string;
  product_name: string;
  category_name?: string | null;
  brand_name?: string | null;
  list_price?: string | number | null;
  is_discontinued?: boolean | null;
}

/** Page size for every picker. Matches SearchableSelect's default. */
export const PICKER_PAGE_SIZE = 50;

/**
 * Search and page on the SERVER.
 *
 * The catalogue has over 22,000 active products. Loading one page and filtering
 * it in the browser meant a search for a code that exists 998 times answered
 * "no products match" - the term never left the client.
 */
export async function listPickerProducts(
  query = '',
  pageIndex = 0,
  pageSize = PICKER_PAGE_SIZE,
  categoryId = '',
): Promise<PickerProduct[]> {
  const params = new URLSearchParams({
    limit: String(pageSize),
    offset: String(pageIndex * pageSize),
  });
  if (query.trim()) params.set('query', query.trim());
  // Narrows, never replaces: a category plus a term means "search inside this
  // category", which is how somebody finds one basin among four hundred.
  if (categoryId) params.set('category_id', categoryId);

  const response = await apiFetch(`/api/v1/master-data/products/select?${params.toString()}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Could not load products'));

  const body = (await response.json()) as { data?: ProductSelectRow[] } | ProductSelectRow[];
  const rows = Array.isArray(body) ? body : (body.data ?? []);

  return rows.map((row) => ({
    id: row.id,
    code: row.product_code,
    name: row.product_name,
    category: row.category_name ?? '',
    brand: row.brand_name ?? '',
    // Formatting here rather than in the row component keeps the picker free of
    // currency logic; the authoritative formatted price comes from the resolver.
    price: row.list_price == null ? '' : `MYR ${Number(row.list_price).toFixed(2)}`,
    isDiscontinued: Boolean(row.is_discontinued),
  }));
}

export interface PickerCategory {
  id: string;
  name: string;
}

/**
 * Categories, for the chip row above the picker.
 *
 * The chips are the browse half of finding a product; the search box is the
 * other. The planner we studied has only the first and no text search at all,
 * which is why finding a known code there means paging "show more" twelve at a
 * time.
 */
export async function listPickerCategories(): Promise<PickerCategory[]> {
  const response = await apiFetch('/api/v1/master-data/product-categories/select');
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not load categories'));
  }
  const body = (await response.json()) as
    | { data?: { id: string; category_name: string }[] }
    | { id: string; category_name: string }[];
  const rows = Array.isArray(body) ? body : (body.data ?? []);
  return rows.map((row) => ({ id: row.id, name: row.category_name }));
}


/**
 * productId -> a signed thumbnail, for the products a picker is showing.
 *
 * A separate call from the product list on purpose. `products/select` stays the
 * one answer to "which products exist" - a second endpoint returning products
 * would be a second place for that to drift - and this answers only "what does
 * this one look like". Signing is not free, and every picker in the app calls
 * `select` while only this one shows photographs.
 */
export async function listProductThumbnails(
  productIds: string[],
): Promise<Record<string, string>> {
  if (productIds.length === 0) return {};

  const response = await apiFetch('/api/v1/dealer-kit/product-thumbnails', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ productIds }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not load product photos'));
  }

  const wire = (await response.json()) as { urls?: Record<string, string> };
  return wire.urls ?? {};
}
