'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  AlertCircle,
  AlertTriangle,
  CalendarClock,
  CalendarDays,
  History,
  Info,
  Loader2,
  PlayCircle,
  RotateCcw,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { recToDispositionRow, splitDispositionRows } from '../lib/planRow';
import { resetRunDecisions } from '../services/reorderRunService';
import { useOrderSummary } from '../hooks/useSummaryOrder';
import { usePlanExceptions } from '../hooks/usePlanExceptions';
import { usePoWorklist } from '../hooks/usePoWorklist';
import { PlanExceptionsView } from './PlanExceptionsView';
import { PoWorklistView } from './PoWorklistView';
import { ConfirmActionDialog } from '../../components/ConfirmActionDialog';
import {
  todayRunKey,
  runHistoryKey,
  useAllDispositionRecommendations,
  useReorderRun,
  useCoveredRecommendations,
  useNeedsLevelRecommendations,
  useTodayRun,
  useSetAsideDemand,
  useUnlocatedDemand,
} from '../hooks/useReorderRun';
import { usePlanLines } from '../hooks/usePlanLines';
import { useReorderPlan } from '../hooks/useReorderPlan';
import { decisionsKey } from '../hooks/useDecisions';
import type { ReorderRunHistoryItem } from '../services/reorderRunService';
import type { OutstandingApplyResult } from '../services/outstandingImportService';
import { PlanLinesGrid } from './PlanLinesGrid';
import type { PlanLineStatus } from '../lib/planLine';
import { PlanBudgetReview } from './PlanBudgetReview';
import { LevelChangesPanel } from './LevelChangesPanel';
import { CoveredByStockView } from './CoveredByStockView';
import { NeedsLevelView } from './NeedsLevelView';
import { PlanSection } from './PlanSection';
import { DispositionResultsGrid } from './DispositionResultsGrid';
import { UploadDataMenu } from './UploadDataMenu';
import type {
  OrderInquiryResult,
  PurchaseHistoryResult,
  SalesHistoryResult,
} from '../services/purchaseHistoryService';
import { PlanAssistant } from './PlanAssistant';
import { PlanMethodologySheet } from './PlanMethodologySheet';
import { ReorderStatTiles, type ReorderPlanView } from './ReorderStatTiles';
import { RunHistoryPanel } from './RunHistoryPanel';
import { RunPlanningModal, type ManualPlanInputs } from './RunPlanningModal';
import { SummaryOrderReportView } from './SummaryOrderReportView';
import { DATE_LOCALE, DATE_PARTS, fmtInt } from '../../lib/format';

/** Parse a naive-UTC ISO string as UTC, then format date / time in Malaysia.
 *
 *  Date parts come from `lib/format` rather than being restated, so the plan header cannot
 *  drift from the dd/mm/yyyy every other screen uses. */
function labelsFor(startedAt: string | null): { date: string; time: string } {
  if (!startedAt) return { date: '', time: '' };
  const hasTz = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(startedAt);
  const d = new Date(hasTz ? startedAt : `${startedAt}Z`);
  if (Number.isNaN(d.getTime())) return { date: startedAt, time: '' };
  const date = new Intl.DateTimeFormat(DATE_LOCALE, {
    ...DATE_PARTS,
    timeZone: 'Asia/Kuala_Lumpur',
  }).format(d);
  const time = new Intl.DateTimeFormat('en-GB', {
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
  /**
   * Which status the one list is filtered to, or null for all of it.
   *
   * The tiles used to reveal and scroll to a band. There are no bands now, so a tile filters
   * the grid instead: same intent - "show me just those" - against a list that never moved.
   */
  const [statusFilter, setStatusFilter] = useState<PlanLineStatus | null>(null);

  const selectView = (next: ReorderPlanView) => {
    if (next === 'covered' || next === 'disposition' || next === 'needs_level') {
      setStatusFilter(
        next === 'covered'
          ? 'covered_by_stock'
          : next === 'disposition'
            ? 'allocation'
            : 'needs_level',
      );
      setView('buy');
      return;
    }
    if (next === 'buy') setStatusFilter(null);
    setView(next);
  };
  // A history-selected run overrides today's; null = show today's default run.
  const [selectedRun, setSelectedRun] = useState<ReorderRunHistoryItem | null>(null);

  const today = useTodayRun();
  const todayData = today.data ?? null;
  // A property of the demand book, not of the run on screen, so it is read once here and
  // shown whichever run the page is looking at.
  const unlocated = useUnlocatedDemand();
  const setAside = useSetAsideDemand();

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

  // Same shape for the worklist tile: subscribed, not fetched. A use-pool decision has
  // no purchase order, so it is not something left to key and is excluded from the count
  // even though it IS a row on the worklist.
  const { data: cachedWorklist } = usePoWorklist({ run_id: currentRunId }, false);
  const poWorklistPending = cachedWorklist
    ? cachedWorklist.rows.filter((r) => r.chosen_qty > 0 && r.keyed_status !== 'keyed').length
    : null;

  // And the same for the exception tile. The count is the OPEN ones, not every exception
  // in the batch: an approved exception is a decision already taken, and counting it would
  // leave the tile reading 6 with nothing left to do.
  const { data: cachedExceptions } = usePlanExceptions({ run_id: currentRunId }, false);
  const planExceptionsOpen = cachedExceptions ? cachedExceptions.counts.open_count : null;
  const isPastRun = !!currentItem && !isToday;
  // Whether a run has actually happened today, which is what decides if there is anywhere
  // for "Back to today's plan" to go. Distinct from `isToday`, which asks whether the run
  // ON SCREEN is today's.
  const hasTodayRun = !!todayData?.is_today && todayData.status === 'completed';
  // A plan is being built in the background. Independent of what is on screen: the run
  // shown is a completed one whenever one exists, so this is only ever an addition to the
  // page, never a reason to empty it.
  const planInProgress = !!todayData?.in_progress;
  // The one case where there is nothing to show: the first plan ever is still running.
  const buildingFirstPlan = planInProgress && !!todayData && todayData.status !== 'completed';

  const plan = useReorderPlan(currentRunId, view === 'buy' && !!currentRunId);
  // S11: one list for every planning line, decisions over it, no budget.
  const planLines = usePlanLines(currentRunId, view === 'buy' && !!currentRunId);
  // Fetched whenever a run is on screen, not only when its view is open, so the tile can
  // carry a real count rather than a dash the user has to click to resolve.
  const covered = useCoveredRecommendations(currentRunId, !!currentRunId);
  const needsLevel = useNeedsLevelRecommendations(currentRunId, !!currentRunId);

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
  // Only the actionable half is read here - the grid does its own splitting for display.
  const { actionable: actionableDispositions } = useMemo(
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

  /**
   * Purchase history and the order inquiry sheet.
   *
   * Neither changes what is on order - history lands closed and fully received - but both
   * change what the NEXT plan reads: last cost and the ageing signal from the history, stock
   * locations and the purchase-order pairing from the inquiry sheet. (Not supplier lead time:
   * that is measured to the goods receipt, and the history file carries none.)
   *
   * The pairing is reported because it is the half nothing else would say: an upload can
   * complete a claim made by a file somebody else uploaded weeks ago.
   */
  const curationApplied = (
    result: PurchaseHistoryResult | OrderInquiryResult | SalesHistoryResult,
  ) => {
    void queryClient.invalidateQueries({ queryKey: todayRunKey });
    void queryClient.invalidateQueries({ queryKey: runHistoryKey });
    const written =
      'orders_created' in result
        ? `${result.orders_created} order${result.orders_created === 1 ? '' : 's'} imported`
        : `${result.locations_written} location${result.locations_written === 1 ? '' : 's'} written`;
    // The sales book claims no order links - it is the demand record, not the pairing - so
    // its result carries no `links` and the toast says only what was written.
    const linked = 'links' in result ? result.links.resolved : 0;
    toast.success(
      linked
        ? `${written}, ${linked} order link${linked === 1 ? '' : 's'} resolved.`
        : `${written}.`,
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
            <UploadDataMenu
              onOutstandingApplied={bookApplied}
              onHistoryApplied={curationApplied}
            />
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
      </>
    );
  }

  // The first plan ever is still being built. There is no snapshot to fall back on, so the
  // page says what is happening rather than "No plan yet", which reads as nothing running
  // and invites the user to start a second one.
  if (buildingFirstPlan) {
    return (
      <Card className="flex flex-col items-center gap-3 p-12 text-center">
        <span className="flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
          <Loader2 className="size-6 animate-spin" aria-hidden />
        </span>
        <div className="text-base font-semibold">Building the plan</div>
        <p className="max-w-md text-sm text-muted-foreground">
          Started {dateLabel} at {timeLabel}. This page updates on its own when it finishes.
        </p>
      </Card>
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
          <UploadDataMenu
            onOutstandingApplied={bookApplied}
            onHistoryApplied={curationApplied}
          />
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

      {/* Demand that arrived with no stated location. It IS planned now - it lands on the
          location holding the most of each item - but the planner should know which part of
          the plan rests on demand nobody located, because that is the part most likely to be
          wrong. Saying "not in this plan" here would now be false. */}
      {unlocated.data && unlocated.data.products > 0 ? (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-sm">
          <AlertTriangle className="size-4 shrink-0 text-amber-600" aria-hidden />
          <span className="text-muted-foreground">
            <span className="font-medium text-foreground tabular-nums">
              {fmtInt(unlocated.data.quantity)}
            </span>{' '}
            units of committed demand across{' '}
            <span className="font-medium text-foreground tabular-nums">
              {fmtInt(unlocated.data.products)}
            </span>{' '}
            product{unlocated.data.products === 1 ? '' : 's'} arrived with no stock location.
            It is planned against the location holding the most of each item, and rows built
            on it are marked.
            {unlocated.data.sample.length ? (
              <>
                {' '}
                Largest:{' '}
                <span className="font-medium text-foreground">
                  {unlocated.data.sample.map((s) => s.product_code).join(', ')}
                </span>
                .
              </>
            ) : null}
          </span>
        </div>
      ) : null}

      {/* Project demand CS has not put on an Order Inquiry. NOT in the plan, by the user's
          own rule - the inquiry is the demand for the project side - and counted here so a
          smaller-than-expected plan explains itself instead of looking like lost data. */}
      {setAside.data && setAside.data.orders > 0 ? (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-sky-500/40 bg-sky-500/5 px-3 py-2 text-sm">
          <Info className="size-4 shrink-0 text-sky-600" aria-hidden />
          <span className="text-muted-foreground">
            <span className="font-medium text-foreground tabular-nums">
              {fmtInt(setAside.data.quantity)}
            </span>{' '}
            units across{' '}
            <span className="font-medium text-foreground tabular-nums">
              {fmtInt(setAside.data.orders)}
            </span>{' '}
            project order{setAside.data.orders === 1 ? '' : 's'} are waiting on an Order
            Inquiry, so this plan leaves them out.
            {setAside.data.sample.length ? (
              <>
                {' '}
                Largest:{' '}
                <span className="font-medium text-foreground">
                  {setAside.data.sample.map((x) => x.so_number).join(', ')}
                </span>
                .
              </>
            ) : null}
          </span>
        </div>
      ) : null}

      {/* A newer plan is being built. Said alongside the plan on screen, not instead of it:
          the numbers below are still the last usable ones, and hiding them would leave the
          planner with nothing to work from while they wait. */}
      {planInProgress ? (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-muted/40 px-3 py-2 text-sm">
          <Loader2 className="size-4 shrink-0 animate-spin text-muted-foreground" aria-hidden />
          <span className="text-muted-foreground">
            A new plan is being built. The figures below are from the last completed one until
            it finishes.
          </span>
        </div>
      ) : null}

      {/* Two different situations, and offering the same control for both made one of them a
          dead end: "Back to today's plan" cleared the selection, landed on the same run, and
          nothing moved. It is offered only when there IS a today plan to return to. */}
      {isPastRun ? (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-primary/40 bg-primary/5 px-3 py-2 text-sm">
          <History className="size-4 shrink-0 text-primary" aria-hidden />
          {hasTodayRun ? (
            <>
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
            </>
          ) : (
            <>
              <span className="text-muted-foreground">
                No plan has run today. This is the most recent one, from{' '}
                <span className="font-medium text-foreground">
                  {dateLabel}, {timeLabel}
                </span>
                . Stock and demand have moved since, so run one before deciding quantities.
              </span>
              <Button
                size="sm"
                variant="outline"
                className="ms-auto"
                onClick={() => setModalOpen(true)}
              >
                <PlayCircle className="size-4" />
                Plan now
              </Button>
            </>
          )}
        </div>
      ) : null}

      {/* TODO(Phase 2, S3b/S4/S5): plan-exception, PO-worklist and order-summary
          counts come from the run summary once those slices exist. Until then they
          are the Phase-1 mock, which dies with `coverageMockStore` and
          `summaryOrderMockStore`. */}
      <ReorderStatTiles
        buyCount={summary?.buy_count ?? 0}
        coveredCount={covered.data ? covered.data.length : null}
        needsLevelCount={needsLevel.data ? needsLevel.data.length : null}
        dispositionCount={actionableDispositions.length}
        cashTotal={summary?.total_cash_impact ?? 0}
        // Null, not a number: the plan-exception and PO-worklist engines are S5 and S4, and
        // until they exist there is nothing to count. These tiles previously rendered mock
        // constants on the live page, so every user read "4 waiting on a decision" off
        // nothing at all.
        planExceptionCount={planExceptionsOpen}
        poWorklistCount={poWorklistPending}
        // From the report's own cache when it has been read, else null. Never a mock
        // constant: this tile rendered a hard-coded 2 on the live page against a real 317.
        orderSummaryPendingCount={orderSummaryPending}
        activeView={view}
        onSelectView={selectView}
      />

      {view === 'covered' ? (
        // Demand the location's own stock covers. A separate view, never merged into the
        // buy grid, so the Buy count and the cash total keep meaning purchases.
        <CoveredByStockView
          runId={currentRunId}
          rows={covered.data ?? []}
          isLoading={covered.isLoading}
          isError={covered.isError}
          error={covered.error}
        />
      ) : view === 'plan_exceptions' ? (
        // Where the plan disagrees with supply already placed (S5, AC-D2). Reads the SAME
        // run as the plan above, so a past run shows the batch that week produced.
        <PlanExceptionsView runId={currentRunId} />
      ) : view === 'po_worklist' ? (
        // What Mr Loo decided, ready to be keyed (S4, AC-E2.1). Reads the SAME run as
        // the plan above, so a past run's worklist is that week's decisions.
        <PoWorklistView runId={currentRunId} />
      ) : view === 'order_summary' ? (
        // The weekly sheet Mr Loo decides order quantities on (S3b, AC-C2.1). Reads
        // the SAME run as the plan above, so a past run reports the week it was.
        <SummaryOrderReportView runId={currentRunId} />
      ) : (
        // ONE LIST (S11). Every planning line lives in a single DataGrid where what the plan
        // found is a STATUS COLUMN, not a place the row lives. The six bands this replaces
        // sorted the work for the buyer, and two of them - Within budget, Over budget -
        // delivered a verdict before the buyer had decided anything, using a budget they had
        // not entered. The money question now comes last, in PlanBudgetReview, asked of the
        // decisions that were actually made.
        <>
          <PlanAssistant
            runId={currentRunId}
            onApplyProposalLine={plan.applyProposalLine}
            onApplyActions={plan.applyActions}
          />
          {planLines.isLoading ? (
            <Skeleton className="h-72 w-full rounded-xl" />
          ) : planLines.isError ? (
            <Card className="flex flex-col items-center gap-3 p-10 text-center">
              <span className="flex size-10 items-center justify-center rounded-full bg-destructive/10 text-destructive">
                <AlertCircle className="size-5" aria-hidden />
              </span>
              <p className="max-w-sm text-sm text-muted-foreground">
                {planLines.error instanceof Error
                  ? planLines.error.message
                  : 'Failed to load the plan.'}
              </p>
              <Button variant="outline" onClick={() => planLines.refetch()}>
                Try again
              </Button>
            </Card>
          ) : (
            <>
              <PlanLinesGrid
                runId={currentRunId}
                statusFilter={statusFilter}
                onStatusFilterChange={setStatusFilter}
                lines={planLines.lines}
                decisions={planLines.decisions}
                onDecide={(line, next) => planLines.decide(line, next)}
                onClear={(line) => planLines.clear(line)}
                coverFor={planLines.coverFor}
                priceFor={planLines.priceFor}
                cheaperFor={planLines.cheaperFor}
                levelFor={planLines.levelFor}
                onAmendLevel={planLines.amendLevel}
                trendFor={planLines.trendFor}
                staleAfterDays={planLines.staleAfterDays}
              />
              {/* Last, and only here: what it costs and whether that works. */}
              <PlanBudgetReview
                lines={planLines.lines}
                decisions={planLines.decisions}
                totals={planLines.totals}
              />
              {/* S13f: the level changes to carry into AutoCount, as one list + CSV. */}
              <div className="flex justify-end">
                <LevelChangesPanel
                  suggestions={planLines.levelSuggestions}
                  onAmend={planLines.amendLevel}
                />
              </div>
            </>
          )}
        </>
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
    </div>
  );
}
