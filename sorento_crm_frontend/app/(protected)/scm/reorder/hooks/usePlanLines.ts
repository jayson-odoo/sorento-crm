'use client';

import { useCallback, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  getCoverSources,
  getBuyRecommendationsForCash,
  getAllDispositionRecommendations,
  getCoveredRecommendations,
  getNeedsLevelRecommendations,
} from '../services/reorderRunService';
import { toPlanLines, type PlanLine } from '../lib/planLine';
import {
  NO_COVER,
  proposeCover,
  type CoverProposal,
  type CoverSource,
  type TakenByWarehouse,
} from '../lib/coverPlan';
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

  const cover = useQuery({
    queryKey: ['plan-lines', runId, 'cover-sources'],
    queryFn: () => getCoverSources(runId as string),
    enabled: on,
    // A missing pool means "nothing to cover from", which is a safe reading: the plan then
    // proposes buying, which is what it did before cover existed.
    retry: false,
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

  /**
   * What each warehouse has already given away, per product.
   *
   * Recomputed from the decisions rather than accumulated, so undoing a decision hands the
   * stock straight back. An accumulator would leak: change your mind twice and the pool would
   * still be short.
   */
  const takenByProduct = useMemo<Record<string, TakenByWarehouse>>(() => {
    const out: Record<string, Record<string, number>> = {};
    for (const line of lines) {
      const d = decisions[line.id];
      if (d?.kind !== 'use_stock' || !d.sources?.length) continue;
      const key = line.product_id ?? '';
      const per = (out[key] ??= {});
      for (const s of d.sources) per[s.warehouse_id] = (per[s.warehouse_id] ?? 0) + s.qty;
    }
    return out;
  }, [lines, decisions]);

  /** The suggested action for a line, against the stock still unspoken for. */
  const coverFor = useCallback(
    (line: PlanLine): CoverProposal => {
      if (!line.purchasable) return NO_COVER;
      const pid = line.product_id ?? '';
      const free: CoverSource[] | undefined = cover.data?.[pid];
      const taken = takenByProduct[pid] ?? {};
      // Exclude what THIS line already took, or its own decision would shrink its own options.
      const own = decisions[line.id];
      const mine: Record<string, number> = {};
      if (own?.kind === 'use_stock') {
        for (const s of own.sources ?? []) mine[s.warehouse_id] = s.qty;
      }
      const net: Record<string, number> = { ...taken };
      for (const [w, q] of Object.entries(mine)) net[w] = (net[w] ?? 0) - q;
      return proposeCover(
        Math.ceil(line.order_qty),
        line.warehouse_id ?? null,
        line.rec.segment ?? null,
        free,
        net,
      );
    },
    [cover.data, takenByProduct, decisions],
  );

  return {
    lines,
    decisions: decisions as PlanDecisionMap,
    decide,
    clear,
    totals,
    coverFor,
    coverSources: cover.data ?? {},
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
