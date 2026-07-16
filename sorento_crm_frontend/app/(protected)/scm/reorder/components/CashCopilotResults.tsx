'use client';

import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { Info, ShoppingCart } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useBuyRecommendationsForCash } from '../hooks/useReorderRun';
import { applyBudget } from '../services/reorderRunService';
import {
  BUDGET_STEP,
  computeFunding,
  defaultBudgetFor,
  sliderMaxFor,
} from '../lib/reorderCashAllocation';
import type { ReorderRecommendation } from '../types/reorder.types';
import { CashBudgetPanel } from './CashBudgetPanel';
import { CashResultsGrid } from './CashResultsGrid';
import { ReorderExplanationDialog } from './ReorderExplanationDialog';

/**
 * M4 Slice A — cash-constrained interactive reorder results. Holds the budget the
 * user slides, recomputes funded/deferred LIVE client-side against the frozen
 * rank_score (M4-D3, no re-run), and persists via "Apply budget". Only BUY recs
 * participate — dispositions/exceptions stay in the read-only planning grid.
 */
export function CashCopilotResults({
  runId,
  enabled,
}: {
  runId: string | null;
  enabled: boolean;
}) {
  const { data, isLoading, isError } = useBuyRecommendationsForCash(runId, enabled);
  // Budget is null until the recs land, then seeded from the run's own costed total
  // (real data → data-derived bounds, not a mock constant). User slides thereafter.
  const [budget, setBudget] = useState<number | null>(null);
  const [appliedBudget, setAppliedBudget] = useState<number | null>(null);
  const [isApplying, setIsApplying] = useState(false);
  const [explainRec, setExplainRec] = useState<ReorderRecommendation | null>(null);

  const baseRecs = useMemo<ReorderRecommendation[]>(() => data ?? [], [data]);

  // Slider bounds derive from THIS run's costed cash (M4-D3, data-driven).
  const sliderMax = useMemo(() => sliderMaxFor(baseRecs), [baseRecs]);
  const defaultBudget = useMemo(() => defaultBudgetFor(baseRecs), [baseRecs]);

  // Seed the budget once the recs arrive (only if the user hasn't slid it yet).
  useEffect(() => {
    if (budget === null && baseRecs.length) setBudget(defaultBudget);
  }, [budget, baseRecs, defaultBudget]);

  const effectiveBudget = budget ?? defaultBudget;

  // Live funded/deferred split — recomputes on every slider tick client-side
  // against the frozen rank_score (M4-D3, no round-trip). "Apply budget" persists.
  const funding = useMemo(
    () => computeFunding(baseRecs, effectiveBudget),
    [baseRecs, effectiveBudget],
  );

  // The dialog's prev/next pager steps within the currently viewed section.
  const explainSection = useMemo(() => {
    if (!explainRec) return funding.funded;
    if (explainRec.funding_status === 'deferred') return funding.deferred;
    if (explainRec.funding_status === 'needs_cost') return funding.needsCost;
    return funding.funded;
  }, [explainRec, funding]);

  const handleApply = async () => {
    if (!runId) return;
    setIsApplying(true);
    try {
      const res = await applyBudget(runId, effectiveBudget);
      setAppliedBudget(effectiveBudget);
      const needsCostNote = res.needs_cost_count
        ? `, ${res.needs_cost_count} need cost`
        : '';
      toast.success(
        `Budget applied — ${res.funded_count} funded, ${res.deferred_count} deferred${needsCostNote}`,
      );
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to apply budget');
    } finally {
      setIsApplying(false);
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-5">
        <Skeleton className="h-44 w-full rounded-xl" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    );
  }

  if (isError) {
    return (
      <Card className="p-6 text-center text-sm text-scm-stockout">
        Couldn&apos;t load the buy recommendations. Retry the run from the toolbar.
      </Card>
    );
  }

  if (!baseRecs.length) {
    return (
      <Card className="flex flex-col items-center gap-3 p-10 text-center">
        <span className="flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
          <ShoppingCart className="size-6" aria-hidden />
        </span>
        <div>
          <div className="text-sm font-semibold">No buy recommendations to fund</div>
          <p className="mt-1 max-w-md text-sm text-muted-foreground">
            This run produced no reorders, so there is nothing to rank against a cash budget.
          </p>
        </div>
      </Card>
    );
  }

  return (
    <div className="space-y-5">
      <CashBudgetPanel
        budget={effectiveBudget}
        onBudgetChange={setBudget}
        sliderMax={sliderMax}
        step={BUDGET_STEP}
        funding={funding}
        onApply={handleApply}
        isApplying={isApplying}
        appliedBudget={appliedBudget}
      />

      <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/30 p-3 text-sm text-muted-foreground">
        <Info className="mt-0.5 size-4 shrink-0" />
        <span>
          Funded buys fit the budget in rank order; a buy that overflows the remaining budget is
          skipped and the next one that fits is funded instead. Deferred buys are never dropped —
          their days-to-stockout shows the risk of waiting. Uncosted buys can&apos;t be cash-ranked,
          so they sit in Needs cost. Click any row to see how it was reached.
        </span>
      </div>

      <CashResultsGrid
        rows={funding.funded}
        variant="funded"
        isLoading={false}
        onRowClick={setExplainRec}
      />
      <CashResultsGrid
        rows={funding.deferred}
        variant="deferred"
        isLoading={false}
        onRowClick={setExplainRec}
      />
      {/* Always render Needs cost (M4-D16), even when empty. */}
      <CashResultsGrid
        rows={funding.needsCost}
        variant="needs_cost"
        isLoading={false}
        onRowClick={setExplainRec}
      />

      <ReorderExplanationDialog
        rec={explainRec}
        open={!!explainRec}
        onOpenChange={(o) => !o && setExplainRec(null)}
        recs={explainSection}
        totalCount={explainSection.length}
        pageItemOffset={0}
        onNavigate={setExplainRec}
      />
    </div>
  );
}
