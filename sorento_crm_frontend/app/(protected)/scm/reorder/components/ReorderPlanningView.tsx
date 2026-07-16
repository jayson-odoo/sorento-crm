'use client';

import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, History as HistoryIcon, PlayCircle, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateTimeInMalaysia, timeAgo } from '@/lib/helpers';
import { runHistoryKey, useReorderRun, useReorderRunDetail } from '../hooks/useReorderRun';
import type { ReorderRunHistoryItem } from '../services/reorderRunService';
import type {
  CreateReorderRunRequest,
  ReorderRecType,
  ReorderRunSummary,
} from '../types/reorder.types';
import { ReorderResultsGrid } from './ReorderResultsGrid';
import { ReorderStatTiles } from './ReorderStatTiles';
import { RunHistoryPanel } from './RunHistoryPanel';
import { RunPlanningModal } from './RunPlanningModal';
import { RunProgressCard } from './RunProgressCard';

/** Parse a naive-UTC ISO string as UTC (see the audit-time lesson). */
function toUtcDate(raw: string | null): Date | null {
  if (!raw) return null;
  const hasTz = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(raw);
  const d = new Date(hasTz ? raw : `${raw}Z`);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function ReorderPlanningView({ autoOpenRun = false }: { autoOpenRun?: boolean }) {
  // `autoOpenRun` (dashboard deep-link `?run=1`) opens the modal on first render.
  const [modalOpen, setModalOpen] = useState(autoOpenRun);
  // Grid type filter is lifted here so the clickable stat tiles and the grid's own
  // filter dropdown share one source of truth ('' = all types).
  const [typeFilter, setTypeFilter] = useState('');
  // A past run the user picked from history to VIEW (null = follow the live run).
  // We keep the full list item so the banner has its time/scope without a refetch.
  const [viewedRun, setViewedRun] = useState<ReorderRunHistoryItem | null>(null);
  const { run, stageIndex, isRunning, isComplete, isStalled, start, reset } = useReorderRun();
  const resultsRef = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();

  // When a fresh run completes, refresh the history list so it appears at the top.
  const completedId = isComplete ? run?.run_id : null;
  useEffect(() => {
    if (completedId) void queryClient.invalidateQueries({ queryKey: runHistoryKey });
  }, [completedId, queryClient]);

  // Are we viewing a PAST run (not the live one)? Selecting the live run just follows it.
  const isPastView = !!viewedRun && viewedRun.run_id !== run?.run_id;

  // Load the viewed run's canonical summary via the existing GET /reorder-runs/{id}
  // (the list item's summary seeds the tiles instantly while it loads).
  const detail = useReorderRunDetail(viewedRun?.run_id ?? null, isPastView);

  // The run currently DISPLAYED drives the tiles + results grid.
  const displayedRunId = isPastView ? viewedRun!.run_id : run?.run_id ?? null;
  const displayedStatus = isPastView ? detail.data?.status ?? viewedRun!.status : run?.status;
  const displayedSummary: ReorderRunSummary | null = isPastView
    ? detail.data?.summary ?? viewedRun!.summary
    : run?.summary ?? null;
  const showResults = displayedStatus === 'completed' && !!displayedSummary && !!displayedRunId;

  const launch = (req: CreateReorderRunRequest) => {
    setViewedRun(null); // a new run becomes the newest — stop viewing a past one
    void start(req);
    setModalOpen(false);
  };

  // Toggle a stat-tile filter: clicking the active type again clears it.
  const toggleType = (type: ReorderRecType) =>
    setTypeFilter((current) => (current === type ? '' : type));

  const reviewRecommendations = () => {
    resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const selectRun = (item: ReorderRunHistoryItem) => {
    setTypeFilter('');
    setViewedRun(item.run_id === run?.run_id ? null : item);
    // Scroll to the results after the swap paints.
    window.setTimeout(reviewRecommendations, 0);
  };

  const backToLatest = () => setViewedRun(null);

  const viewedWhen = isPastView ? toUtcDate(viewedRun!.started_at) : null;

  return (
    <div className="space-y-5">
      <div className="flex justify-end">
        <Button onClick={() => setModalOpen(true)} disabled={isRunning} className="shrink-0">
          <PlayCircle className="size-4" />
          Run planning
        </Button>
      </div>

      {/* Idle — no run yet and not viewing history. Explicit empty state + CTA. */}
      {!run && !isPastView ? (
        <Card className="flex flex-col items-center gap-3 p-10 text-center">
          <span className="flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
            <Sparkles className="size-6" aria-hidden />
          </span>
          <div>
            <div className="text-sm font-semibold">No planning run yet</div>
            <p className="mt-1 max-w-md text-sm text-muted-foreground">
              Run planning to evaluate the selected warehouses and generate reorder
              recommendations.
            </p>
          </div>
          <Button variant="outline" onClick={() => setModalOpen(true)}>
            <PlayCircle className="size-4" />
            Run planning
          </Button>
        </Card>
      ) : null}

      {/* Live run progress (only while following the live run, not a past view). */}
      {run && !isPastView ? (
        <RunProgressCard
          run={run}
          stageIndex={stageIndex}
          isStalled={isStalled}
          onReview={reviewRecommendations}
          onRetry={reset}
        />
      ) : null}

      {/* Viewing a past run — banner identifying it (by time + warehouses, no UUID). */}
      {isPastView ? (
        <Card className="flex flex-col gap-3 border-primary/40 bg-primary/5 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <HistoryIcon className="size-4.5" aria-hidden />
            </span>
            <div className="min-w-0">
              <div className="text-sm font-semibold">
                Viewing run from {viewedWhen ? timeAgo(viewedWhen) : ''}
              </div>
              <div className="truncate text-xs text-muted-foreground">
                {viewedRun!.started_at ? formatDateTimeInMalaysia(viewedRun!.started_at) : ''}
                {viewedRun!.warehouse_count
                  ? ` · ${viewedRun!.warehouse_count} warehouse${
                      viewedRun!.warehouse_count === 1 ? '' : 's'
                    }`
                  : ''}
              </div>
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={backToLatest} className="shrink-0">
            <ArrowLeft className="size-4" />
            Back to latest
          </Button>
        </Card>
      ) : null}

      {/* Loading / error while fetching a past run's summary. */}
      {isPastView && detail.isLoading && !displayedSummary ? (
        <Skeleton className="h-28 w-full rounded-xl" />
      ) : null}
      {isPastView && detail.isError && !displayedSummary ? (
        <Card className="p-6 text-center text-sm text-muted-foreground">
          Failed to load this run. Pick another from the history below.
        </Card>
      ) : null}

      {/* Stat tiles + results grid — driven by whichever run is displayed. */}
      {showResults && displayedSummary && displayedRunId ? (
        <div ref={resultsRef} className="scroll-mt-4 space-y-5">
          <ReorderStatTiles
            summary={displayedSummary}
            activeType={typeFilter}
            onToggle={toggleType}
          />
          <ReorderResultsGrid
            runId={displayedRunId}
            enabled={showResults}
            typeFilter={typeFilter}
            onTypeFilterChange={setTypeFilter}
          />
        </div>
      ) : null}

      {/* Run history — always rendered (own loading / empty / error states). */}
      <RunHistoryPanel selectedRunId={displayedRunId} onSelect={selectRun} />

      <RunPlanningModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        onSubmit={launch}
        isSubmitting={false}
      />
    </div>
  );
}
