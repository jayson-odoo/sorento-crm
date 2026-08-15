'use client';

import { useCallback, useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  amendLevelSuggestion,
  getCoverSources,
  getLevelSuggestions,
  getPoBook,
  getPriceHistory,
  getProductEconomics,
  getPurchaseTrend,
  getTrajectory,
  recordLifecycleDecision,
  getBuyRecommendationsForCash,
  getAllDispositionRecommendations,
  getCoveredRecommendations,
  getNeedsLevelRecommendations,
} from '../services/reorderRunService';
import { toPlanLines, type PlanLine } from '../lib/planLine';
import {
  NO_COVER,
  coverForLine,
  type CoverProposal,
  type CoverSource,
  type TakenByWarehouse,
} from '../lib/coverPlan';
import { poolWarehouseIdOf } from '../lib/planLine';
import { planTotals, type PlanDecision, type PlanDecisionMap } from '../lib/planDecisions';
import type { ProductEconomics } from '../lib/productHealth';
import {
  cheaperAlternative,
  priceKey,
  type CheaperAlternative,
  type PriceAdvice,
} from '../lib/priceAdvice';
import { trajectoryKey, type TrajectoryEntry } from '../lib/trajectory';
import { levelKey, type LevelSuggestion } from '../lib/levelSuggestion';
import type { PoReceipt } from '../lib/poCover';
import type { ProductPurchaseTrend } from '../lib/purchaseTrend';

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

  // Lazy, not eager (fix-cluster, 2026-08-12): unlike every other plan-lines fetch, the
  // purchase-trend query is not needed to render the grid at all - the PO cell shows the
  // bare figure until its popover opens, same as `priceFor`'s underlying fetch is used only
  // inside a popup. Fetching it for every product on plan mount was pure waste on a plan
  // most of whose rows the buyer never opens the PO popover for. `requestPurchaseTrend`
  // flips the flag once the FIRST popover opens; react-query then caches the response the
  // normal way, so every later popover on the run is free.
  const [purchaseTrendWanted, setPurchaseTrendWanted] = useState(false);
  const requestPurchaseTrend = useCallback(() => setPurchaseTrendWanted(true), []);
  const purchaseTrend = useQuery({
    queryKey: ['plan-lines', runId, 'purchase-trend'],
    queryFn: () => getPurchaseTrend(runId as string),
    enabled: on && purchaseTrendWanted,
    // Losing the purchase trend must not take the plan down: the PO cell's popup then
    // reads "never purchased", the same honest fallback the order-trend cell already uses
    // for a product it has no opinion on.
    retry: false,
  });

  const poBook = useQuery({
    queryKey: ['plan-lines', runId, 'po-book'],
    queryFn: () => getPoBook(runId as string),
    enabled: on,
    // Losing the receipts must not take the plan down: the row then offers no PO offset,
    // which is what the screen said before S15.
    retry: false,
  });

  const economics = useQuery({
    queryKey: ['plan-lines', runId, 'product-economics'],
    queryFn: () => getProductEconomics(runId as string),
    enabled: on,
    // Losing the economics must not take the plan down: the health cell then shows no
    // opinion, which is honest - "we do not know the margin" is not "the margin is fine".
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
      if (!d?.stock?.sources.length) continue;
      const key = line.product_id ?? '';
      const per = (out[key] ??= {});
      for (const s of d.stock.sources) per[s.warehouse_id] = (per[s.warehouse_id] ?? 0) + s.qty;
    }
    return out;
  }, [lines, decisions]);

  /**
   * The suggested action for a line, against the stock still unspoken for AND inside the
   * scope the policy allows.
   *
   * The scope filter belongs here rather than on the endpoint because the pool is keyed by
   * PRODUCT: two rows of the same product can sit in different pools, so one filtered map
   * would be wrong for one of them.
   */
  const coverScope = cover.data?.cover_scope;
  const coverFor = useCallback(
    (line: PlanLine): CoverProposal => {
      if (!line.purchasable) return NO_COVER;
      const pid = line.product_id ?? '';
      const free: CoverSource[] | undefined = cover.data?.sources[pid];
      const taken = takenByProduct[pid] ?? {};
      // Exclude what THIS line already took, or its own decision would shrink its own options.
      const own = decisions[line.id];
      const mine: Record<string, number> = {};
      for (const s of own?.stock?.sources ?? []) mine[s.warehouse_id] = s.qty;
      const net: Record<string, number> = { ...taken };
      for (const [w, q] of Object.entries(mine)) net[w] = (net[w] ?? 0) - q;
      return coverForLine(line, free, net, {
        scope: coverScope,
        poolWarehouseId: poolWarehouseIdOf(line),
      });
    },
    [cover.data, coverScope, takenByProduct, decisions],
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

  /** The mirror of `trendFor`, on the buy side: what we have actually purchased for a
   *  line's product. Undefined = no opinion (fetch failed or nothing on the run). */
  const purchaseTrendFor = useCallback(
    (line: PlanLine): ProductPurchaseTrend | undefined =>
      line.product_id ? purchaseTrend.data?.products[line.product_id] : undefined,
    [purchaseTrend.data],
  );

  /** S15: the open PO lines carrying this product to this warehouse. Empty = none. */
  const poFor = useCallback(
    (line: PlanLine): PoReceipt[] => {
      const key = levelKey(line.product_id, line.warehouse_id);
      return (key ? poBook.data?.po_book[key] : undefined) ?? [];
    },
    [poBook.data],
  );

  /** S14: record (or withdraw, with null) the buyer's own figure beside the engine's. */
  const qc = useQueryClient();
  const amendLevel = useCallback(
    async (s: LevelSuggestion, amended: number | null) => {
      await amendLevelSuggestion({
        product_id: s.product_id,
        warehouse_id: s.warehouse_id,
        amended_level: amended,
      });
      await qc.invalidateQueries({ queryKey: ['plan-lines', runId, 'level-suggestions'] });
    },
    [qc, runId],
  );

  /** The order trend for a line's product+side. Undefined = no opinion, render nothing. */
  const trendFor = useCallback(
    (line: PlanLine): TrajectoryEntry | undefined => {
      const key = trajectoryKey(line.product_id, line.rec.segment);
      return key ? trend.data?.series[key] : undefined;
    },
    [trend.data],
  );

  /** The sell/turnover facts for a line's product. Undefined = no opinion. */
  const economicsFor = useCallback(
    (line: PlanLine): ProductEconomics | undefined =>
      line.product_id ? economics.data?.products[line.product_id] : undefined,
    [economics.data],
  );

  /** Record (or withdraw, with null) the buyer's keep-or-discontinue answer. */
  const decideLifecycle = useCallback(
    async (productId: string, decision: 'keep' | 'discontinue' | null) => {
      await recordLifecycleDecision({ product_id: productId, decision });
      await qc.invalidateQueries({
        queryKey: ['plan-lines', runId, 'product-economics'],
      });
    },
    [qc, runId],
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
    poFor,
    purchaseTrendFor,
    purchaseTrendWindowMonths: purchaseTrend.data?.window_months ?? 3,
    requestPurchaseTrend,
    economicsFor,
    decideLifecycle,
    healthThresholds: economics.data?.thresholds ?? {
      margin_floor_pct: 15,
      dead_turnover_months: 6,
    },
    amendLevel,
    levelSuggestions: levels.data?.suggestions ?? {},
    staleAfterDays: prices.data?.stale_after_days ?? 180,
    coverSources: cover.data?.sources ?? {},
    coverScope,
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
