/**
 * The tag canvas's window onto the catalogue.
 *
 * ## API contract
 *
 * ```
 * GET  /api/v1/dealer-kit/products/search?q=&limit=
 *   200 [{ id, product_code, product_name }]
 *
 * GET  /api/v1/dealer-kit/products/{id}/tag-data?promotion_id=
 *   200 { id, code, name, dimensions, spec_lines[], images[], list_price,
 *         offer_price, promotion_id }
 *
 * GET  /api/v1/dealer-kit/product-sets/search?q=&limit=
 *   200 [{ id, set_code, name }]
 *
 * GET  /api/v1/dealer-kit/product-sets/{id}/tag-data?promotion_id=
 *   200 { id, set_code, name, members[], list_price, offer_price, promotion_id }
 *
 * GET  /api/v1/dealer-kit/spec-keys
 *   200 [{ key, label, unit }]
 *
 * POST /api/v1/dealer-kit/tag-templates/resolve-preview
 *   { product_id? , product_set_id?, promotion_id? }
 *   200 { product: ProductTagData | null, product_set: ProductSetTagData | null }
 *   422 when neither id is named.
 * ```
 *
 * Nothing this module returns is ever saved into a template or a tag sheet
 * document. The document holds the binding; these values are resolved again on
 * every open, so a promotion ending overnight changes the tag rather than
 * leaving a stale price on it (ADR 0008).
 */

import type { SearchableSelectOption } from '@/components/common/SearchableSelect';
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  ProductSetTagData,
  ProductTagData,
} from '@/lib/dealer-kit/tag-template-types';
import type { SpecKeyOption } from '@/lib/dealer-kit/merge-fields';

const BASE = '/api/v1/dealer-kit';

export interface ProductSearchItem {
  id: string;
  product_code: string;
  product_name: string;
}

export interface ProductSetSearchItem {
  id: string;
  set_code: string;
  name: string;
}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

/**
 * The spec vocabulary, for the Insert field dialog's Specs group (D58).
 *
 * The dealer-kit read rather than the master-data one: that route is gated on
 * `master_data.products.view`, which the marketing role designing a tag has no
 * reason to hold.
 */
export async function listSpecKeys(): Promise<SpecKeyOption[]> {
  const response = await apiFetch(`${BASE}/spec-keys`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load the spec keys'));
  }
  return response.json();
}

export async function searchProducts(
  query: string,
  limit = 25,
): Promise<ProductSearchItem[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (query.trim()) params.set('q', query.trim());

  const response = await apiFetch(`${BASE}/products/search?${params.toString()}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to search products'));
  }
  return response.json();
}

export async function searchProductSets(
  query: string,
  limit = 25,
): Promise<ProductSetSearchItem[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (query.trim()) params.set('q', query.trim());

  const response = await apiFetch(`${BASE}/product-sets/search?${params.toString()}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to search product sets'));
  }
  return response.json();
}

/** Options for a `SearchableSelect` in async mode. Code first, name underneath. */
export async function productOptions(query: string): Promise<SearchableSelectOption[]> {
  const rows = await searchProducts(query);
  return rows.map((row) => ({
    value: row.id,
    label: row.product_code,
    description: row.product_name,
  }));
}

export async function productSetOptions(
  query: string,
): Promise<SearchableSelectOption[]> {
  const rows = await searchProductSets(query);
  return rows.map((row) => ({
    value: row.id,
    label: row.set_code,
    description: row.name,
  }));
}

// ---------------------------------------------------------------------------
// Tag data
// ---------------------------------------------------------------------------

export async function getProductTagData(
  productId: string,
  promotionId?: string | null,
): Promise<ProductTagData> {
  const params = new URLSearchParams();
  if (promotionId) params.set('promotion_id', promotionId);
  const qs = params.toString();

  const response = await apiFetch(
    `${BASE}/products/${encodeURIComponent(productId)}/tag-data${qs ? `?${qs}` : ''}`,
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load product data'));
  }
  return response.json();
}

export async function getProductSetTagData(
  setId: string,
  promotionId?: string | null,
): Promise<ProductSetTagData> {
  const params = new URLSearchParams();
  if (promotionId) params.set('promotion_id', promotionId);
  const qs = params.toString();

  const response = await apiFetch(
    `${BASE}/product-sets/${encodeURIComponent(setId)}/tag-data${qs ? `?${qs}` : ''}`,
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load product set data'));
  }
  return response.json();
}

// ---------------------------------------------------------------------------
// Preview
// ---------------------------------------------------------------------------

export interface ResolvePreviewResult {
  product: ProductTagData | null;
  product_set: ProductSetTagData | null;
}

export async function resolvePreview(input: {
  productId?: string;
  productSetId?: string;
  promotionId?: string | null;
}): Promise<ResolvePreviewResult> {
  const response = await apiFetch(`${BASE}/tag-templates/resolve-preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      product_id: input.productId ?? null,
      product_set_id: input.productSetId ?? null,
      promotion_id: input.promotionId ?? null,
    }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to resolve preview'));
  }
  return response.json();
}
