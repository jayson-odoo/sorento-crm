'use client';

import { useQuery } from '@tanstack/react-query';
import { getRecommendationDemand, getRecommendationNet } from '../services/drillService';

/**
 * Lazy net-breakdown drill (M8-A1). Only fires when `enabled` (the Net popover is
 * open). The frozen positions don't change within a run, so it caches long.
 */
export function useExplainNet(recId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ['scm', 'reorder', 'explain-net', recId],
    queryFn: () => getRecommendationNet(recId as string),
    enabled: enabled && !!recId,
    staleTime: 5 * 60_000,
    retry: 1,
  });
}

/**
 * Lazy days-cover demand drill (M8-A2). Fires when the Days-cover popover opens.
 * `warehouseId` is null on a network row (demand sums across warehouses).
 */
export function useExplainDemand(
  productId: string | null,
  warehouseId: string | null,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ['scm', 'reorder', 'explain-demand', productId, warehouseId],
    queryFn: () => getRecommendationDemand(productId as string, warehouseId),
    enabled: enabled && !!productId,
    staleTime: 5 * 60_000,
    retry: 1,
  });
}
