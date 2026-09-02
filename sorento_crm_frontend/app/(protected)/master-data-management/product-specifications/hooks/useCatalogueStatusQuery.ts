'use client';

import { useQuery } from '@tanstack/react-query';
import { getCatalogueStatus } from '../services/productSpecService';

export const CATALOGUE_STATUS_QUERY_KEY = ['spec-catalogue-status'];

/**
 * Whether the stored specifications were read with the rules that are live now
 * (AC-A.3). Polls every 3s only while a read is actually running, so an idle
 * screen asks the server nothing.
 */
export function useCatalogueStatusQuery() {
  return useQuery({
    queryKey: CATALOGUE_STATUS_QUERY_KEY,
    queryFn: () => getCatalogueStatus(),
    refetchOnWindowFocus: false,
    refetchInterval: (query) => (query.state.data?.status === 'running' ? 3000 : false),
  });
}
