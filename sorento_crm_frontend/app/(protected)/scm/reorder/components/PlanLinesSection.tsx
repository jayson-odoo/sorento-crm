'use client';

import { useEffect, useMemo, useState } from 'react';
import { AlertCircle, CheckCircle2, Save } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import type { ToolbarAction } from '@/components/ui/data-grid-list-toolbar';
import { ConfirmActionDialog } from '../../components/ConfirmActionDialog';
import { usePlanLines } from '../hooks/usePlanLines';
import { usePlanEdits } from '../hooks/usePlanEdits';
import type { PlanLine, PlanLineStatus } from '../lib/planLine';
import { planTotals, type PlanTotals } from '../lib/planDecisions';
import { groupPlanLinesByChannel } from '../lib/planLineGrouping';
import { lineBreachStatus } from '../lib/orderQtyLedger';
import { fmtInt, fmtMoney } from '../../lib/format';
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
  onDecisionProgressChange,
  onUnsavedChange,
  secondaryActions,
  decisionsReadOnly = false,
  readOnlyReason = null,
  groupByChannel = false,
}: {
  runId: string | null;
  statusFilter?: PlanLineStatus | null;
  onStatusFilterChange?: (next: PlanLineStatus | null) => void;
  /** Undecided/decided the list is narrowed to. The reorder page's decision-progress tile
   *  drives this the same way its status tiles drive `statusFilter`. */
  decidedFilter?: 'all' | 'undecided' | 'decided';
  onDecidedFilterChange?: (next: 'all' | 'undecided' | 'decided') => void;
  /** Reported every time the decided/undecided split changes, so a caller (the decision-
   *  progress tile) can show it without re-deriving decisions of its own. Cash figures
   *  only, since S16: the decided/undecided COUNT is `onDecisionProgressChange` below. */
  onTotalsChange?: (totals: PlanTotals) => void;
  /** S16: the header's own "N of Total made", counted server-side (`usePlanLines`'
   *  `decidedCount`/`totalDecidableCount`, off `GET .../plan-row-decisions`) rather than
   *  derived from whatever is currently on screen - a filtered/grouped view must not
   *  change what the header reports. */
  onDecisionProgressChange?: (progress: { decided: number; total: number }) => void;
  /** How many PRODUCTS carry an unsaved draft (R14). The page uses it for the leave-page
   *  prompt on its own back link - `beforeunload` cannot see an in-app navigation. */
  onUnsavedChange?: (count: number) => void;
  /** Forwarded to `PlanLinesGrid`'s own toolbar (quiet links to Order summary / Plan
   *  exceptions / PO worklist, next to Filters / Columns / Export). */
  secondaryActions?: ToolbarAction[];
  /** The run predates the front-planning contract: read and drill only (S16 - grain no
   *  longer locks the plan row, only a legacy run does; see `lib/planGrain.ts`'s
   *  `legacyLockReason`). */
  decisionsReadOnly?: boolean;
  readOnlyReason?: string | null;
  /** Forwarded to `PlanLinesGrid` (5.3): group the grid into one row per (product,
   *  channel) instead of one row per (product, warehouse). The caller derives this from
   *  the run's own stamped `decision_grain` (`lib/planGrain.ts`'s `shouldGroupByChannel`),
   *  never decided here. */
  groupByChannel?: boolean;
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
    const hidden = new Set(
      planLines.lines
        .filter(
          (l) =>
            l.rec.policy_type === 'reorder_level' &&
            l.status === 'covered_by_stock' &&
            !lineBreachStatus(l.rec, l.net).breached,
        )
        .map((l) => l.id),
    );
    if (hidden.size === 0) return planLines.lines;
    // ONE exception: the product's OWN row, while the product is still on the plan for
    // another reason.
    //
    // The level basis plans per PRODUCT, so that covered row IS the product's row - it
    // holds every location's stock and demand, and the grouped view builds the product row
    // from it. Dropping it left SRTWT7408's BRW disposition standing in as the plan row:
    // Suggested qty "-", On hand 1,296 of 5,495, and no ledger to open. A per-location
    // covered row is hidden exactly as before, and so is a product row whose product has
    // nothing else on the plan - that item really is not the buyer's business today.
    const keyOf = (l: PlanLine) => l.product_id ?? `sku:${l.sku}`;
    const shown = new Set(
      planLines.lines.filter((l) => !hidden.has(l.id)).map(keyOf),
    );
    return planLines.lines.filter(
      (l) => !hidden.has(l.id) || (l.warehouse_id === null && shown.has(keyOf(l))),
    );
  }, [planLines.lines, statusFilter]);

  // Reported over `visibleLines`, NOT `planLines.lines`: the grid renders `visibleLines`
  // (manual-mode hides not-breached covered rows by default, above), so cash figures
  // counting every line - including ones the buyer cannot see under the current filter -
  // could report cost for rows nowhere on screen. Always the per-warehouse (ungrouped)
  // list, even under `groupByChannel`: S16 records a decision on the underlying member
  // recommendation ids, never a synthetic `group:<product_id>` key, so counting the
  // grouped rows here would look the decisions up under a key the map never carries.
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

  // S16: the header's "N of Total made" is the SERVER's own count (`GET
  // .../plan-row-decisions`), not derived from whatever is filtered/grouped on screen -
  // see `onDecisionProgressChange`'s own doc above.
  const { decidedCount, totalDecidableCount } = planLines;
  useEffect(() => {
    onDecisionProgressChange?.({ decided: decidedCount, total: totalDecidableCount });
  }, [decidedCount, totalDecidableCount, onDecisionProgressChange]);

  /**
   * The rows AS THE GRID RENDERS THEM. The grid groups per-warehouse rows into one row per
   * product on a product-grain run, and the draft map is keyed by those row ids - so the
   * counts here have to be taken over the same set, not over the ungrouped lines that feed
   * it. Same pure function, same input, same ids.
   */
  const gridRows = useMemo(
    () => (groupByChannel ? groupPlanLinesByChannel(visibleLines) : visibleLines),
    [groupByChannel, visibleLines],
  );

  const planEdits = usePlanEdits(
    runId,
    gridRows,
    planLines.decisions,
    planLines.coverFor,
    planLines.poFor,
  );

  useEffect(() => {
    onUnsavedChange?.(planEdits.saveCount);
  }, [planEdits.saveCount, onUnsavedChange]);

  const [confirmOpen, setConfirmOpen] = useState(false);
  const { products: confirmProducts, cash: confirmCash, unpriced: confirmUnpriced } =
    planEdits.confirmable;

  const confirmDescription = `${fmtInt(confirmProducts)} product${
    confirmProducts === 1 ? '' : 's'
  } go into draft purchase orders, ${fmtMoney(confirmCash)} of buying.${
    confirmUnpriced > 0
      ? ` ${fmtInt(confirmUnpriced)} of them carry no price yet and are drafted unpriced.`
      : ''
  } Products nobody touched are confirmed as the plan suggested; skipped ones are left out.`;

  const doSave = async () => {
    try {
      const result = await planEdits.save();
      if (!result) return;
      toast.success(
        `Saved ${fmtInt(result.saved_rows)} change${result.saved_rows === 1 ? '' : 's'}.`,
      );
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not save the changes.');
    }
  };

  const doConfirm = async () => {
    try {
      const result = await planEdits.confirm();
      setConfirmOpen(false);
      if (!result) return;
      toast.success(
        result.confirmed_count > 0
          ? `Confirmed ${fmtInt(result.confirmed_count)} product${result.confirmed_count === 1 ? '' : 's'} into ${fmtInt(result.po_count)} draft purchase order${result.po_count === 1 ? '' : 's'}.`
          : 'Nothing to confirm - no product carries a buy.',
      );
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not confirm the plan.');
    }
  };

  /**
   * Save and Confirm, on the grid's own toolbar, right of Actions and Confirm last (R11).
   * They sit with the grid rather than in the page header because they act on what the grid
   * holds - the draft map - and a header button acting on a table below it was the layout
   * the captain asked to end.
   */
  const toolbarPrimary = decisionsReadOnly ? null : (
    <>
      <Button
        variant="outline"
        onClick={() => void doSave()}
        disabled={planEdits.saveCount === 0 || planEdits.isSaving}
        title="Save every unsaved change on this plan"
      >
        <Save className="size-4" />
        {`Save (${fmtInt(planEdits.saveCount)})`}
      </Button>
      <Button
        onClick={() => setConfirmOpen(true)}
        disabled={confirmProducts === 0 || planEdits.isConfirming}
        title="Save, then turn this plan into draft purchase orders"
      >
        <CheckCircle2 className="size-4" />
        {`Confirm (${fmtInt(confirmProducts)})`}
      </Button>
    </>
  );

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
        decisionsReadOnly={decisionsReadOnly}
        readOnlyReason={readOnlyReason}
        groupByChannel={groupByChannel}
        lines={visibleLines}
        decisions={planLines.decisions}
        edits={planEdits.edits}
        onRowEdit={planEdits.setRowEdit}
        onResetRow={planEdits.resetRow}
        toolbarPrimary={toolbarPrimary}
        coverFor={planLines.coverFor}
        priceFor={planLines.priceFor}
        cheaperFor={planLines.cheaperFor}
        levelFor={planLines.levelFor}
        poFor={planLines.poFor}
        trendFor={planLines.trendFor}
        trendSeriesMonths={planLines.trendSeriesMonths}
        purchaseTrendFor={planLines.purchaseTrendFor}
        purchaseTrendWindowMonths={planLines.purchaseTrendWindowMonths}
        purchaseTrendReady={planLines.purchaseTrendReady}
        onOpenPurchaseTrend={planLines.requestPurchaseTrend}
        hasPhotoFor={planLines.hasPhotoFor}
        photoStatus={planLines.photoStatus}
        onOpenPhoto={planLines.requestProductImages}
        economicsFor={planLines.economicsFor}
        healthThresholds={planLines.healthThresholds}
        healthWindows={planLines.healthWindows}
        staleAfterDays={planLines.staleAfterDays}
      />

      <ConfirmActionDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Confirm this plan?"
        description={confirmDescription}
        confirmLabel="Confirm"
        isBusy={planEdits.isConfirming}
        onConfirm={() => void doConfirm()}
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
