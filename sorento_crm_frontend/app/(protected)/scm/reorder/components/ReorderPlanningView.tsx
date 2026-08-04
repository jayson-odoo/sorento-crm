'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  AlertCircle,
  CalendarClock,
  CalendarDays,
  History,
  PlayCircle,
  RotateCcw,
  Upload,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { recToDispositionRow, splitDispositionRows } from '../lib/planRow';
import { resetRunDecisions } from '../services/reorderRunService';
import { useOrderSummary } from '../hooks/useSummaryOrder';
import { ConfirmActionDialog } from '../../components/ConfirmActionDialog';
import {
  todayRunKey,
  runHistoryKey,
  useAllDispositionRecommendations,
  useReorderRun,
  useTodayRun,
} from '../hooks/useReorderRun';
import { useReorderPlan } from '../hooks/useReorderPlan';
import { decisionsKey } from '../hooks/useDecisions';
import type { ReorderRunHistoryItem } from '../services/reorderRunService';
import type { OutstandingApplyResult } from '../services/outstandingImportService';
import { CashCopilotResults } from './CashCopilotResults';
import { DispositionResultsGrid } from './DispositionResultsGrid';
import { OutstandingUploadDialog } from './OutstandingUploadDialog';
import { PlanAssistant } from './PlanAssistant';
import { PlanMethodologySheet } from './PlanMethodologySheet';
import { ReorderStatTiles, type ReorderPlanView } from './ReorderStatTiles';
import { RunHistoryPanel } from './RunHistoryPanel';
import { RunPlanningModal, type ManualPlanInputs } from './RunPlanningModal';
import { SummaryOrderReportView } from './SummaryOrderReportView';

/** Parse a naive-UTC ISO string as UTC, then format date / time in Malaysia. */
function labelsFor(startedAt: string | null): { date: string; time: string } {
  if (!startedAt) return { date: '', time: '' };
  const hasTz = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(startedAt);
  const d = new Date(hasTz ? startedAt : `${startedAt}Z`);
  if (Number.isNaN(d.getTime())) return { date: startedAt, time: '' };
  const date = new Intl.DateTimeFormat('en-MY', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    timeZone: 'Asia/Kuala_Lumpur',
  }).format(d);
  const time = new Intl.DateTimeFormat('en-MY', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Asia/Kuala_Lumpur',
  }).format(d);
  return { date, time };
}

/**
 * SCM M8 - the reorder planning page reframed as "Today's plan": a daily scheduled
 * snapshot the user reviews and steers, opening directly to the plan (no run click
 * needed). One table with two draggable sections, budget-in-header, inline
 * decisions + drills, one unified assistant, and a run-history list to revisit past
 * runs. PHASE 2 - wired to the live backend (GET /reorder-runs/today + the
 * recommendation / decision / drill / market endpoints).
 */
export function ReorderPlanningView({ autoOpenRun = false }: { autoOpenRun?: boolean }) {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(autoOpenRun);
  const [view, setView] = useState<ReorderPlanView>('buy');
  // The outstanding order book the plan is computed from is uploaded here, because
  // loading it IS a planning action (until AutoCount is integrated).
  const [uploadOpen, setUploadOpen] = useState(false);
  // A history-selected run overrides today's; null = show today's default run.
  const [selectedRun, setSelectedRun] = useState<ReorderRunHistoryItem | null>(null);

  const today = useTodayRun();
  const todayData = today.data ?? null;

  // Manual re-plan runs a live run then swaps the page to today's fresh snapshot.
  const manual = useReorderRun();
  const pendingManual = useRef(false);

  const currentItem = selectedRun ?? todayData;
  const currentRunId = currentItem?.run_id ?? null;
  const isToday =
    !!todayData && currentRunId === todayData.run_id && todayData.is_today;

  // How many planned products still have no decided quantity. SUBSCRIBED to the report
  // query with fetching DISABLED: the report is the whole book, and pulling it on every page
  // load just to fill one tile is a cost nobody asked for, but reading the cache directly
  // with `getQueryData` does not re-render when the panel below fills it, so the tile stayed
  // on "open to count" with the report open on screen. `enabled: false` is the shape that
  // gets both: no request of its own, and a re-render when the value arrives.
  const { data: cachedOrderSummary } = useOrderSummary({ run_id: currentRunId }, false);
  const orderSummaryPending = cachedOrderSummary
    ? cachedOrderSummary.rows.filter((r) => r.chosen_qty === null).length
    : null;
  const isPastRun = !!currentItem && !isToday;

  const plan = useReorderPlan(currentRunId, view === 'buy' && !!currentRunId);

  // Disposition (Stock allocation) rows come from the same run (type=disposition).
  // Fetched WHOLE (M8-F18) - kept enabled in the buy view too so the tile's
  // actionable-only count is always live, and so the grid can split actionable
  // (Discontinue / Promote) from FYI hold accurately (the actionable rows are few
  // and scattered across a run that may carry >1000 hold rows).
  const dispositionQuery = useAllDispositionRecommendations(currentRunId, !!currentRunId);
  const dispositionRows = useMemo(
    () => (dispositionQuery.data ?? []).map(recToDispositionRow),
    [dispositionQuery.data],
  );
  const { actionable: actionableDispositions, hold: holdDispositions } = useMemo(
    () => splitDispositionRows(dispositionRows),
    [dispositionRows],
  );

  const summary = currentItem?.summary ?? null;
  const { date: dateLabel, time: timeLabel } = labelsFor(currentItem?.started_at ?? null);

  // Frozen per-run numbers for the "How this plan was built" sheet (M8-F15 follow-up):
  // the top buys by priority + the funding roll-up, so each step can reveal the ACTUAL
  // figures it describes. All values are the engine's frozen row fields - never an LLM.
  const methodologyFacts = useMemo(() => {
    const within = plan.funding?.within ?? [];
    const over = plan.funding?.over ?? [];
    const rows = [...within, ...over].sort((a, b) => a.rank - b.rank);
    return {
      topBuys: rows.slice(0, 4).map((r) => ({
        sku: r.sku,
        demand: r.forecast_daily_demand,
        net: r.net,
        safetyStock: r.order_qty_inputs?.safety_stock ?? null,
        leadTime: r.supplier?.lead_time_days ?? null,
        reorderPoint: r.order_qty_inputs?.reorder_point ?? null,
        orderUpTo: r.order_qty_inputs?.order_up_to ?? null,
        orderQty: r.order_qty,
        daysCover: r.days_cover,
      })),
      withinCount: within.length,
      overCount: over.length,
      committed: plan.funding?.committed ?? 0,
      free: plan.funding?.free ?? 0,
      budget: plan.budget ?? 0,
    };
  }, [plan.funding, plan.budget]);

  // When a manual run completes, refresh today's snapshot + history and jump to it.
  useEffect(() => {
    if (!pendingManual.current) return;
    if (manual.isComplete && manual.run?.run_id) {
      pendingManual.current = false;
      void queryClient.invalidateQueries({ queryKey: todayRunKey });
      void queryClient.invalidateQueries({ queryKey: runHistoryKey });
      void queryClient.invalidateQueries({ queryKey: decisionsKey(manual.run.run_id) });
      setSelectedRun(null); // fall back to today's default (the fresh run)
      toast.success('Manual plan generated - showing the refreshed snapshot.');
      manual.reset();
    } else if (manual.isFailed) {
      pendingManual.current = false;
      toast.error(manual.error ?? 'Manual plan failed.');
      manual.reset();
    }
  }, [manual.isComplete, manual.isFailed, manual.run?.run_id, manual.error, manual, queryClient]);

  // The upload rewrites the demand the NEXT plan is computed from; today's snapshot is
  // frozen, so refresh what the page reads and say what to do next.
  const bookApplied = (result: OutstandingApplyResult) => {
    void queryClient.invalidateQueries({ queryKey: todayRunKey });
    void queryClient.invalidateQueries({ queryKey: runHistoryKey });
    const changed = result.applied.added + result.applied.updated + result.applied.closed;
    toast.success(
      `Order book updated - ${changed} line${changed === 1 ? '' : 's'} changed. Generate a plan to use it.`,
    );
  };

  const launch = (inputs: ManualPlanInputs) => {
    setModalOpen(false);
    pendingManual.current = true;
    void manual.start({
      warehouse_codes: inputs.warehouse_codes,
      // Empty = every product (AC-B8a), which is what the scheduled daily run does.
      product_codes: inputs.product_codes,
      budget_id: null,
    });
    toast.info('Generating manual plan...');
  };

  // Demo reset (M8 admin): clear this run's decisions + draft POs so the accept /
  // reject / confirm flow can be shown again. Guarded by a confirm dialog; on success
  // every plan-derived query is invalidated so the page snaps back to as-generated.
  const [resetOpen, setResetOpen] = useState(false);
  const [resetting, setResetting] = useState(false);
  const doReset = async () => {
    if (!currentRunId) return;
    setResetting(true);
    try {
      const res = await resetRunDecisions(currentRunId);
      setResetOpen(false);
      plan.resetLocal(); // drop the FE decision overlay so stale pins/rejects clear too
      void queryClient.invalidateQueries({ queryKey: decisionsKey(currentRunId) });
      void queryClient.invalidateQueries({ queryKey: ['scm', 'reorder', 'cash-recs', currentRunId] });
      void queryClient.invalidateQueries({ queryKey: ['scm', 'reorder', 'dispositions', currentRunId] });
      void queryClient.invalidateQueries({ queryKey: todayRunKey });
      void queryClient.invalidateQueries({ queryKey: runHistoryKey });
      toast.success(
        `Plan reset - cleared ${res.decisions_cleared} decision${res.decisions_cleared === 1 ? '' : 's'}. Ready to demo again.`,
      );
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to reset the plan');
    } finally {
      setResetting(false);
    }
  };

  // ---- loading / empty --------------------------------------------------------
  if (today.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full rounded-xl" />
          ))}
        </div>
        <Skeleton className="h-72 w-full rounded-xl" />
      </div>
    );
  }

  if (today.isError) {
    return (
      <Card className="flex flex-col items-center gap-3 p-10 text-center">
        <span className="flex size-11 items-center justify-center rounded-full bg-destructive/10 text-destructive">
          <AlertCircle className="size-5" aria-hidden />
        </span>
        <p className="max-w-sm text-sm text-muted-foreground">
          {today.error instanceof Error ? today.error.message : 'Failed to load the plan.'}
        </p>
        <Button variant="outline" onClick={() => void today.refetch()}>
          Try again
        </Button>
      </Card>
    );
  }

  if (!todayData && !selectedRun) {
    return (
      <>
        <Card className="flex flex-col items-center gap-3 p-12 text-center">
          <span className="flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
            <CalendarDays className="size-6" aria-hidden />
          </span>
          <div className="text-base font-semibold">No plan yet</div>
          <p className="max-w-md text-sm text-muted-foreground">
            The daily reorder plan runs automatically each morning. You can also generate one now for
            a single warehouse.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-2">
            <Button variant="outline" onClick={() => setUploadOpen(true)}>
              <Upload className="size-4" />
              Upload order book
            </Button>
            <Button onClick={() => setModalOpen(true)}>
              <PlayCircle className="size-4" />
              Manual plan
            </Button>
          </div>
        </Card>
        <RunPlanningModal
          open={modalOpen}
          onOpenChange={setModalOpen}
          onSubmit={launch}
          isSubmitting={manual.isRunning || pendingManual.current}
        />
        <OutstandingUploadDialog
          open={uploadOpen}
          onOpenChange={setUploadOpen}
          kind="sales-orders"
          onApplied={bookApplied}
        />
      </>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {isPastRun ? (
            <CalendarClock className="size-5 text-primary" aria-hidden />
          ) : (
            <CalendarDays className="size-5 text-primary" aria-hidden />
          )}
          <h2 className="text-lg font-semibold">
            {isPastRun ? `Plan · ${dateLabel}, ${timeLabel}` : `Today's plan · ${dateLabel}`}
          </h2>
          <PlanMethodologySheet
            runContext={{
              dateLabel,
              timeLabel,
              warehouseCount: currentItem?.warehouse_count,
              warehouseCodes: currentItem?.warehouse_codes,
              isPastRun,
            }}
            facts={methodologyFacts}
          />
        </div>
        <div className="flex flex-wrap items-center gap-1">
          {currentRunId ? (
            <button
              type="button"
              onClick={() => setResetOpen(true)}
              title="Reset this plan for a fresh demo"
              aria-label="Reset demo"
              className="inline-flex size-8 items-center justify-center rounded-md text-muted-foreground/60 transition-colors hover:bg-muted hover:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <RotateCcw className="size-3.5" aria-hidden />
            </button>
          ) : null}
          <Button variant="outline" onClick={() => setUploadOpen(true)}>
            <Upload className="size-4" />
            Upload order book
          </Button>
          <Button onClick={() => setModalOpen(true)}>
            <PlayCircle className="size-4" />
            Manual plan
          </Button>
        </div>
      </div>

      <ConfirmActionDialog
        open={resetOpen}
        onOpenChange={setResetOpen}
        title="Reset this plan for a fresh demo?"
        description="This clears every accept, reject and adjust on today's plan and removes the draft purchase orders they staged, returning it to the as-generated state. Confirmed (active) purchase orders are not affected. This cannot be undone."
        confirmLabel="Reset plan"
        onConfirm={doReset}
        isBusy={resetting}
      />

      {isPastRun ? (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-primary/40 bg-primary/5 px-3 py-2 text-sm">
          <History className="size-4 shrink-0 text-primary" aria-hidden />
          <span className="text-muted-foreground">
            You are viewing a past run from{' '}
            <span className="font-medium text-foreground">
              {dateLabel}, {timeLabel}
            </span>
            . Return to today&apos;s plan to make changes.
          </span>
          <button
            type="button"
            className="ms-auto font-medium text-primary underline-offset-2 hover:underline"
            onClick={() => setSelectedRun(null)}
          >
            Back to today&apos;s plan
          </button>
        </div>
      ) : null}

      {/* TODO(Phase 2, S3b/S4/S5): plan-exception, PO-worklist and order-summary
          counts come from the run summary once those slices exist. Until then they
          are the Phase-1 mock, which dies with `coverageMockStore` and
          `summaryOrderMockStore`. */}
      <ReorderStatTiles
        buyCount={summary?.buy_count ?? 0}
        dispositionCount={actionableDispositions.length}
        cashTotal={summary?.total_cash_impact ?? 0}
        // Null, not a number: the plan-exception and PO-worklist engines are S5 and S4, and
        // until they exist there is nothing to count. These tiles previously rendered mock
        // constants on the live page, so every user read "4 waiting on a decision" off
        // nothing at all.
        planExceptionCount={null}
        poWorklistCount={null}
        // From the report's own cache when it has been read, else null. Never a mock
        // constant: this tile rendered a hard-coded 2 on the live page against a real 317.
        orderSummaryPendingCount={orderSummaryPending}
        activeView={view}
        onSelectView={setView}
      />

      {view === 'order_summary' ? (
        // The weekly sheet Mr Loo decides order quantities on (S3b, AC-C2.1). Reads
        // the SAME run as the plan above, so a past run reports the week it was.
        <SummaryOrderReportView runId={currentRunId} />
      ) : view === 'buy' ? (
        <>
          <PlanAssistant
            runId={currentRunId}
            onApplyProposalLine={plan.applyProposalLine}
            onApplyActions={plan.applyActions}
          />
          {plan.isLoading ? (
            <Skeleton className="h-72 w-full rounded-xl" />
          ) : plan.isError ? (
            <Card className="flex flex-col items-center gap-3 p-10 text-center">
              <span className="flex size-10 items-center justify-center rounded-full bg-destructive/10 text-destructive">
                <AlertCircle className="size-5" aria-hidden />
              </span>
              <p className="max-w-sm text-sm text-muted-foreground">
                {plan.error instanceof Error ? plan.error.message : 'Failed to load buy recommendations.'}
              </p>
              <Button variant="outline" onClick={() => void plan.refetch()}>
                Try again
              </Button>
            </Card>
          ) : (
            <CashCopilotResults plan={plan} />
          )}
        </>
      ) : dispositionQuery.isLoading ? (
        <Skeleton className="h-72 w-full rounded-xl" />
      ) : (
        <DispositionResultsGrid rows={dispositionRows} />
      )}

      <RunHistoryPanel
        selectedRunId={currentRunId}
        onSelect={(run) => setSelectedRun(run)}
      />

      <RunPlanningModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        onSubmit={launch}
        isSubmitting={manual.isRunning || pendingManual.current}
      />

      <OutstandingUploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        kind="sales-orders"
        onApplied={bookApplied}
      />
    </div>
  );
}
