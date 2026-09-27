'use client';

import { useQuery } from '@tanstack/react-query';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import { getSpecKeyProducts } from '../services/productSpecService';

export interface SpecKeyProductsParams {
  value?: string;
  q?: string;
  classLabel?: string;
  source?: string;
  limit: number;
  offset: number;
}

/** Every page and facet of one key's products - what to invalidate once a save or a
 *  committed remove has re-read products (S-12). */
export const specKeyProductsKey = (specKey: string) => ['spec-key-products', specKey] as const;

/**
 * One page of products carrying this specification, plus the facets that narrow it
 * (AC-B.5). `LIST_QUERY_OPTIONS` so paging or filtering does not blank the grid while
 * the next page loads - the facets and the row count stay put and only refresh once
 * the new page answers. `classLabel`/`source` ride the query key like every other
 * param here, so picking either refetches rather than filtering the page already held.
 */
export function useSpecKeyProductsQuery(specKey: string, params: SpecKeyProductsParams) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: [...specKeyProductsKey(specKey), params],
    queryFn: () => getSpecKeyProducts(specKey, params),
    enabled: Boolean(specKey),
  });
}
