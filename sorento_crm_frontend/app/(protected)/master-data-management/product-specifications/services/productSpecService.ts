import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
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
  include_accessories?: boolean;
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
    allowed_values?: string[];
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

export async function deleteSpecKey(specKey: string): Promise<void> {
  const response = await apiFetch(`/api/v1/master-data/spec-registry/${specKey}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to delete the spec key'));
  }
}
