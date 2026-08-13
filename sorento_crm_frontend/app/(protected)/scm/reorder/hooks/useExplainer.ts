'use client';

import { useMutation, useQuery } from '@tanstack/react-query';
import {
  askRecommendation,
  askRunChat,
  getMarketProposal,
  getRecommendationAdvisory,
  getRecommendationExplanation,
  getRunOverview,
  searchMarket,
} from '../services/explainerService';
import type { ReorderRecommendation } from '../types/reorder.types';
import type { RunChatTurn } from '../types/explainer.types';

/** Cache key for a rec's generated explanation. The frozen inputs never change,
 *  so this is effectively immutable once fetched - long stale time, no refetch. */
export const explanationKey = (id: string) => ['scm', 'reorder', 'explanation', id];
/** Cache key for a rec's market advisory. */
export const advisoryKey = (id: string) => ['scm', 'reorder', 'advisory', id];
/** Cache key for a run's AI overview. */
export const runOverviewKey = (id: string) => ['scm', 'reorder', 'run-overview', id];

/**
 * Lazily fetch the run-level AI overview - a short brief over the whole run.
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
 * when `enabled` (the dialog is open on a buy/exception rec) - the query is not
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
 * market signal matches - the caller hides the callout in that case.
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
 * whose `mutateAsync(question)` resolves to `{ answer }` - the caller appends it
 * to a local transcript. The answer is grounded in the rec's frozen numbers and
 * may be the exact refusal string when the question can't be answered from them.
 */
export function useAskRecommendation(rec: ReorderRecommendation | null) {
  return useMutation({
    mutationFn: (question: string) => askRecommendation(rec as ReorderRecommendation, question),
  });
}

/**
 * Grounded plan-chat over the whole run (M6-A). `mutateAsync({ question, history })`
 * forwards the prior transcript so follow-ups resolve; the answer reasons over the
 * run's frozen numbers only. The caller keeps the transcript in local state.
 */
export function useRunChat(runId: string | null) {
  return useMutation({
    mutationFn: ({ question, history }: { question: string; history: RunChatTurn[] }) =>
      askRunChat(runId as string, question, history),
  });
}

/**
 * Fire an ad-hoc market web search from the planning flow (M6-B).
 * `mutateAsync({ query, categoryRef?, currency? })` resolves to the cached signals
 * + the run row; the caller surfaces the findings and refreshes rec advisories.
 */
export function useMarketSearch() {
  return useMutation({
    mutationFn: ({
      query,
      categoryRef,
      currency,
    }: {
      query: string;
      categoryRef?: string | null;
      currency?: string | null;
    }) => searchMarket(query, categoryRef, currency),
  });
}

/**
 * Run a live market scan and get a confirm-gated per-line qty PROPOSAL for the
 * run's matching buys (M8-E5). `mutateAsync({ query | signalId, categoryRef? })`
 * resolves to the proposal card; nothing is written until each line is confirmed
 * via a real /adjust override.
 */
export function useMarketProposal(runId: string | null) {
  return useMutation({
    mutationFn: (opts: { signalId?: string | null; query?: string | null; categoryRef?: string | null }) =>
      getMarketProposal(runId as string, opts),
  });
}
