'use client';

import { useEffect, useMemo, useState } from 'react';
import { AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import type { ToolbarAction } from '@/components/ui/data-grid-list-toolbar';
import { usePlanLines } from '../hooks/usePlanLines';
import type { PlanLineStatus } from '../lib/planLine';
import { planTotals, type PlanTotals } from '../lib/planDecisions';
import { lineBreachStatus } from '../lib/orderQtyLedger';
import { LevelChangesPanel } from './LevelChangesPanel';
import { PlanBudgetReview } from './PlanBudgetReview';
import { PlanLinesGrid } from './PlanLinesGrid';

/**
 * ONE list (S11) - PlanLinesGrid + PlanBudgetReview + LevelChangesPanel, driven entirely
 * by `usePlanLines(runId)`. Extracted out of `ReorderPlanningView` so a second screen (the
 * SCM simulation page's "Planning view" tab) can render the exact same grid, hooks, cell
 * popovers and decision controls against a different run instead of re-implementing them.
 * One render source - tooltips/popovers/columns can never drift between the two screens.
 *
 * `statusFilter` / `onStatusFilterChange` and `decidedFilter` / `onDecidedFilterChange` are
 * optional so a caller that also drives a filter from elsewhere (the reorder page's summary
 * tiles) can control it; when omitted the section owns its own filter state.
 */
export function PlanLinesSection({
  runId,
  statusFilter: statusFilterProp,
  onStatusFilterChange,
  decidedFilter: decidedFilterProp,
  onDecidedFilterChange,
  onTotalsChange,
  secondaryActions,
}: {
  runId: string | null;
  statusFilter?: PlanLineStatus | null;
  onStatusFilterChange?: (next: PlanLineStatus | null) => void;
  /** Undecided/decided the list is narrowed to. The reorder page's decision-progress tile
   *  drives this the same way its status tiles drive `statusFilter`. */
  decidedFilter?: 'all' | 'undecided' | 'decided';
  onDecidedFilterChange?: (next: 'all' | 'undecided' | 'decided') => void;
  /** Reported every time the decided/undecided split changes, so a caller (the decision-
   *  progress tile) can show it without re-deriving decisions of its own. */
  onTotalsChange?: (totals: PlanTotals) => void;
  /** Forwarded to `PlanLinesGrid`'s own toolbar (quiet links to Order summary / Plan
   *  exceptions / PO worklist, next to Filters / Columns / Export). */
  secondaryActions?: ToolbarAction[];
}) {
  const [ownStatusFilter, setOwnStatusFilter] = useState<PlanLineStatus | null>(null);
  const statusFilter = statusFilterProp !== undefined ? statusFilterProp : ownStatusFilter;
  const setStatusFilter = onStatusFilterChange ?? setOwnStatusFilter;

  const [ownDecidedFilter, setOwnDecidedFilter] = useState<'all' | 'undecided' | 'decided'>('all');
  const decidedFilter = decidedFilterProp ?? ownDecidedFilter;
  const setDecidedFilter = onDecidedFilterChange ?? setOwnDecidedFilter;

  const planLines = usePlanLines(runId, !!runId);

  /**
   * Manual mode hides not-breached covered rows by default (user feedback, 2026-08-12:
   * "if net is not below my reorder level, it is not my business, I don't need to see
   * this in reorder planning").
   *
   * Scoped narrowly: a manual-basis (`reorder_level`) row whose own status is
   * `covered_by_stock` (the informational rec_type - `covered`, per `planLine.ts`) AND
   * whose net sits ABOVE its level. Reuses `lineBreachStatus` (the same breach math the
   * order-qty ledger's own "Line not breached" sentence uses) rather than re-deriving it -
   * a breached row, an auto-mode row, or any other rec_type is untouched. Hidden from the
   * DEFAULT list only: an explicit "Covered by stock" status filter still shows every one
   * of them, so nothing is unreachable, just no longer the default.
   */
  const visibleLines = useMemo(() => {
    if (statusFilter === 'covered_by_stock') return planLines.lines;
    return planLines.lines.filter((l) => {
      if (l.rec.policy_type !== 'reorder_level') return true;
      if (l.status !== 'covered_by_stock') return true;
      return lineBreachStatus(l.rec, l.net).breached;
    });
  }, [planLines.lines, statusFilter]);

  // Reported over `visibleLines`, NOT `planLines.lines`: the grid renders `visibleLines`
  // (manual-mode hides not-breached covered rows by default, above), so a tile counting
  // every line - including ones the buyer cannot see under the current filter - could read
  // "30 of 40, 10 left" with zero of those ten rows anywhere on screen.
  //
  // Keyed on the PRIMITIVE fields, not the totals object itself: a fresh `useMemo` result
  // whenever `visibleLines` or `decisions` change identity, and a hand-rolled test double
  // may not memoize either at all - depending on the object's identity would refire this
  // effect, call `setState` in the caller, and re-render forever.
  const reportedTotals = useMemo(
    () => planTotals(visibleLines, planLines.decisions),
    [visibleLines, planLines.decisions],
  );
  const { decided, undecided, buying, usingStock, usingPo, skipped, units, cost, unpriced } =
    reportedTotals;
  useEffect(() => {
    onTotalsChange?.({ decided, undecided, buying, usingStock, usingPo, skipped, units, cost, unpriced });
  }, [decided, undecided, buying, usingStock, usingPo, skipped, units, cost, unpriced, onTotalsChange]);

  if (planLines.isLoading) {
    return <Skeleton className="h-72 w-full rounded-xl" />;
  }

  if (planLines.isError) {
    return (
      <Card className="flex flex-col items-center gap-3 p-10 text-center">
        <span className="flex size-10 items-center justify-center rounded-full bg-destructive/10 text-destructive">
          <AlertCircle className="size-5" aria-hidden />
        </span>
        <p className="max-w-sm text-sm text-muted-foreground">
          {planLines.error instanceof Error ? planLines.error.message : 'Failed to load the plan.'}
        </p>
        <Button variant="outline" onClick={() => planLines.refetch()}>
          Try again
        </Button>
      </Card>
    );
  }

  return (
    <>
      <PlanLinesGrid
        runId={runId}
        statusFilter={statusFilter}
        onStatusFilterChange={setStatusFilter}
        decidedFilter={decidedFilter}
        onDecidedFilterChange={setDecidedFilter}
        secondaryActions={secondaryActions}
        lines={visibleLines}
        decisions={planLines.decisions}
        onDecide={(line, next) => planLines.decide(line, next)}
        onClear={(line) => planLines.clear(line)}
        coverFor={planLines.coverFor}
        priceFor={planLines.priceFor}
        cheaperFor={planLines.cheaperFor}
        levelFor={planLines.levelFor}
        onAmendLevel={planLines.amendLevel}
        poFor={planLines.poFor}
        trendFor={planLines.trendFor}
        purchaseTrendFor={planLines.purchaseTrendFor}
        purchaseTrendWindowMonths={planLines.purchaseTrendWindowMonths}
        onOpenPurchaseTrend={planLines.requestPurchaseTrend}
        photoFor={planLines.photoFor}
        photoStatus={planLines.photoStatus}
        onOpenPhoto={planLines.requestProductImages}
        economicsFor={planLines.economicsFor}
        healthThresholds={planLines.healthThresholds}
        onDecideLifecycle={planLines.decideLifecycle}
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
  );
}
