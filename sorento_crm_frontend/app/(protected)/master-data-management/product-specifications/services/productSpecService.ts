import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  FindabilityResult,
  FindabilityRun,
  SpecDerivationRule,
  SpecSearchPolicyRow,
  ProductSpecDetail,
  ProductSpecRow,
  SpecException,
  SpecPreviewResult,
  SpecRegistryKey,
} from '../types/productSpec.types';

interface Paged<T> {
  data: T[];
  pagination: { total: number; page: number; limit: number };
}

export async function getProductSpecs(params: {
  page?: number;
  limit?: number;
  query?: string;
  status?: string;
}): Promise<Paged<ProductSpecRow>> {
  const search = new URLSearchParams({
    page: String(params.page ?? 1),
    limit: String(params.limit ?? 25),
    ...(params.query ? { query: params.query } : {}),
    ...(params.status ? { status: params.status } : {}),
  });

  const response = await apiFetch(
    `/api/v1/master-data/product-specifications/?${search.toString()}`,
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load product specifications'));
  }
  return response.json();
}

export async function getSpecExceptions(params: {
  page?: number;
  limit?: number;
}): Promise<Paged<SpecException>> {
  const search = new URLSearchParams({
    page: String(params.page ?? 1),
    limit: String(params.limit ?? 25),
  });

  const response = await apiFetch(
    `/api/v1/master-data/product-specifications/exceptions?${search.toString()}`,
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load spec exceptions'));
  }
  return response.json();
}

/**
 * One product's derived specs, or the reason there are none. Used by the
 * Specifications tab on the product record.
 */
export async function getProductSpecDetail(productId: string): Promise<ProductSpecDetail> {
  const response = await apiFetch(
    `/api/v1/master-data/product-specifications/by-product/${productId}`,
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load derived specifications'));
  }
  return response.json();
}

export async function getSpecRegistry(): Promise<{ keys: SpecRegistryKey[] }> {
  const response = await apiFetch('/api/v1/master-data/spec-registry');
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load the spec registry'));
  }
  return response.json();
}

/**
 * Run the ranker exactly as the chatbot would. Returns each candidate's score and the
 * keys it matched on, so a reviewer can see why a result placed where it did.
 */
export async function previewSpecSearch(body: {
  specs: { key: string; value: string | number }[];
  free_terms: string[];
  floor?: number;
  /** The raw sentence, read semantically. */
  phrase?: string;
  /** False to see the literal reading alone, for comparison. */
  understand?: boolean;
}): Promise<SpecPreviewResult> {
  const response = await apiFetch('/api/v1/master-data/product-specifications/preview-search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Spec search preview failed'));
  }
  return response.json();
}

/** Register a new spec key. Owned by whoever creates it — never seed-repaired. */
export async function createSpecKey(body: {
  spec_key: string;
  label: string;
  data_type: string;
  unit?: string | null;
  allowed_values?: string[];
  user_synonyms?: Record<string, string[]>;
  rank_weight?: number;
  is_active?: boolean;
}): Promise<SpecRegistryKey> {
  const response = await apiFetch('/api/v1/master-data/spec-registry', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to create the spec key'));
  }
  return response.json();
}

/**
 * Edit calibration and extend vocabulary. A seeded key's `allowed_values` are
 * rejected by the API on purpose — they are the chatbot parser's contract.
 */
export async function updateSpecKey(
  specKey: string,
  body: {
    label?: string;
    rank_weight?: number;
    is_active?: boolean;
    match_tolerance?: number;
    match_decay?: number;
    user_synonyms?: Record<string, string[]>;
    suppressed_synonyms?: Record<string, string[]>;
    allowed_values?: string[];
    excluded_values?: string[];
    value_weights?: Record<string, number>;
    user_values?: string[];
    suppressed_values?: string[];
    derivation_rules?: SpecDerivationRule[];
    applies_when?: Record<string, string[]>;
  },
): Promise<SpecRegistryKey> {
  const response = await apiFetch(`/api/v1/master-data/spec-registry/${specKey}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to save the spec key'));
  }
  return response.json();
}

/** One spec a given product carries, and where it was read from. */
export interface ProductSpecKey {
  value: string | number | boolean | null;
  source: string | null;
}

/**
 * Which spec keys a product code carries, so the keys table can be filtered by product.
 * `matched_product` is null when the code names nothing.
 */
export async function getKeysForProduct(code: string): Promise<{
  code: string;
  matched_product: { id: string; product_code: string } | null;
  keys: Record<string, ProductSpecKey>;
}> {
  const response = await apiFetch(
    `/api/v1/master-data/spec-registry/keys-for-product?code=${encodeURIComponent(code)}`,
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to look up the product'));
  }
  return response.json();
}

/** Every product carrying a key, with the words each value was read from. */
export interface SpecKeyProduct {
  id: string;
  product_code: string;
  description: string | null;
  class: string | null;
  value: string | number | boolean | null;
  source: string | null;
  evidence: string | null;
}

export interface SpecKeyProducts {
  spec_key: string;
  label: string;
  total: number;
  by_value: { value: string | null; count: number }[];
  by_class: { class: string | null; count: number }[];
  by_source: { source: string | null; count: number }[];
  products: SpecKeyProduct[];
}

/** How many products carry each key right now. Not `measured_coverage`. */
export async function getSpecCoverage(): Promise<{ coverage: Record<string, number> }> {
  const response = await apiFetch('/api/v1/master-data/spec-registry/coverage');
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load the coverage'));
  }
  return response.json();
}

export async function getSpecKeyProducts(
  specKey: string,
  params: { value?: string; q?: string; limit?: number; offset?: number } = {},
): Promise<SpecKeyProducts> {
  const query = new URLSearchParams();
  if (params.value !== undefined) query.set('value', params.value);
  // Searched server-side over the whole key, not over the page on screen.
  if (params.q) query.set('q', params.q);
  query.set('limit', String(params.limit ?? 100));
  query.set('offset', String(params.offset ?? 0));
  const response = await apiFetch(
    `/api/v1/master-data/spec-registry/${specKey}/products?${query.toString()}`,
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load the products'));
  }
  return response.json();
}

/** Read one product again with the rules that are live now. */
export async function rederiveProduct(productId: string): Promise<{ written: number }> {
  const response = await apiFetch(
    `/api/v1/master-data/product-specifications/by-product/${productId}/rederive`,
    { method: 'POST' },
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not read this product again'));
  }
  return response.json();
}

/** Set a value the catalogue never states. Held against every later re-derivation. */
export async function setSpecValueByHand(
  productId: string,
  specKey: string,
  value: string | number | boolean,
): Promise<void> {
  const response = await apiFetch(
    `/api/v1/master-data/product-specifications/by-product/${productId}/values/${specKey}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ value }),
    },
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not save the value'));
  }
}

/**
 * Correct the flyer card this product's specs are read from, and read it again.
 *
 * The card text comes from a machine reading of the printed flyer, and that reading
 * missed cards. Sending an empty string means the product has no flyer card at all.
 */
export async function setFlyerText(
  productId: string,
  text: string,
): Promise<{ flyer_text: string | null }> {
  const response = await apiFetch(
    `/api/v1/master-data/product-specifications/by-product/${productId}/flyer-text`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    },
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not save the flyer text'));
  }
  return response.json();
}

/** Drop a hand-set value and let the rules own the key again. */
export async function clearSpecValueByHand(productId: string, specKey: string): Promise<void> {
  const response = await apiFetch(
    `/api/v1/master-data/product-specifications/by-product/${productId}/values/${specKey}`,
    { method: 'DELETE' },
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not clear the value'));
  }
}

export async function deleteSpecKey(specKey: string): Promise<void> {
  const response = await apiFetch(`/api/v1/master-data/spec-registry/${specKey}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to delete the spec key'));
  }
}


/** Every scoring knob the ranker reads, with its shipped default alongside. */
export async function getSearchPolicy(): Promise<{ policy: SpecSearchPolicyRow[] }> {
  const response = await apiFetch('/api/v1/master-data/spec-registry/policy');
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load the search settings'));
  }
  return response.json();
}

export async function updateSearchPolicy(
  policyKey: string,
  value: number,
): Promise<{ policy_key: string; value: number }> {
  const response = await apiFetch(`/api/v1/master-data/spec-registry/policy/${policyKey}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ value }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to save the search setting'));
  }
  return response.json();
}


export interface CatalogueStatus {
  status: 'idle' | 'running' | 'done' | 'failed';
  started_at: string | null;
  finished_at: string | null;
  result: { codes?: number; written?: number; error?: string } | null;
  /** The rules have been edited since the stored specifications were read. */
  rules_changed_since_last_read: boolean;
  ever_read: boolean;
}

export async function getCatalogueStatus(): Promise<CatalogueStatus> {
  const response = await apiFetch('/api/v1/master-data/spec-registry/catalogue-status');
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to read the catalogue status'));
  }
  return response.json();
}

/** Re-read every product with the rules as they stand now. Runs in the background. */
export async function rereadCatalogue(): Promise<{ status: string }> {
  const response = await apiFetch('/api/v1/master-data/spec-registry/reread-catalogue', {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to start reading the catalogue'));
  }
  return response.json();
}

// --- Findability: can a customer find this product by describing it? ---------------

export async function getFlyers(): Promise<{
  flyers: { source_id: string; source_label: string; cards: number; last_run: string | null }[];
}> {
  const response = await apiFetch(
    '/api/v1/master-data/product-specifications/findability/flyers',
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load flyers'));
  }
  return response.json();
}

export async function runFindability(params: {
  sourceId?: string;
  window?: number;
  limit?: number;
}): Promise<FindabilityRun> {
  const search = new URLSearchParams({
    ...(params.sourceId ? { source_id: params.sourceId } : {}),
    ...(params.window ? { window: String(params.window) } : {}),
    ...(params.limit ? { limit: String(params.limit) } : {}),
  });
  const response = await apiFetch(
    `/api/v1/master-data/product-specifications/findability/run?${search.toString()}`,
    { method: 'POST' },
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to run the findability sweep'));
  }
  return response.json();
}

export async function getFindabilityRuns(
  sourceId?: string,
): Promise<{ runs: FindabilityRun[] }> {
  const search = new URLSearchParams(sourceId ? { source_id: sourceId } : {});
  const response = await apiFetch(
    `/api/v1/master-data/product-specifications/findability/runs?${search.toString()}`,
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load past sweeps'));
  }
  return response.json();
}

export async function getFindabilityRun(
  runId: string,
  params: { boundary?: string; q?: string } = {},
): Promise<{ run: FindabilityRun; results: FindabilityResult[] }> {
  const search = new URLSearchParams({
    ...(params.boundary ? { boundary: params.boundary } : {}),
    ...(params.q ? { q: params.q } : {}),
  });
  const response = await apiFetch(
    `/api/v1/master-data/product-specifications/findability/runs/${runId}?${search.toString()}`,
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load the sweep'));
  }
  return response.json();
}
