'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertCircle, CheckCircle2, Save } from 'lucide-react';
import { toast } from '@/lib/toast';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import type { ToolbarAction } from '@/components/ui/data-grid-list-toolbar';
import { ConfirmActionDialog } from '../../components/ConfirmActionDialog';
import { usePlanLines } from '../hooks/usePlanLines';
import { usePlanEdits } from '../hooks/usePlanEdits';
import type { PlanRowEdit } from '../lib/planEdits';
import type { PlanLine, PlanLineStatus } from '../lib/planLine';
import { planTotals, type PlanTotals } from '../lib/planDecisions';
import { groupPlanLinesByChannel } from '../lib/planLineGrouping';
import { filterGroupAsksForRecType } from '../lib/planLineFilters';
import { fmtInt, fmtMoney } from '../../lib/format';
import type { ListQueryFilterGroup } from '@/lib/list-query/listQueryService';
import { LevelChangesPanel } from './LevelChangesPanel';
import { PlanBudgetReview } from './PlanBudgetReview';
import { PlanLinesGrid } from './PlanLinesGrid';

/**
 * ONE list (S11) - PlanLinesGrid + PlanBudgetReview + LevelChangesPanel, driven entirely
 * by `usePlanLines(runId)`. Extracted out of the plan page so a second screen (the SCM
 * simulation page's "Planning view" tab) can render the exact same grid, hooks, row panel
 * and decision controls against a different run instead of re-implementing them.
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

  // AC-5b: the grid owns `filterGroup` (its own Filters builder + saved segments) and
  // reports the APPLIED one upward via `onFilterGroupChange` - captured here purely to
  // decide whether to reveal the hidden-by-default rows below, never to drive the grid's
  // own filtering (it already applies the group itself).
  const [appliedFilterGroup, setAppliedFilterGroup] = useState<ListQueryFilterGroup | null>(
    null,
  );

  /**
   * Manual mode hides not-breached covered rows by default (user feedback, 2026-08-12:
   * "if net is not below my reorder level, it is not my business, I don't need to see
   * this in reorder planning").
   *
   * PLAN-plan-list-tile-sheet-one-scope.md, S6 (AC-5): reads the server's own
   * `rec.hidden_by_default` flag instead of recomputing the rule here - the list, the
   * Decisions tile total (`GET .../plan-row-decisions`) and the order sheet export all
   * have to agree on which rows are hidden, and three independent re-derivations could
   * drift. `lineBreachStatus` (`lib/orderQtyLedger.ts`) is unchanged and still drives the
   * order-qty ledger's own "Line not breached" sentence elsewhere - only THIS path stops
   * calling it. Hidden from the DEFAULT list only: an explicit "Covered by stock" status
   * filter still shows every one of them, so nothing is unreachable, just no longer the
   * default. This is `defaultVisibleLines` - what the tile counts (below) always reads,
   * regardless of the AC-5b reveal.
   */
  const defaultVisibleLines = useMemo(() => {
    if (statusFilter === 'covered_by_stock') return planLines.lines;
    const hidden = new Set(
      planLines.lines.filter((l) => l.rec.hidden_by_default === true).map((l) => l.id),
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

  /**
   * PLAN-plan-list-tile-sheet-one-scope.md, AC-5b (owner, 10 Sep: "better to reveal them
   * for flexibility"). A Filters condition asking for Rec type = "Covered by stock" (the
   * dynamic builder or a saved segment, at any nesting depth - `filterGroupAsksForRecType`)
   * reveals every hidden-by-default row, the same early-return shape the existing
   * `statusFilter === 'covered_by_stock'` branch already uses. No new control, no preset:
   * the builder's own Rec type field is the one path. This is what the GRID renders; the
   * tile below stays on `defaultVisibleLines` - the reveal is a lens on what is already
   * on the plan, never a change to what counts as decidable.
   */
  const visibleLines = useMemo(() => {
    if (filterGroupAsksForRecType(appliedFilterGroup, 'covered_by_stock')) {
      return planLines.lines;
    }
    return defaultVisibleLines;
  }, [appliedFilterGroup, planLines.lines, defaultVisibleLines]);

  // Reported over `defaultVisibleLines`, NEVER the (possibly AC-5b-revealed) `visibleLines`:
  // cash figures counting every line - including ones the buyer cannot see by DEFAULT -
  // could report cost for rows nowhere on the tile. Always the per-warehouse (ungrouped)
  // list, even under `groupByChannel`: S16 records a decision on the underlying member
  // recommendation ids, never a synthetic `group:<product_id>` key, so counting the
  // grouped rows here would look the decisions up under a key the map never carries.
  //
  // Keyed on the PRIMITIVE fields, not the totals object itself: a fresh `useMemo` result
  // whenever `defaultVisibleLines` or `decisions` change identity, and a hand-rolled test
  // double may not memoize either at all - depending on the object's identity would refire
  // this effect, call `setState` in the caller, and re-render forever.
  const reportedTotals = useMemo(
    () => planTotals(defaultVisibleLines, planLines.decisions),
    [defaultVisibleLines, planLines.decisions],
  );
  const { decided, undecided, buying, usingStock, usingPo, skipped, units, cost, unpriced } =
    reportedTotals;
  useEffect(() => {
    onTotalsChange?.({ decided, undecided, buying, usingStock, usingPo, skipped, units, cost, unpriced });
    // `appliedFilterGroup` is listed so a reveal/clear RE-ASSERTS the totals explicitly
    // (AC-5b) even on the common case where the DEFAULT figures happen not to change - a
    // caller watching `onTotalsChange` must see, on every filter change, that the tile
    // stayed pinned to the default list rather than infer it from silence.
  }, [decided, undecided, buying, usingStock, usingPo, skipped, units, cost, unpriced, onTotalsChange, appliedFilterGroup]);

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
    planLines.economicsFor,
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
  } Only rows you decided are bought; untouched and skipped rows are left out.`;

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

  /**
   * S12 (round 2, 9 Sep, review fix - AC-S12.1/AC-S12.5): the SAME try/await/toast shape
   * as the toolbar's own `doSave`, so a row's own Save gives the buyer the same feedback
   * a bulk save already does - an unwrapped `planEdits.saveRow` left a rejected save
   * silent, and "Saved" now says which end. `pendingPatch` is the panel's own un-blurred
   * Buy value, flushed straight into the save (`saveRow` merges it before reading the
   * draft - see its own doc for why this cannot go through `onEdit` first). A row with
   * NOTHING drafted (`result === null`, review fix round 3, AC-S12.5) says so rather than
   * firing a PUT for nothing or - the bug this closes - staying silent as if the click
   * never happened. `savingRowIds` (also on the hook) is the per-row disabled guard the
   * panel reads to keep a second click from firing a second PUT.
   */
  const doSaveRow = useCallback(async (line: PlanLine, pendingPatch?: PlanRowEdit) => {
    try {
      const result = await planEdits.saveRow(line, pendingPatch);
      if (!result) {
        toast.info('Nothing to save on this row.');
        return;
      }
      toast.success('Row saved.');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not save this row.');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [planEdits.saveRow]);

  const onSaveRow = useCallback(
    (l: PlanLine, pendingPatch?: PlanRowEdit) => void doSaveRow(l, pendingPatch),
    [doSaveRow],
  );
  const savingFor = useCallback(
    (l: PlanLine) => planEdits.savingRowIds.has(l.id),
    [planEdits.savingRowIds],
  );

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
        // AC-S6.3: Confirm (0) explains itself - a buyer who has decided nothing sees why
        // the button is dead rather than assuming the plan is broken.
        title={
          confirmProducts === 0
            ? 'Decide at least one row first'
            : 'Save, then turn this plan into draft purchase orders'
        }
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
        onFilterGroupChange={setAppliedFilterGroup}
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
        onSaveRow={onSaveRow}
        savingFor={savingFor}
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
