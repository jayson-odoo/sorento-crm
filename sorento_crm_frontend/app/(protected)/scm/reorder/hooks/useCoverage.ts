'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  acceptCoverageTransfer,
  getCoverageTimeline,
  type CoverageQuery,
} from '../services/coverageService';

/** Query key for one product-at-one-pool timeline. Exported so a mutation can bust it. */
export function coverageKey(q: Partial<CoverageQuery>) {
  return ['scm', 'reorder', 'coverage', q.product_code ?? null, q.pool_code ?? null, q.floor ?? 0] as const;
}

/**
 * The dated Coverage Timeline for one row (UAC Group B).
 *
 * Lazy: `enabled` is the dialog's own open flag, so opening the plan grid does not
 * fetch a timeline per row. **Keyed on product + pool + floor**, which is what makes
 * the dialog's previous/next stepping work - each neighbour is a different cache
 * entry, so stepping refetches instead of showing the previous row's timeline.
 *
 * Not cached long. The timeline is computed and never stored (AC-B6) precisely so it
 * cannot go stale against the documents it summarises, and a long `staleTime` here
 * would put the staleness back on the client.
 */
export function useCoverageTimeline(q: Partial<CoverageQuery>, enabled: boolean) {
  const ready = !!q.product_code && !!q.pool_code;
  return useQuery({
    queryKey: coverageKey(q),
    queryFn: () =>
      getCoverageTimeline({
        product_code: q.product_code as string,
        pool_code: q.pool_code as string,
        floor: q.floor ?? 0,
        product_name: q.product_name ?? null,
      }),
    enabled: enabled && ready,
    staleTime: 30_000,
    retry: 1,
  });
}

/**
 * Accept a cross-site transfer proposal (AC-B1d). Invalidates the timeline it came
 * from, because accepting changes what covers the shortfall.
 */
export function useAcceptCoverageTransfer(q: Partial<CoverageQuery>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (proposalRef: string) => acceptCoverageTransfer(proposalRef),
    onSuccess: (result) => {
      void qc.invalidateQueries({ queryKey: coverageKey(q) });
      toast.success(`Transfer accepted - ${result.transfer_ref}`);
    },
    onError: (e: Error) => toast.error(e.message),
  });
}
