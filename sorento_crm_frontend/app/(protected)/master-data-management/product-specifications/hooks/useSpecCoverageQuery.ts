'use client';

import { useQuery } from '@tanstack/react-query';
import { getSpecCoverage } from '../services/productSpecService';
import { SPEC_REGISTRY_QUERY_KEY } from './useSpecRegistryQuery';

/**
 * How many products carry each specification now, and when one was last read (the
 * record header, fix round 5). Under the registry key so every save that already
 * invalidates the registry refreshes these counts too, with no list of its own.
 */
export const SPEC_COVERAGE_QUERY_KEY = [...SPEC_REGISTRY_QUERY_KEY, 'coverage'];

export function useSpecCoverageQuery() {
  return useQuery({
    queryKey: SPEC_COVERAGE_QUERY_KEY,
    queryFn: () => getSpecCoverage(),
    staleTime: 60_000,
  });
}
