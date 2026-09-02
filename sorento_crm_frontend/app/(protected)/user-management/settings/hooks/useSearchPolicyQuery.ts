'use client';

import { useQuery } from '@tanstack/react-query';
import { getSearchPolicy } from '@/app/(protected)/master-data-management/product-specifications/services/productSpecService';

/** Shared by the query and its mutation's post-save invalidation. */
export const SEARCH_POLICY_QUERY_KEY = ['spec-registry-policy'];

/**
 * Every scoring knob the ranker reads, with its shipped default alongside
 * (AC-C.1). Lives under Settings now; the endpoint is unchanged
 * (`/spec-registry/policy`), so a 403 without `master_data.spec_registry.view`
 * surfaces the same way it would have on Product Specifications.
 */
export function useSearchPolicyQuery() {
  return useQuery({
    queryKey: SEARCH_POLICY_QUERY_KEY,
    queryFn: () => getSearchPolicy(),
    select: (data) => data.policy,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
}
