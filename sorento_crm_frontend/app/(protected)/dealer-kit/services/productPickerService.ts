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
): Promise<PickerProduct[]> {
  const params = new URLSearchParams({
    limit: String(pageSize),
    offset: String(pageIndex * pageSize),
  });
  if (query.trim()) params.set('query', query.trim());

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
