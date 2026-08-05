import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
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
