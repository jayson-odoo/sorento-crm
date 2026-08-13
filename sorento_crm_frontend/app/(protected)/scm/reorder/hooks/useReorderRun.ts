'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  createReorderRun,
  getAllDispositionRecommendations,
  getBuyRecommendationsForCash,
  getCoveredRecommendations,
  getNeedsLevelRecommendations,
  getRecommendationDemand,
  getReorderRun,
  getRecommendations,
  getTodayRun,
  getSetAsideDemand,
  getUnlocatedDemand,
  listReorderRuns,
  type RecommendationQuery,
} from '../services/reorderRunService';
import type {
  CreateReorderRunRequest,
  ReorderRun,
  ReorderRunStage,
} from '../types/reorder.types';

/** Ordered stages surfaced in the live progress stepper. */
export const RUN_STAGES: { key: ReorderRunStage; label: string }[] = [
  { key: 'resolving_policies', label: 'Resolving policies' },
  { key: 'computing_reorder_points', label: 'Computing reorder points' },
  { key: 'selecting_suppliers', label: 'Selecting suppliers' },
  { key: 'writing_recommendations', label: 'Writing recommendations' },
];

/** Poll cadence while a run is still `running`. */
const RUN_POLL_MS = 1_500;

/** Hard cap on how long we keep polling a still-`running` run. A healthy run finishes
 *  in seconds; if the server-side enqueue silently failed (no worker picked it up) the
 *  run would otherwise poll forever. After this we stop polling and surface a
 *  "taking longer than expected" state so the user can retry. */
const MAX_POLL_MS = 3 * 60 * 1_000;

/** Map a backend stage → its index in RUN_STAGES (drives the stepper). */
function stageIndexOf(stage: ReorderRunStage | undefined): number {
  if (!stage) return 0;
  const i = RUN_STAGES.findIndex((s) => s.key === stage);
  return i < 0 ? 0 : i;
}

export interface ReorderRunController {
  /** null before the first run. */
  run: ReorderRun | null;
  /** Index into RUN_STAGES for the current/last stage (drives the stepper). */
  stageIndex: number;
  isRunning: boolean;
  isComplete: boolean;
  isFailed: boolean;
  /** Still `running` past MAX_POLL_MS - polling stopped, run may have stalled/failed. */
  isStalled: boolean;
  error: string | null;
  start: (req: CreateReorderRunRequest) => Promise<void>;
  reset: () => void;
}

/**
 * Launches a run (POST) then polls `GET /reorder-runs/{id}` on an interval until
 * the backgrounded RQ job reaches completed | failed. The view reads a stable
 * controller shape; the polling is react-query-driven under the hood.
 */
export function useReorderRun(): ReorderRunController {
  const [runId, setRunId] = useState<string | null>(null);
  // The POST response, shown until the first poll lands (avoids a blank flash).
  const [initialRun, setInitialRun] = useState<ReorderRun | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  // Flips true once a still-running run exceeds MAX_POLL_MS (stops the poll).
  const [stalled, setStalled] = useState(false);
  const polledToastRef = useRef(false);

  // Stop polling a run that never terminates: MAX_POLL_MS after a new run starts, mark
  // it stalled. Cleared/rescheduled on each new run and on reset.
  useEffect(() => {
    if (!runId) return;
    setStalled(false);
    const timer = setTimeout(() => setStalled(true), MAX_POLL_MS);
    return () => clearTimeout(timer);
  }, [runId]);

  const runQuery = useQuery({
    queryKey: ['scm', 'reorder', 'run', runId],
    queryFn: () => getReorderRun(runId as string),
    enabled: !!runId,
    refetchInterval: (query) =>
      !stalled && query.state.data?.status === 'running' ? RUN_POLL_MS : false,
    refetchOnWindowFocus: false,
    retry: 2,
  });

  // A failed POST has no run to poll - synthesize a failed record so the view can
  // render the retry card (not just a toast).
  const syntheticFailed: ReorderRun | null = startError
    ? {
        run_id: '',
        status: 'failed',
        stage: 'resolving_policies',
        buy_scope: 'network',
        summary: null,
        error: startError,
      }
    : null;
  const run = runQuery.data ?? initialRun ?? syntheticFailed;

  // Surface a poll failure once (the background run itself keeps going server-side).
  useEffect(() => {
    if (runQuery.isError && !polledToastRef.current) {
      polledToastRef.current = true;
      const msg =
        runQuery.error instanceof Error
          ? runQuery.error.message
          : 'Failed to load run status';
      toast.error(msg);
    }
    if (!runQuery.isError) polledToastRef.current = false;
  }, [runQuery.isError, runQuery.error]);

  const start = useCallback(async (req: CreateReorderRunRequest) => {
    setStartError(null);
    setInitialRun(null);
    setRunId(null);
    polledToastRef.current = false;
    try {
      const created = await createReorderRun(req);
      setInitialRun(created);
      setRunId(created.run_id);
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to start planning run';
      setStartError(msg);
      toast.error(msg);
    }
  }, []);

  const reset = useCallback(() => {
    setRunId(null);
    setInitialRun(null);
    setStartError(null);
    setStalled(false);
    polledToastRef.current = false;
  }, []);

  const pollError =
    runQuery.isError && !runQuery.data
      ? runQuery.error instanceof Error
        ? runQuery.error.message
        : 'Failed to load run status'
      : null;

  const isStalled = stalled && run?.status === 'running';

  return {
    run,
    stageIndex: stageIndexOf(run?.stage),
    // A stalled run is no longer actively "running" from the UI's perspective.
    isRunning: run?.status === 'running' && !isStalled,
    isComplete: run?.status === 'completed',
    isFailed: run?.status === 'failed' || !!startError || !!pollError,
    isStalled,
    error: startError ?? run?.error ?? pollError,
    start,
    reset,
  };
}

/** React-query cache key for a single run's status/summary. Shared by the live
 *  poll and the history-view detail fetch so revisiting the live run hits cache. */
export const runDetailKey = (runId: string | null) => ['scm', 'reorder', 'run', runId];

/** React-query cache key for the run-history list. */
export const runHistoryKey = ['scm', 'reorder', 'history'];

/** React-query cache key for the "today's plan" default run. */
export const todayRunKey = ['scm', 'reorder', 'today'];

/**
 * The run the page opens to (M8-D3/D4): today's scheduled snapshot when present,
 * else the most-recent completed run; `null` when no run exists yet. Invalidate
 * `todayRunKey` after a manual run completes so the newest snapshot surfaces.
 */
export function useTodayRun() {
  return useQuery({
    queryKey: todayRunKey,
    queryFn: () => getTodayRun(),
    refetchOnWindowFocus: false,
    staleTime: 10_000,
    retry: 1,
    // A plan is built by a background worker, so the page that opened while one was
    // running has no other way to learn it finished. Poll only while that is true, and
    // stop the moment nothing is in flight.
    refetchInterval: (query) => (query.state.data?.in_progress ? 5_000 : false),
  });
}

/** React-query cache key for the unlocated-demand signal. */
export const unlocatedDemandKey = ['scm', 'reorder', 'unlocated-demand'];

/** React-query cache key for the set-aside project demand signal. */
export const setAsideDemandKey = ['scm', 'reorder', 'set-aside-demand'];

/**
 * Project demand no Order Inquiry names, so the plan set it aside (S13b). Like unlocated
 * demand, a property of the demand book rather than of any one run.
 */
export function useSetAsideDemand() {
  return useQuery({
    queryKey: setAsideDemandKey,
    queryFn: () => getSetAsideDemand(),
    refetchOnWindowFocus: false,
    staleTime: 60_000,
    retry: 1,
  });
}

/**
 * Demand the plan cannot net because the sales-order line names no warehouse. A property
 * of the demand book, not of any one run, so it is keyed on its own and survives a re-plan.
 */
export function useUnlocatedDemand() {
  return useQuery({
    queryKey: unlocatedDemandKey,
    queryFn: () => getUnlocatedDemand(),
    refetchOnWindowFocus: false,
    staleTime: 60_000,
    retry: 1,
  });
}

/**
 * Newest-first paginated run history for the Run history panel. Invalidate
 * `runHistoryKey` when a fresh run completes so it appears at the top.
 */
export function useReorderRunHistory(page: number, limit: number, enabled = true) {
  return useQuery({
    queryKey: [...runHistoryKey, page, limit],
    queryFn: () => listReorderRuns(page, limit),
    enabled,
    refetchOnWindowFocus: false,
    staleTime: 10_000,
    // Keep the previous page visible while the next page loads (no flash to empty).
    placeholderData: (prev) => prev,
    retry: 1,
  });
}

/**
 * Load a PAST run's summary (status + roll-up counts) so the tiles + grid can
 * render it WITHOUT re-running. Reuses the poll cache key - revisiting the live
 * run is a cache hit. Only enabled for a completed/failed run being viewed.
 */
export function useReorderRunDetail(runId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: runDetailKey(runId),
    queryFn: () => getReorderRun(runId as string),
    enabled: enabled && !!runId,
    refetchOnWindowFocus: false,
    staleTime: 30_000,
    retry: 1,
  });
}

/**
 * The FULL buy recommendation set for the M4 cash co-pilot (not paginated -
 * greedy funding runs across the whole ranked list). Fetched once; the budget
 * slider then recomputes funded/deferred live client-side via `computeFunding`,
 * so this does NOT refetch per slider tick.
 */
/**
 * Every `covered` row for a run: demand the location's own stock already covers.
 *
 * Its own query, never merged into the cash set. A covered row is not a purchase, and
 * letting it into the funding split would spend budget on something nobody agreed to buy.
 */
export function useCoveredRecommendations(runId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ['scm', 'reorder', 'covered-recs', runId],
    queryFn: () => getCoveredRecommendations(runId as string),
    enabled: enabled && !!runId,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

/**
 * Items the plan could not size because nobody has set a reorder level for them.
 *
 * Fetched separately from the buys for the same reason covered rows are: they are not
 * purchases and must not reach the cash split. They still have to be VISIBLE, though - a
 * plan that drops them reports "nothing to do" for stock that was never set up.
 */
export function useNeedsLevelRecommendations(runId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ['scm', 'reorder', 'needs-level-recs', runId],
    queryFn: () => getNeedsLevelRecommendations(runId as string),
    enabled: enabled && !!runId,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

/**
 * The open order lines a planned quantity was built from. Fetched only when the drill is
 * opened: the row carries the total, and pulling every contributing line for every row on
 * load is a cost nobody asked for.
 */
export function useRecommendationDemand(
  runId: string | null,
  recId: string | null,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ['scm', 'reorder', 'rec-demand', runId, recId],
    queryFn: () => getRecommendationDemand(runId as string, recId as string),
    enabled: enabled && !!runId && !!recId,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useBuyRecommendationsForCash(runId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ['scm', 'reorder', 'cash-recs', runId],
    queryFn: () => getBuyRecommendationsForCash(runId as string),
    enabled: enabled && !!runId,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

/**
 * The FULL disposition (Stock allocation) recommendation set for a run. The M8-F18
 * view needs every row to split actionable (Discontinue / Promote) from FYI hold
 * and to count only the actionable subset on the tile - so it is fetched whole
 * (paged internally past the 1000-row cap) and cached per run, not paginated. Kept
 * enabled in the buy view too so the tile's actionable count is always live.
 */
export function useAllDispositionRecommendations(runId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ['scm', 'reorder', 'dispositions', runId],
    queryFn: () => getAllDispositionRecommendations(runId as string),
    enabled: enabled && !!runId,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

/** Paginated recommendations for a completed run (DataGrid source). */
export function useReorderRecommendations(
  runId: string | null,
  query: RecommendationQuery,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ['scm', 'reorder', 'recs', runId, query],
    queryFn: () => getRecommendations(runId as string, query),
    enabled: enabled && !!runId,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}
