'use client';

import { useMutation, useQuery } from '@tanstack/react-query';
import {
  askRecommendation,
  getRecommendationAdvisory,
  getRecommendationExplanation,
  getRunOverview,
} from '../services/explainerService';
import type { ReorderRecommendation } from '../types/reorder.types';

/** Cache key for a rec's generated explanation. The frozen inputs never change,
 *  so this is effectively immutable once fetched — long stale time, no refetch. */
export const explanationKey = (id: string) => ['scm', 'reorder', 'explanation', id];
/** Cache key for a rec's market advisory. */
export const advisoryKey = (id: string) => ['scm', 'reorder', 'advisory', id];
/** Cache key for a run's AI overview. */
export const runOverviewKey = (id: string) => ['scm', 'reorder', 'run-overview', id];

/**
 * Lazily fetch the run-level AI overview — a short brief over the whole run.
 * Cached ~indefinitely (built from the run's frozen aggregates).
 */
export function useRunOverview(runId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: runOverviewKey(runId ?? 'none'),
    queryFn: () => getRunOverview(runId as string),
    enabled: enabled && !!runId,
    refetchOnWindowFocus: false,
    staleTime: Infinity,
    retry: 1,
  });
}

/**
 * Lazily fetch the one-sentence LLM explanation for a recommendation. Only runs
 * when `enabled` (the dialog is open on a buy/exception rec) — the query is not
 * kicked off for every row in the grid. Cached ~indefinitely because the
 * explanation is built from frozen numbers.
 */
export function useRecommendationExplanation(rec: ReorderRecommendation | null, enabled: boolean) {
  return useQuery({
    queryKey: explanationKey(rec?.id ?? 'none'),
    queryFn: () => getRecommendationExplanation(rec as ReorderRecommendation),
    enabled: enabled && !!rec,
    refetchOnWindowFocus: false,
    staleTime: Infinity,
    retry: 1,
  });
}

/**
 * Lazily fetch the optional market advisory. `data.advisory` is null when no
 * market signal matches — the caller hides the callout in that case.
 */
export function useRecommendationAdvisory(rec: ReorderRecommendation | null, enabled: boolean) {
  return useQuery({
    queryKey: advisoryKey(rec?.id ?? 'none'),
    queryFn: () => getRecommendationAdvisory(rec as ReorderRecommendation),
    enabled: enabled && !!rec,
    refetchOnWindowFocus: false,
    staleTime: Infinity,
    retry: 1,
  });
}

/**
 * Ask a bounded question about a recommendation. Returns a react-query mutation
 * whose `mutateAsync(question)` resolves to `{ answer }` — the caller appends it
 * to a local transcript. The answer is grounded in the rec's frozen numbers and
 * may be the exact refusal string when the question can't be answered from them.
 */
export function useAskRecommendation(rec: ReorderRecommendation | null) {
  return useMutation({
    mutationFn: (question: string) => askRecommendation(rec as ReorderRecommendation, question),
  });
}
