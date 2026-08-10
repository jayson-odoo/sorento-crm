'use client';

import { useCallback, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  getCoverSources,
  getLevelSuggestions,
  getPriceHistory,
  getTrajectory,
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
import {
  cheaperAlternative,
  priceKey,
  type CheaperAlternative,
  type PriceAdvice,
} from '../lib/priceAdvice';
import { trajectoryKey, type TrajectoryEntry } from '../lib/trajectory';
import { levelKey, type LevelSuggestion } from '../lib/levelSuggestion';

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

  const prices = useQuery({
    queryKey: ['plan-lines', runId, 'price-history'],
    queryFn: () => getPriceHistory(runId as string),
    enabled: on,
    // Losing the price facts must not take the plan down with them. The grid then shows no
    // price opinion at all, which is honest: it is what the screen said before S12c.
    retry: false,
  });

  const trend = useQuery({
    queryKey: ['plan-lines', runId, 'trajectory'],
    queryFn: () => getTrajectory(runId as string),
    enabled: on,
    // Losing the trend must not take the plan down: the row then shows no trend opinion,
    // which is what the screen said before S13d.
    retry: false,
  });

  const levels = useQuery({
    queryKey: ['plan-lines', runId, 'level-suggestions'],
    queryFn: () => getLevelSuggestions(runId as string),
    enabled: on,
    // Losing the level suggestions must not take the plan down: the row then shows no
    // third suggestion, which is what the screen said before S13f.
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

  /**
   * The price facts for a line's CHOSEN supplier.
   *
   * Undefined when the line has no supplier (a no-supplier exception) or the fetch failed.
   * The caller renders nothing in that case rather than guessing, because "we have no
   * opinion on this price" and "this price is fine" are different answers.
   */
  const priceFor = useCallback(
    (line: PlanLine): PriceAdvice | undefined => {
      const key = priceKey(line.product_id, line.supplier?.code ?? null);
      return key ? prices.data?.prices[key] : undefined;
    },
    [prices.data],
  );

  /**
   * S13e: a materially cheaper supplier on the line's OWN shortlist, or null.
   *
   * Compared on the base-currency figures the ranking already used, gated by the same
   * threshold as price movement (one knob for "a difference worth acting on").
   */
  const movementThresholdPct = prices.data?.movement_threshold_pct ?? 5;
  const cheaperFor = useCallback(
    (line: PlanLine): CheaperAlternative | null => {
      if (!line.purchasable || !line.rec.supplier) return null;
      return cheaperAlternative(line.rec.supplier, line.rec.alternatives, movementThresholdPct);
    },
    [movementThresholdPct],
  );

  /** The level suggestion for a line's product+location. Undefined = no opinion. */
  const levelFor = useCallback(
    (line: PlanLine): LevelSuggestion | undefined => {
      const key = levelKey(line.product_id, line.warehouse_id);
      return key ? levels.data?.suggestions[key] : undefined;
    },
    [levels.data],
  );

  /** The order trend for a line's product+side. Undefined = no opinion, render nothing. */
  const trendFor = useCallback(
    (line: PlanLine): TrajectoryEntry | undefined => {
      const key = trajectoryKey(line.product_id, line.rec.segment);
      return key ? trend.data?.series[key] : undefined;
    },
    [trend.data],
  );

  return {
    lines,
    decisions: decisions as PlanDecisionMap,
    decide,
    clear,
    totals,
    coverFor,
    priceFor,
    cheaperFor,
    trendFor,
    levelFor,
    levelSuggestions: levels.data?.suggestions ?? {},
    staleAfterDays: prices.data?.stale_after_days ?? 180,
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
