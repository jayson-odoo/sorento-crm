'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  ClipboardList,
  FileSpreadsheet,
  Loader2,
  RotateCcw,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import type { ToolbarAction } from '@/components/ui/data-grid-list-toolbar';
import { ConfirmActionDialog } from '../../components/ConfirmActionDialog';
import { fmtDate, fmtInt } from '../../lib/format';
import { legacyLockReason, shouldGroupByChannel } from '../lib/planGrain';
import { runStartedLabel } from '../lib/runListing';
import { decisionsKey } from '../hooks/useDecisions';
import { planRowDecisionsKey } from '../hooks/usePlanLines';
import {
  runHistoryKey,
  todayRunKey,
  useReorderRunDetail,
  useUnlocatedDemand,
} from '../hooks/useReorderRun';
import { resetRunDecisions } from '../services/reorderRunService';
import type { PlanTotals } from '../lib/planDecisions';
import { PlanExceptionsView } from './PlanExceptionsView';
import { PlanHeaderTab } from './PlanHeaderTab';
import { PlanLinesSection } from './PlanLinesSection';
import { PoWorklistView } from './PoWorklistView';
import { ReorderStatTiles, type ReorderPlanView as PlanViewKey } from './ReorderStatTiles';
import { SummaryOrderReportView } from './SummaryOrderReportView';

/**
 * ONE plan, at its own address (`/scm/reorder/{id}`, R1).
 *
 * The screen this replaces tried to be three things at once: the latest plan, a list of past
 * runs, and the launcher for a new one. A plan is a record, so it gets a record's page - a
 * header naming which plan it is, the tiles over it, and one grid where the deciding happens.
 *
 * The header carries the date-time and the cut-off, and nothing else (R11). Save and Confirm
 * are on the GRID's toolbar, because they act on what the grid holds; a header button acting
 * on a table below it is the arrangement the captain asked to end.
 */
export function ReorderPlanView({ runId }: { runId: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [view, setView] = useState<PlanViewKey>('buy');
  const [decidedFilter, setDecidedFilter] = useState<'all' | 'undecided' | 'decided'>('all');
  const [progressTotals, setProgressTotals] = useState<PlanTotals | null>(null);
  const [decisionProgress, setDecisionProgress] = useState<{ decided: number; total: number } | null>(
    null,
  );
  const [unsavedCount, setUnsavedCount] = useState(0);
  const [leaveOpen, setLeaveOpen] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const [resetting, setResetting] = useState(false);
  // S5: Header (Plan until, warehouse/product scope, cut-off, status, counts) + Lines
  // (the existing grid) - view and edit share the SAME layout (ADR-PRODUCT-STANDARDS).
  // Defaults to Lines: the deciding happens there, and that is what this page has always
  // opened to.
  const [tab, setTab] = useState<'header' | 'lines'>('lines');

  const run = useReorderRunDetail(runId, true);
  // A property of the demand book, not of this run, so it is read once and shown whichever
  // plan the page is looking at.
  const unlocated = useUnlocatedDemand();

  const item = run.data ?? null;
  const rowDecisionLockReason = legacyLockReason(item);
  const groupByChannel = shouldGroupByChannel(item);

  /**
   * R4 + R10: the three run reports and the demo reset live in the grid's own Actions menu.
   * They are views OF this run, so they belong on this page; none of them needs a permanent
   * button, and Reset planning least of all.
   */
  const actions = useMemo<ToolbarAction[]>(
    () => [
      {
        key: 'order_summary',
        label: 'Order summary',
        icon: FileSpreadsheet,
        onClick: () => setView('order_summary'),
      },
      {
        key: 'plan_exceptions',
        label: 'Plan exceptions',
        icon: AlertTriangle,
        onClick: () => setView('plan_exceptions'),
      },
      {
        key: 'po_worklist',
        label: 'PO worklist',
        icon: ClipboardList,
        onClick: () => setView('po_worklist'),
      },
      {
        key: 'reset_planning',
        label: 'Reset planning',
        icon: RotateCcw,
        destructive: true,
        onClick: () => setResetOpen(true),
      },
    ],
    [],
  );

  const doReset = async () => {
    setResetting(true);
    try {
      const res = await resetRunDecisions(runId);
      setResetOpen(false);
      void queryClient.invalidateQueries({ queryKey: decisionsKey(runId) });
      void queryClient.invalidateQueries({ queryKey: planRowDecisionsKey(runId) });
      void queryClient.invalidateQueries({ queryKey: ['scm', 'reorder', 'cash-recs', runId] });
      void queryClient.invalidateQueries({ queryKey: ['scm', 'reorder', 'dispositions', runId] });
      void queryClient.invalidateQueries({ queryKey: todayRunKey });
      void queryClient.invalidateQueries({ queryKey: runHistoryKey });
      toast.success(
        `Plan reset - cleared ${fmtInt(res.decisions_cleared)} decision${res.decisions_cleared === 1 ? '' : 's'}.`,
      );
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to reset the plan');
    } finally {
      setResetting(false);
    }
  };

  const goToPlans = () => {
    // The one exit inside the app. `beforeunload` (in `usePlanEdits`) covers a refresh or a
    // close; Next's app router gives no cancellable navigation event, so the link asks here.
    if (unsavedCount > 0) {
      setLeaveOpen(true);
      return;
    }
    router.push('/scm/reorder');
  };

  if (run.isLoading) {
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

  if (run.isError || !item) {
    return (
      <Card className="flex flex-col items-center gap-3 p-10 text-center">
        <span className="flex size-11 items-center justify-center rounded-full bg-destructive/10 text-destructive">
          <AlertCircle className="size-5" aria-hidden />
        </span>
        <p className="max-w-sm text-sm text-muted-foreground">
          {run.error instanceof Error ? run.error.message : 'This plan could not be loaded.'}
        </p>
        <Button variant="outline" asChild>
          <Link href="/scm/reorder">Back to plans</Link>
        </Button>
      </Card>
    );
  }

  const startedLabel = item.started_at ? runStartedLabel(item.started_at) : null;

  const header = (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <button
          type="button"
          onClick={goToPlans}
          className="mb-1 inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-3.5" aria-hidden />
          Plans
        </button>
        <h2 className="truncate text-lg font-semibold">
          {startedLabel ? `Plan ${startedLabel}` : 'Plan'}
        </h2>
        <p className="text-sm text-muted-foreground">
          {item.plan_horizon_date
            ? `Sales order cut-off ${fmtDate(item.plan_horizon_date)}`
            : 'No cut-off'}
        </p>
      </div>
    </div>
  );

  // The worker is still building this plan - Start Plan navigates here on the 202, so this
  // is the first thing a fresh plan shows. The page polls itself out of this state.
  if (item.status === 'running') {
    return (
      <div className="space-y-5">
        {header}
        <Card className="flex flex-col items-center gap-3 p-12 text-center">
          <span className="flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
            <Loader2 className="size-6 animate-spin" aria-hidden />
          </span>
          <div className="text-base font-semibold">Building the plan</div>
          <p className="max-w-md text-sm text-muted-foreground">
            This page updates on its own when it finishes.
          </p>
        </Card>
      </div>
    );
  }

  if (item.status === 'failed') {
    return (
      <div className="space-y-5">
        {header}
        <Card className="flex flex-col items-center gap-3 p-12 text-center">
          <span className="flex size-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
            <AlertTriangle className="size-6" aria-hidden />
          </span>
          <div className="text-base font-semibold">This plan failed</div>
          <p className="max-w-md text-sm text-muted-foreground">
            {item.error ?? 'The engine stopped before it wrote any recommendations.'}
          </p>
          <Button variant="outline" asChild>
            <Link href="/scm/reorder?run=1">Start another plan</Link>
          </Button>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {header}

      <Tabs value={tab} onValueChange={(v) => setTab(v as 'header' | 'lines')} className="w-full">
        <TabsList variant="line" className="mb-4 w-full justify-start overflow-x-auto">
          <TabsTrigger value="lines">Lines</TabsTrigger>
          <TabsTrigger value="header">Header</TabsTrigger>
        </TabsList>

        <TabsContent value="header" className="mt-0 focus-visible:outline-none">
          <PlanHeaderTab runId={runId} run={item} unsavedCount={unsavedCount} />
        </TabsContent>

        <TabsContent value="lines" className="mt-0 space-y-5 focus-visible:outline-none">
          {/* Demand that arrived with no stated location. It IS planned - it lands on the
              location holding the most of each item - but the planner should know which part
              of the plan rests on demand nobody located, because that is the part most likely
              to be wrong. */}
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
                It is planned against the location holding the most of each item.
              </span>
            </div>
          ) : null}

          {/* R9: the tiles stay above the grid, counting PRODUCTS (R14). */}
          <ReorderStatTiles
            decided={decisionProgress?.decided ?? 0}
            total={decisionProgress?.total ?? 0}
            cashCommitted={progressTotals?.cost ?? 0}
            cashTotal={item.summary?.total_cash_impact ?? 0}
            undecidedFilterActive={decidedFilter === 'undecided'}
            onToggleUndecidedFilter={() =>
              setDecidedFilter((f) => (f === 'undecided' ? 'all' : 'undecided'))
            }
          />

          {view === 'plan_exceptions' ? (
            <PlanExceptionsView runId={runId} onBack={() => setView('buy')} />
          ) : view === 'po_worklist' ? (
            <PoWorklistView runId={runId} onBack={() => setView('buy')} />
          ) : view === 'order_summary' ? (
            <SummaryOrderReportView runId={runId} onBack={() => setView('buy')} />
          ) : (
            <PlanLinesSection
              runId={runId}
              decidedFilter={decidedFilter}
              onDecidedFilterChange={setDecidedFilter}
              onTotalsChange={setProgressTotals}
              onDecisionProgressChange={setDecisionProgress}
              onUnsavedChange={setUnsavedCount}
              secondaryActions={actions}
              decisionsReadOnly={!!rowDecisionLockReason}
              readOnlyReason={rowDecisionLockReason}
              groupByChannel={groupByChannel}
            />
          )}
        </TabsContent>
      </Tabs>

      <ConfirmActionDialog
        open={leaveOpen}
        onOpenChange={setLeaveOpen}
        title="Leave with unsaved changes?"
        description={`${fmtInt(unsavedCount)} product${unsavedCount === 1 ? '' : 's'} carry changes nobody has saved. Leaving this plan drops them.`}
        confirmLabel="Leave anyway"
        isBusy={false}
        onConfirm={() => {
          setLeaveOpen(false);
          router.push('/scm/reorder');
        }}
      />

      <ConfirmActionDialog
        open={resetOpen}
        onOpenChange={setResetOpen}
        title="Reset this plan?"
        description="This clears every decision on the plan and removes the draft purchase orders they staged, returning it to the as-generated state. Confirmed purchase orders are not affected. This cannot be undone."
        confirmLabel="Reset planning"
        onConfirm={() => void doReset()}
        isBusy={resetting}
      />
    </div>
  );
}

