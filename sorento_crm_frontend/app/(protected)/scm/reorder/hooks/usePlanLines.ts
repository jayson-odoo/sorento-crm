'use client';

import { useCallback, useMemo, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  amendLevelSuggestion,
  clearPlanRowDecision,
  getCoverSources,
  getLevelSuggestions,
  getPlanRowDecisions,
  getPoBook,
  getPriceHistory,
  getProductEconomics,
  getProductImages,
  getPurchaseTrend,
  getTrajectory,
  recordLifecycleDecision,
  recordPlanRowDecision,
  getBuyRecommendationsForCash,
  getAllDispositionRecommendations,
  getCoveredRecommendations,
  getNeedsLevelRecommendations,
  setMoqOverride,
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
import {
  DEFAULT_PRICE_MODE,
  applyDecisionClears,
  applyDecisionWrites,
  planTotals,
  productIdMap,
  serverDecisionsToMap,
  toRecordPlanRowDecisionPayload,
  type PlanDecision,
  type PlanDecisionMap,
} from '../lib/planDecisions';
import type { PlanRowDecisionListResponse, PlanRowPriceMode } from '../types/decisions.types';
import type { ProductEconomics } from '../lib/productHealth';
import {
  cheaperAlternative,
  priceKey,
  type CheaperAlternative,
  type PriceAdvice,
} from '../lib/priceAdvice';
import { trajectoryKey, type ChannelTrendEntry, type TrajectoryEntry } from '../lib/trajectory';
import { isGroupedLine, type PlanChannel } from '../lib/planLineGrouping';
import type { ProductPhotoStatus } from '../components/ProductPhotoPopover';
import { levelKey, type LevelSuggestion } from '../lib/levelSuggestion';
import { isProjectOnlyLine, type PoReceipt } from '../lib/poCover';
import type { ProductPurchaseTrend } from '../lib/purchaseTrend';

/**
 * Every line of a plan, in one list, with the buyer's decisions over it.
 *
 * The four fetches stay separate because that is how the endpoint is filtered, but they are
 * merged the moment they land: from here on there is one list, and what kind of line it is
 * is a field on it. No budget appears anywhere in this hook - it is a question for the review
 * panel, asked of the finished decisions.
 *
 * Decisions (S16, captain 21 Aug) are the server's own - `decisions` below is the persisted
 * `plan_row_decision` list (`GET .../plan-row-decisions`) folded back into the FE's
 * `PlanDecisionMap`, and `decide`/`clear` write straight through to
 * `POST`/`DELETE .../recommendations/{rec_id}/decision`. There is no local decision
 * state left to drift out of step with it.
 */
/** Cache key for the run's persisted row decisions (S16) - exported so a caller that
 *  clears a run's decisions server-side (the demo Reset action) can invalidate it. */
export const planRowDecisionsKey = (runId: string | null) => ['plan-lines', runId, 'row-decisions'];

/** A pending price/supplier change on a row, before (or alongside) its decision. */
export interface PlanRowChoice {
  priceMode?: PlanRowPriceMode;
  supplierCode?: string;
}

/** The same pair, resolved: never undefined, so a control always has a value to show. */
export interface ResolvedRowChoice {
  priceMode: PlanRowPriceMode;
  supplierCode: string | null;
}

export function usePlanLines(runId: string | null, enabled = true) {
  const on = Boolean(runId) && enabled;
  const qc = useQueryClient();

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

  /** S16: every row decision persisted on this run, plus the "N of Total made" header's
   *  own server-counted decided/total (see `usePlanLines.decidedCount` /
   *  `.totalDecidableCount` below). */
  const planRowDecisions = useQuery({
    queryKey: planRowDecisionsKey(runId),
    queryFn: () => getPlanRowDecisions(runId as string),
    enabled: on,
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

  /**
   * WHICH products have a photo (AC-7), fetched the same lazy way the purchase trend is.
   *
   * > "as IT I do not know what a product looks like"
   *
   * One cheap call for the whole run: it answers only the question the icon asks, so nothing
   * is signed for the thousands of rows nobody opens. `requestProductImages` flips the flag
   * when the FIRST icon opens; the picture itself is a separate per-product fetch inside the
   * popover that wants it.
   */
  const [photosWanted, setPhotosWanted] = useState(false);
  const requestProductImages = useCallback(() => setPhotosWanted(true), []);
  const photos = useQuery({
    queryKey: ['plan-lines', runId, 'product-images'],
    queryFn: () => getProductImages(runId as string),
    enabled: on && photosWanted,
    // Losing the photos must not take the plan down: the popover says so and nothing else on
    // the row changes - a photo is context, never an input to a decision.
    retry: false,
    // Reported in place, so it must not raise the page-level destructive toast.
    meta: { silent: true },
  });

  /** Whether this line's product has a photo to show. */
  const hasPhotoFor = useCallback(
    (line: PlanLine): boolean =>
      !!line.product_id && !!photos.data?.has_image[line.product_id],
    [photos.data],
  );

  /**
   * Where the map is, so the icon knows whether "no photo" is a FACT yet.
   *
   * Dimming before the answer lands would tell the buyer this product has no photo when we
   * have not looked. `data` is checked BEFORE `isError` because react-query keeps the last
   * good map through a failed refetch, and an answer we still hold beats an error about
   * fetching it again.
   */
  const photoStatus: ProductPhotoStatus = !photosWanted
    ? 'idle'
    : photos.data
      ? 'ready'
      : photos.isError
        ? 'error'
        : 'loading';

  /**
   * The server's persisted decisions, folded into the FE's own shape - see
   * `serverDecisionsToMap`. `cover.data?.sources` resolves each stock take's warehouse
   * CODE back to an id (the server only ever stores/returns the code).
   */
  const decisions = useMemo<PlanDecisionMap>(
    () => serverDecisionsToMap(planRowDecisions.data?.data ?? [], lines, cover.data?.sources ?? {}),
    [planRowDecisions.data, lines, cover.data],
  );

  /** `recommendation_id -> product_id`, built once off this run's flat line list - what
   *  `applyDecisionWrites`/`applyDecisionClears` need to recompute `decided_count` by
   *  DISTINCT PRODUCT (R14) rather than per write/clear call (S3 perf review fix: an
   *  increment-per-call double-counted a product decided at two warehouses on a
   *  location-grain, ungrouped run). */
  const productOfMap = useMemo(() => productIdMap(lines), [lines]);
  const productOf = useCallback(
    (recId: string) => productOfMap.get(recId),
    [productOfMap],
  );

  // Read inside `chooseRow`, whose identity must not change with every decision fetch.
  const decisionsRef = useRef(decisions);
  decisionsRef.current = decisions;

  /** The header's own "N of Total made" - counted server-side, never off this session's
   *  own state (S16). */
  const decidedCount = planRowDecisions.data?.decided_count ?? 0;
  const totalDecidableCount = planRowDecisions.data?.total_count ?? 0;

  /**
   * Record a row decision. A GROUPED (product-grain) line fans the SAME decision out to
   * every member recommendation id, exactly the way `updateMoq` already fans a MOQ edit
   * out - this hook is the only place that knows a group row is several real rows
   * underneath. `Promise.allSettled`, not `Promise.all` (S8, code review 20 Aug, same
   * doctrine as `updateMoq`): one member's failure must not hide the members that DID
   * save. Every query is invalidated regardless of outcome, so the grid reflects what
   * actually changed; a failure is re-thrown (with the count, on a grouped line) for the
   * caller - which owns the control the buyer is looking at - to toast.
   */
  /**
   * The price call and the supplier the buyer made on a row BEFORE deciding it (AC-R13 /
   * AC-R14). Held here rather than written straight through, because writing one would
   * create a decision - and a row nobody has settled must not start counting as decided
   * just because its supplier was changed. `decide` folds it into the payload; a row that
   * is ALREADY decided is re-recorded on the spot, so the persisted decision keeps up.
   */
  const [rowChoices, setRowChoices] = useState<Record<string, PlanRowChoice>>({});
  // Read through a ref inside `decide` so the callback's identity stays stable - the grid
  // memoises whole columns on it (see `renderSuggestedQtyCell`).
  const rowChoicesRef = useRef(rowChoices);
  rowChoicesRef.current = rowChoices;

  const decide = useCallback(
    async (line: PlanLine, next: PlanDecision) => {
      const recIds = isGroupedLine(line)
        ? line.__group.members.map((m) => m.rec.id)
        : [line.rec.id];
      const choice = rowChoicesRef.current[line.id];
      const payload = toRecordPlanRowDecisionPayload({
        ...next,
        priceMode: next.priceMode ?? choice?.priceMode,
        supplierCode: next.supplierCode ?? choice?.supplierCode,
      });
      const results = await Promise.allSettled(
        recIds.map((id) => recordPlanRowDecision(id, payload)),
      );
      // S3 perf, AC-3.5: fold the rows the server actually wrote straight into the
      // cache rather than invalidating and refetching the run's WHOLE decisions list -
      // one row's decision is a handful of writes, not a reason to re-page a run that
      // can hold thousands.
      const written = results
        .filter((r): r is PromiseFulfilledResult<Awaited<ReturnType<typeof recordPlanRowDecision>>> =>
          r.status === 'fulfilled')
        .map((r) => r.value);
      qc.setQueryData<PlanRowDecisionListResponse>(planRowDecisionsKey(runId), (old) =>
        applyDecisionWrites(old, written, productOf),
      );
      const failures = results.filter(
        (r): r is PromiseRejectedResult => r.status === 'rejected',
      );
      if (failures.length === 0) return;
      const reason = failures[0].reason;
      const detail = reason instanceof Error ? reason.message : 'Failed to record the decision.';
      throw new Error(
        recIds.length > 1
          ? `${detail} (${failures.length} of ${recIds.length} locations did not save)`
          : detail,
      );
    },
    [qc, runId, productOf],
  );

  /**
   * Change the price call or the supplier on a row. A row that already carries a decision
   * is re-recorded immediately (so the persisted decision, and the draft PO it will raise,
   * carry the change); an undecided row just remembers it until it IS decided.
   */
  const chooseRow = useCallback(
    async (line: PlanLine, patch: PlanRowChoice) => {
      const merged = { ...rowChoicesRef.current[line.id], ...patch };
      rowChoicesRef.current = { ...rowChoicesRef.current, [line.id]: merged };
      setRowChoices((prev) => ({ ...prev, [line.id]: merged }));
      const existing = decisionsRef.current[line.id];
      if (existing) await decide(line, { ...existing, ...merged });
    },
    [decide],
  );

  /**
   * What the row's price + supplier controls should READ: the buyer's own pending choice
   * first, then whatever their persisted decision carries, then the engine's proposal.
   */
  const choiceFor = useCallback(
    (line: PlanLine): ResolvedRowChoice => {
      const pending = rowChoices[line.id];
      const decided = decisions[line.id];
      return {
        priceMode: pending?.priceMode ?? decided?.priceMode ?? DEFAULT_PRICE_MODE,
        supplierCode:
          pending?.supplierCode ?? decided?.supplierCode ?? line.supplier?.code ?? null,
      };
    },
    [rowChoices, decisions],
  );

  /** Withdraw a row decision back to undecided - the same per-member fan-out as `decide`. */
  const clear = useCallback(
    async (line: PlanLine) => {
      const recIds = isGroupedLine(line)
        ? line.__group.members.map((m) => m.rec.id)
        : [line.rec.id];
      const results = await Promise.allSettled(recIds.map((id) => clearPlanRowDecision(id)));
      // S3 perf, AC-3.5: same targeted update as `decide` - only recs the server
      // actually cleared leave the cache, never a refetch of the whole list. A
      // rejected clear (already-undecided is idempotent, so a real failure is rare)
      // simply leaves that rec's cached row as-is.
      const cleared = recIds.filter((id, i) => results[i].status === 'fulfilled');
      qc.setQueryData<PlanRowDecisionListResponse>(planRowDecisionsKey(runId), (old) =>
        applyDecisionClears(old, cleared, productOf),
      );
      const failures = results.filter(
        (r): r is PromiseRejectedResult => r.status === 'rejected',
      );
      if (failures.length === 0) return;
      const reason = failures[0].reason;
      const detail = reason instanceof Error ? reason.message : 'Failed to clear the decision.';
      throw new Error(
        recIds.length > 1
          ? `${detail} (${failures.length} of ${recIds.length} locations did not save)`
          : detail,
      );
    },
    [qc, runId, productOf],
  );

  const totals = useMemo(
    () => planTotals(lines, decisions),
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

  /**
   * The level suggestion for a line's product+location. Undefined = no opinion.
   *
   * A Product-grain row's `warehouse_id` is null (`planLineGrouping.ts` groups to one row
   * per product; there IS no single warehouse), so its own key (`${pid}:`) is one the
   * backend never writes - `suggestions_for_run` only ever emits real `(product,
   * warehouse)` pairs. Falling back across the group's own MEMBER rows (each a genuine
   * per-location pair) is the fix: it reuses the location suggestion a member already has
   * rather than inventing a product-wide aggregate for a figure (a stocking trigger) that
   * is not naturally summable across locations the way a quantity is.
   */
  const levelFor = useCallback(
    (line: PlanLine): LevelSuggestion | undefined => {
      if (isGroupedLine(line)) {
        for (const member of line.__group.members) {
          const key = levelKey(member.product_id, member.warehouse_id);
          const hit = key ? levels.data?.suggestions[key] : undefined;
          if (hit) return hit;
        }
        return undefined;
      }
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

  /**
   * S15: the open PO lines carrying this product to this warehouse. Empty = none.
   *
   * A Product-grain row's own key (`${pid}:`) does not exist in `po_book` for the same
   * reason `levelFor` above falls back: grouping never invents a warehouse. Unlike a
   * level, receipts genuinely ARE a per-location list that sums cleanly, so the group's
   * figure is every member's own receipts concatenated - the same "what is actually
   * inbound across this product's locations" reading the summed `on_hand`/`net_position`
   * fields already give the row.
   *
   * A PROJECT row serves none (P8, `isProjectOnlyLine`): its purchase order is consumed by
   * the Order Inquiry's own links, so offering it here would have the buyer net the same
   * quantity a second time. Checked per MEMBER on a grouped row, so a product whose project
   * bin and dealer bin are summed together still shows the dealer bin's receipts.
   */
  const poFor = useCallback(
    (line: PlanLine): PoReceipt[] => {
      if (isGroupedLine(line)) {
        const out: PoReceipt[] = [];
        for (const member of line.__group.members) {
          if (isProjectOnlyLine(member)) continue;
          const key = levelKey(member.product_id, member.warehouse_id);
          const hit = key ? poBook.data?.po_book[key] : undefined;
          if (hit) out.push(...hit);
        }
        return out;
      }
      if (isProjectOnlyLine(line)) return [];
      const key = levelKey(line.product_id, line.warehouse_id);
      return (key ? poBook.data?.po_book[key] : undefined) ?? [];
    },
    [poBook.data],
  );

  /** S14: record (or withdraw, with null) the buyer's own figure beside the engine's. */
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

  /**
   * 20 Aug live test: record (or withdraw, with null) the buyer's own MoQ for a line.
   *
   * Grouped rows apply the SAME override to every member (MOQ is a supplier/product fact,
   * not a per-location one - captain's 20 Aug ruling in `planLineGrouping.ts`); an ungrouped
   * row writes its own single recommendation. Either way the write returns the recalculated
   * figures, but this still invalidates the underlying fetches so the numbers a fresh page
   * load would see and the numbers this session shows never drift apart.
   *
   * S8 (code review, 20 Aug 2026): the per-member writes are NOT atomic - `Promise.allSettled`,
   * not `Promise.all`, so one rejection cannot hide the members that DID save. Every query is
   * still invalidated afterwards regardless of outcome, so the grid reflects which members
   * actually changed rather than a stale figure that papers over a group half applied. A
   * failure is re-thrown (with the count, on a grouped line) rather than swallowed here, so
   * the caller - which owns the input the buyer is looking at - is the one that tells them.
   */
  const updateMoq = useCallback(
    async (line: PlanLine, moq: number | null) => {
      const recIds = isGroupedLine(line)
        ? line.__group.members.map((m) => m.rec.id)
        : [line.rec.id];
      const results = await Promise.allSettled(recIds.map((id) => setMoqOverride(id, moq)));
      await Promise.all([
        qc.invalidateQueries({ queryKey: ['plan-lines', runId, 'buy'] }),
        qc.invalidateQueries({ queryKey: ['plan-lines', runId, 'covered'] }),
        qc.invalidateQueries({ queryKey: ['plan-lines', runId, 'disposition'] }),
      ]);
      const failures = results.filter(
        (r): r is PromiseRejectedResult => r.status === 'rejected',
      );
      if (failures.length === 0) return;
      const reason = failures[0].reason;
      const detail = reason instanceof Error ? reason.message : 'Failed to save the MOQ.';
      throw new Error(
        recIds.length > 1
          ? `${detail} (${failures.length} of ${recIds.length} locations did not save)`
          : detail,
      );
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

  /**
   * The order trend for one PRODUCT'S channel (5.3 grouped view - "what is the trend in
   * project, what is the trend in retail"). Additive to `trendFor` above, which stays keyed
   * by warehouse segment for the ungrouped grid; this reads `channel_trends`, keyed by
   * `sales_orders.demand_class`. Undefined = no opinion, render nothing.
   */
  const channelTrendFor = useCallback(
    (productId: string | null, channel: PlanChannel): ChannelTrendEntry | undefined =>
      productId ? trend.data?.channel_trends?.[productId]?.[channel] : undefined,
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
    decisions,
    decide,
    chooseRow,
    choiceFor,
    clear,
    // The "N of Total made" header's own server-counted figures (S16) - the caller no
    // longer derives them from `decisions`/`totals`, which count whatever is on screen
    // right now rather than what the backend actually holds.
    decidedCount,
    totalDecidableCount,
    totals,
    coverFor,
    priceFor,
    cheaperFor,
    trendFor,
    channelTrendFor,
    levelFor,
    poFor,
    purchaseTrendFor,
    // How far back the ORDER trend's series reaches, off the payload rather than repeated
    // as a literal on the screen that renders it.
    trendSeriesMonths: trend.data?.series_months ?? 24,
    purchaseTrendWindowMonths: purchaseTrend.data?.window_months ?? 3,
    // Whether the lazy fetch has ANSWERED. A product with no purchases and a fetch that
    // has not run both read as `undefined` from `purchaseTrendFor`, and the ledger's
    // History block must not print "never purchased" for the second one.
    purchaseTrendReady: purchaseTrend.isSuccess,
    requestPurchaseTrend,
    hasPhotoFor,
    photoStatus,
    requestProductImages,
    economicsFor,
    decideLifecycle,
    healthThresholds: economics.data?.thresholds ?? {
      margin_floor_pct: 15,
      dead_turnover_months: 6,
    },
    /** The movement windows the health class was judged on (AC-R12). */
    healthWindows: {
      sold_window_months: economics.data?.sold_window_months,
      bought_window_months: economics.data?.bought_window_months,
    },
    amendLevel,
    updateMoq,
    levelSuggestions: levels.data?.suggestions ?? {},
    staleAfterDays: prices.data?.stale_after_days ?? 180,
    coverSources: cover.data?.sources ?? {},
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
