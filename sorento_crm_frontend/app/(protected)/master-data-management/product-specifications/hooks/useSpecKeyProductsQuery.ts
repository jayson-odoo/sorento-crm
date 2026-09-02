'use client';

import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { getSpecKeyProducts } from '../services/productSpecService';

export interface SpecKeyProductsParams {
  value?: string;
  q?: string;
  limit: number;
  offset: number;
}

/**
 * One page of products carrying this specification, plus the facets that narrow it
 * (AC-B.5). `keepPreviousData` so paging or filtering does not blank the grid while
 * the next page loads - the facets and the row count stay put and only refresh once
 * the new page answers.
 */
export function useSpecKeyProductsQuery(specKey: string, params: SpecKeyProductsParams) {
  return useQuery({
    queryKey: ['spec-key-products', specKey, params],
    queryFn: () => getSpecKeyProducts(specKey, params),
    enabled: Boolean(specKey),
    placeholderData: keepPreviousData,
  });
}
