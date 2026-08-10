'use client';

import { useCallback, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  getBuyRecommendationsForCash,
  getAllDispositionRecommendations,
  getCoveredRecommendations,
  getNeedsLevelRecommendations,
} from '../services/reorderRunService';
import { toPlanLines, type PlanLine } from '../lib/planLine';
import { planTotals, type PlanDecision, type PlanDecisionMap } from '../lib/planDecisions';

/**
 * Every line of a plan, in one list, with the buyer's decisions over it.
 *
 * The four fetches stay separate because that is how the endpoint is filtered, but they are
 * merged the moment they land: from here on there is one list, and what kind of line it is
 * is a field on it. No budget appears anywhere in this hook - it is a question for the review
 * panel, asked of the finished decisions.
 *
 * Decisions are client state for now. They are staged the same way the old screen staged
 * accept and adjust, so persisting them is a matter of posting each one; that lands with the
 * confirm step rather than here, so a half-made decision is never written to the run.
 */
export function usePlanLines(runId: string | null, enabled = true) {
  const on = Boolean(runId) && enabled;

  const buys = useQuery({
    queryKey: ['plan-lines', runId, 'buy'],
    queryFn: () => getBuyRecommendationsForCash(runId as string),
    enabled: on,
  });
  const covered = useQuery({
    queryKey: ['plan-lines', runId, 'covered'],
    queryFn: () => getCoveredRecommendations(runId as string),
    enabled: on,
  });
  const needsLevel = useQuery({
    queryKey: ['plan-lines', runId, 'needs_level'],
    queryFn: () => getNeedsLevelRecommendations(runId as string),
    enabled: on,
  });
  const dispositions = useQuery({
    queryKey: ['plan-lines', runId, 'disposition'],
    queryFn: () => getAllDispositionRecommendations(runId as string),
    enabled: on,
  });

  const lines = useMemo<PlanLine[]>(
    () => toPlanLines(buys.data, covered.data, needsLevel.data, dispositions.data),
    [buys.data, covered.data, needsLevel.data, dispositions.data],
  );

  const [decisions, setDecisions] = useState<Record<string, PlanDecision | undefined>>({});

  const decide = useCallback((line: PlanLine, next: PlanDecision) => {
    setDecisions((d) => ({ ...d, [line.id]: next }));
  }, []);

  // Delete the key rather than storing a falsy decision: `undecided` is the absence of an
  // entry, and every count in `planTotals` reads it that way.
  const clear = useCallback((line: PlanLine) => {
    setDecisions((d) => {
      const next = { ...d };
      delete next[line.id];
      return next;
    });
  }, []);

  const totals = useMemo(
    () => planTotals(lines, decisions as PlanDecisionMap),
    [lines, decisions],
  );

  return {
    lines,
    decisions: decisions as PlanDecisionMap,
    decide,
    clear,
    totals,
    isLoading:
      buys.isLoading || covered.isLoading || needsLevel.isLoading || dispositions.isLoading,
    isError: buys.isError || covered.isError || needsLevel.isError || dispositions.isError,
    error: buys.error ?? covered.error ?? needsLevel.error ?? dispositions.error,
    refetch: () => {
      void buys.refetch();
      void covered.refetch();
      void needsLevel.refetch();
      void dispositions.refetch();
    },
  };
}
