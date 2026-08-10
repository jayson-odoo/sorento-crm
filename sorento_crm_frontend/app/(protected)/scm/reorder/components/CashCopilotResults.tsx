'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { toast } from 'sonner';
import {
  DndContext,
  DragOverlay,
  MouseSensor,
  TouchSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core';
import { CheckCheck, Info, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Slider, SliderThumb } from '@/components/ui/slider';
import { fmtInt, fmtMoney } from '../../lib/format';
import { ConfirmActionDialog } from '../../components/ConfirmActionDialog';
import type { M8PlanState } from '../hooks/useReorderPlan';
import { formatDateInMalaysia } from '@/lib/helpers';
import { useCashBudget, useSaveCashBudget } from '../hooks/useCashBudget';
import { m8CashImpact, type M8PlanRow } from '../lib/planRow';
import { BUDGET_STEP } from '../lib/reorderCashAllocation';
import type { ReorderRecommendation } from '../types/reorder.types';
import { CashResultsGrid } from './CashResultsGrid';
import { ReorderExplanationDialog } from './ReorderExplanationDialog';

/**
 * SCM M8 (slice C) - the funded/deferred experience as ONE table with two
 * draggable sections. Owns the budget control (in the Within-budget header), the
 * drag-between-sections wiring, the needs-cost banner, and the confirm-decisions
 * bar. All plan state lives in the shared `useReorderPlan` hook so the assistant's
 * market bumps land on the same rows. Phase 2: wired to the live backend.
 */
export function CashCopilotResults({ plan }: { plan: M8PlanState }) {
  const { funding, displayRank, decisions, editedIds, poByRow, budget, setBudget, fund, defer, reject, editRow, confirm: runConfirm, isConfirming } = plan;
  // The standing company figure behind the budget control, so the header can say whose
  // number it is and let the buyer make theirs the standing one.
  const cashBudgetQuery = useCashBudget();
  const cashBudget = cashBudgetQuery.data;
  const saveBudget = useSaveCashBudget();
  const onSaveBudget = (amount: number) => saveBudget.mutate({ budget_amount: amount });
  const savingBudget = saveBudget.isPending;
  const [bannerDismissed, setBannerDismissed] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [activeRow, setActiveRow] = useState<M8PlanRow | null>(null);
  // Row-click detail (M8-C10): reuse the existing ReorderExplanationDialog, fed a
  // recommendation adapted from the mock row. See m8RowToRecommendation.
  const [detailRec, setDetailRec] = useState<ReorderRecommendation | null>(null);
  // Local string mirror of the numeric budget so the input is fully clearable
  // (empty = 0 for the split, but shown blank - no stuck leading "0"). Re-syncs
  // when the budget changes from elsewhere (e.g. a manual-plan run).
  const [budgetText, setBudgetText] = useState(() => (budget ? String(budget) : ''));
  useEffect(() => {
    if ((Number(budgetText) || 0) !== budget) setBudgetText(budget ? String(budget) : '');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [budget]);

  const sensors = useSensors(
    useSensor(MouseSensor, { activationConstraint: { distance: 5 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 150, tolerance: 8 } }),
  );

  const allRows = [...funding.within, ...funding.over];
  // Slider ceiling = the plan's TRUE cash impact (Σ all costed cash), rounded up to a
  // step. No headroom: at max every buy is funded and free ≈ 0 - budgeting beyond the
  // total buys nothing, so the slider must not run past it (min one step so the track
  // is always draggable even on a tiny plan).
  const sliderMax = useMemo(() => {
    const total = allRows.reduce((s, r) => s + (m8CashImpact(r) ?? 0), 0);
    if (total <= 0) return BUDGET_STEP;
    return Math.ceil(total / BUDGET_STEP) * BUDGET_STEP;
  }, [allRows]);
  // The confirm bar materialises draft POs, which only happens for ACCEPTED/adjusted
  // (decision-funded) lines - NOT merely for within-budget rows the user hasn't acted
  // on. Gate the bar + its count on accepted decisions (M8-F2). Adjusted rows are
  // pinned, so they read 'accepted' in the decision map and are counted here too.
  // M8-F9: a line that has ALREADY been confirmed into a draft PO is no longer
  // "pending confirmation" - exclude it so the bar's count shrinks after Confirm and
  // hides once every accepted line has its PO.
  const acceptedCount = Object.entries(decisions).filter(
    ([id, d]) => d === 'accepted' && !poByRow[id],
  ).length;
  const hasAcceptedDecisions = acceptedCount > 0;
  // The real recommendations behind the visible rows, so the detail dialog can page
  // across them (arrow-key / prev-next navigation) and fetch each rec's real AI
  // summary / advisory / Q&A + derivation (M8-C10).
  const detailRecs = useMemo(
    () => [...funding.within, ...funding.over].map((r) => r.rec),
    [funding.within, funding.over],
  );

  // M8-F14: "Review & add cost" deep-links to the product listing so the buyer can
  // add the missing supplier cost. The products list (/master-data-management/products)
  // restores a single free-text `query` from the URL, so a SINGLE skipped SKU
  // pre-filters precisely; when several are skipped, one free-text term can't filter
  // to a set (no SKU-set param exists), so we land on the unfiltered list rather than
  // invent a route - the banner still states how many were skipped.
  const needsCostSkus = useMemo(
    () => funding.needsCost.map((r) => r.sku).filter(Boolean),
    [funding.needsCost],
  );
  const reviewCostHref =
    needsCostSkus.length === 1
      ? `/master-data-management/products?query=${encodeURIComponent(needsCostSkus[0])}`
      : '/master-data-management/products';

  const onDragStart = (e: DragStartEvent) => {
    setActiveRow(allRows.find((r) => r.id === e.active.id) ?? null);
  };

  const onDragEnd = (e: DragEndEvent) => {
    setActiveRow(null);
    const over = e.over?.data.current?.section as 'within' | 'over' | undefined;
    const from = e.active.data.current?.section as 'within' | 'over' | undefined;
    if (!over || over === from) return;
    const row = allRows.find((r) => r.id === e.active.id);
    if (!row) return;
    if (over === 'within') fund(row); // drag up = pin/fund (no reason needed)
    else defer(row); // drag down = defer
  };

  const handleConfirm = async () => {
    try {
      const res = await runConfirm();
      setConfirmOpen(false);
      const poCount = res?.po_count ?? 0;
      toast.success(
        `Confirmed ${fmtInt(res?.confirmed_count ?? acceptedCount)} decision${(res?.confirmed_count ?? acceptedCount) === 1 ? '' : 's'} - ${fmtInt(poCount)} consolidated draft PO${poCount === 1 ? '' : 's'} ready to review`,
      );
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to confirm decisions');
    }
  };

  const budgetHeader = (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <div className="flex items-center gap-2">
        <Label htmlFor="cash-budget" className="text-xs text-muted-foreground">
          Cash budget
        </Label>
        <div className="flex items-center gap-1">
          <span className="text-xs text-muted-foreground">RM</span>
          <Input
            id="cash-budget"
            type="text"
            inputMode="numeric"
            value={budgetText}
            onChange={(e) => {
              const raw = e.target.value.replace(/[^0-9]/g, '');
              setBudgetText(raw);
              setBudget(raw === '' ? 0 : Number(raw));
            }}
            placeholder="0"
            className="h-8 w-28 text-right tabular-nums"
          />
        </div>
      </div>
      {/* Slider mirrors the numeric input (M8: drag OR type) - same clamp + step as the
          server allocator, so a drag lands the funded boundary exactly where a typed
          value would. Kept compact so it sits inline in the section header. */}
      <Slider
        value={[Math.min(budget, sliderMax)]}
        min={0}
        max={sliderMax}
        step={BUDGET_STEP}
        onValueChange={([v]) => {
          const next = Math.max(0, Math.min(v, sliderMax));
          setBudget(next);
          setBudgetText(next ? String(next) : '');
        }}
        aria-label="Cash budget slider"
        className="w-40 sm:w-48"
      >
        <SliderThumb aria-label="Budget amount" />
      </Slider>
      {/* Where the number CAME from. Without this the budget reads as a fact about the
          company when it may be nothing of the sort - which is how a plan came to show
          "Over budget" against a limit nobody had set. */}
      <div className="flex items-center gap-2 text-2xs text-muted-foreground">
        {cashBudget?.configured ? (
          <span>
            Company budget
            {cashBudget.period_start && cashBudget.period_end
              ? ` · ${formatDateInMalaysia(cashBudget.period_start)} to ${formatDateInMalaysia(cashBudget.period_end)}`
              : ''}
          </span>
        ) : (
          <span>No company budget set, so the whole plan is shown</span>
        )}
        {budget > 0 && budget !== (cashBudget?.budget_amount ?? -1) ? (
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-2xs"
            onClick={() => onSaveBudget(budget)}
            disabled={savingBudget}
          >
            Save as our budget
          </Button>
        ) : null}
      </div>
      <div className="text-right text-2xs leading-tight">
        <div className="tabular-nums">{fmtMoney(funding.committed)} committed</div>
        <div className={funding.free < 0 ? 'text-scm-stockout tabular-nums' : 'text-scm-incoming tabular-nums'}>
          {fmtMoney(funding.free)} {funding.free < 0 ? 'over' : 'free'}
        </div>
      </div>
    </div>
  );

  return (
    <div className="space-y-4">
      {/* Confirm-decisions bar - draft POs are created here (M8-C8), so it only shows
          once at least one line is accepted/adjusted (M8-F2). */}
      {hasAcceptedDecisions ? (
        <div className="flex flex-col gap-2 rounded-lg border border-primary/40 bg-primary/5 p-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2.5 text-sm">
            <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <CheckCheck className="size-4.5" aria-hidden />
            </span>
            <span>
              <span className="font-semibold tabular-nums">{fmtInt(acceptedCount)}</span> accepted line
              {acceptedCount === 1 ? '' : 's'}, ready to confirm into draft purchase orders
            </span>
          </div>
          <Button onClick={() => setConfirmOpen(true)} className="shrink-0">
            <CheckCheck className="size-4" />
            Confirm decisions
          </Button>
        </div>
      ) : null}

      <DndContext
        sensors={sensors}
        onDragStart={onDragStart}
        onDragEnd={onDragEnd}
        onDragCancel={() => setActiveRow(null)}
      >
        <CashResultsGrid
          runId={plan.runId ?? null}
          within={funding.within}
          over={funding.over}
          decisions={decisions}
          editedIds={editedIds}
          poByRow={poByRow}
          displayRank={displayRank}
          budgetHeader={budgetHeader}
          handlers={{ onFund: fund, onReject: reject, onEdit: editRow }}
          onOpenDetail={(row) => setDetailRec(row.rec)}
        />
        <DragOverlay dropAnimation={null}>
          {activeRow ? (
            <div className="rounded-md border bg-background px-3 py-1.5 text-xs font-medium shadow-md">
              {activeRow.sku}
            </div>
          ) : null}
        </DragOverlay>
      </DndContext>

      {/* Needs-cost banner (M8-C7) - not a third section, just a dismissible note. */}
      {funding.needsCost.length > 0 && !bannerDismissed ? (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-muted/40 px-3 py-2 text-sm">
          <Info className="size-4 shrink-0 text-muted-foreground" aria-hidden />
          <span className="text-muted-foreground">
            <span className="font-medium text-foreground tabular-nums">
              {fmtInt(funding.needsCost.length)}
            </span>{' '}
            product{funding.needsCost.length === 1 ? '' : 's'} skipped - no supplier cost yet.
          </span>
          <Link
            href={reviewCostHref}
            className="font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
            title={
              needsCostSkus.length === 1
                ? `Review ${needsCostSkus[0]} in Products`
                : 'Review these products in Products'
            }
          >
            Review &amp; add cost
          </Link>
          <button
            type="button"
            className="ms-auto rounded-sm p-1 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-label="Dismiss"
            onClick={() => setBannerDismissed(true)}
          >
            <X className="size-4" aria-hidden />
          </button>
        </div>
      ) : null}

      <ConfirmActionDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Confirm decisions?"
        description={
          `This creates a consolidated draft purchase order per supplier from your ` +
          `${fmtInt(acceptedCount)} accepted line${acceptedCount === 1 ? '' : 's'}. ` +
          `Draft POs are held in Purchase Orders and are NOT counted as incoming stock until you ` +
          `confirm the draft there.`
        }
        confirmLabel="Confirm decisions"
        onConfirm={handleConfirm}
        isBusy={isConfirming}
      />

      {/* Row-click recommendation detail (M8-C10) - the pre-M8 row-detail view,
          reused intact. Phase 2 feeds it the real recommendation (and its AI
          summary / advisory / Q&A) instead of the mock-row adapter. */}
      <ReorderExplanationDialog
        rec={detailRec}
        open={!!detailRec}
        onOpenChange={(o) => !o && setDetailRec(null)}
        recs={detailRecs}
        totalCount={detailRecs.length}
        onNavigate={setDetailRec}
        poLink={detailRec ? poByRow[detailRec.id] ?? null : null}
      />
    </div>
  );
}
