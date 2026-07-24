'use client';

import { useQuery } from '@tanstack/react-query';
import { getFacts } from './ruleEngineService';

/**
 * Whitelisted rule facts for the given sources. Keyed by the sorted source
 * list so two triggers exposing the same source share one cache entry.
 */
export function useRuleFacts(sources: string[]) {
  const sorted = [...sources].sort();
  return useQuery({
    queryKey: ['rule-facts', sorted],
    queryFn: () => getFacts(sorted),
    enabled: sorted.length > 0,
    staleTime: 1000 * 60 * 5,
  });
}
