'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import { Info, ShoppingCart } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useBuyRecommendationsForCash } from '../hooks/useReorderRun';
import { useDecisionMutations, useRecommendationDecisions } from '../hooks/useDecisions';
import { applyBudget } from '../services/reorderRunService';
import {
  BUDGET_STEP,
  computeFunding,
  defaultBudgetFor,
  sliderMaxFor,
} from '../lib/reorderCashAllocation';
import { fmtInt } from '../../lib/format';
import type { ReorderRecommendation } from '../types/reorder.types';
import type { AdjustPayload, RejectPayload } from '../types/decisions.types';
import { CashBudgetPanel } from './CashBudgetPanel';
import { CashResultsGrid } from './CashResultsGrid';
import { AdjustRecommendationModal } from './AdjustRecommendationModal';
import { RejectRecommendationDialog } from './RejectRecommendationDialog';
import { BulkRejectDialog } from './BulkRejectDialog';
import { ConfirmActionDialog } from '../../components/ConfirmActionDialog';
import { ReorderExplanationDialog } from './ReorderExplanationDialog';

type PendingBulk = { recs: ReorderRecommendation[]; clear: () => void };

/**
 * M4 Slice A + B — cash-constrained interactive reorder results with the human
 * decision layer. Holds the budget the user slides (Slice A: funded/deferred
 * recompute live client-side against the frozen rank_score), and layers on the
 * Accept / Adjust / Reject decisions + bulk Accept-funded (Slice B, M4-D4/D7/D8/D9).
 * Only BUY recs participate — dispositions/exceptions stay in the read-only grid.
 */
export function CashCopilotResults({
  runId,
  enabled,
}: {
  runId: string | null;
  enabled: boolean;
}) {
  const router = useRouter();
  const { data, isLoading, isError } = useBuyRecommendationsForCash(runId, enabled);
  const { byId: decisionsById } = useRecommendationDecisions(runId, enabled);
  const { accept, adjust, reject, bulkAccept, bulkReject } = useDecisionMutations(runId);

  // Budget is null until the recs land, then seeded from the run's own costed total
  // (real data → data-derived bounds, not a mock constant). User slides thereafter.
  const [budget, setBudget] = useState<number | null>(null);
  const [appliedBudget, setAppliedBudget] = useState<number | null>(null);
  const [isApplying, setIsApplying] = useState(false);
  const [explainRec, setExplainRec] = useState<ReorderRecommendation | null>(null);

  // Decision-layer dialog state.
  const [adjustRec, setAdjustRec] = useState<ReorderRecommendation | null>(null);
  const [rejectRec, setRejectRec] = useState<ReorderRecommendation | null>(null);
  const [pendingBulkAccept, setPendingBulkAccept] = useState<PendingBulk | null>(null);
  const [pendingBulkReject, setPendingBulkReject] = useState<PendingBulk | null>(null);

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

  const viewDraftPoAction = (poId?: string) => ({
    label: 'View draft PO',
    onClick: () => router.push(poId ? `/scm/purchase-orders/${poId}` : '/scm/purchase-orders'),
  });

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

  const handleAccept = async (rec: ReorderRecommendation) => {
    try {
      const res = await accept.mutateAsync(rec);
      toast.success(`Accepted ${rec.sku} — added to draft PO for ${res.supplier_name}`, {
        action: viewDraftPoAction(res.draft_po_id),
      });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to accept recommendation');
    }
  };

  const handleAdjustSubmit = async (payload: AdjustPayload) => {
    if (!adjustRec) return;
    try {
      const res = await adjust.mutateAsync({ rec: adjustRec, payload });
      toast.success(`Adjusted ${adjustRec.sku} — draft PO for ${res.supplier_name} updated`, {
        action: viewDraftPoAction(res.draft_po_id),
      });
      setAdjustRec(null);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to adjust recommendation');
    }
  };

  const handleRejectSubmit = async (payload: RejectPayload) => {
    if (!rejectRec) return;
    try {
      await reject.mutateAsync({ rec: rejectRec, payload });
      toast.success(`Rejected ${rejectRec.sku}`);
      setRejectRec(null);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to reject recommendation');
    }
  };

  const handleBulkAcceptConfirm = async () => {
    if (!pendingBulkAccept) return;
    try {
      const res = await bulkAccept.mutateAsync(pendingBulkAccept.recs);
      pendingBulkAccept.clear();
      toast.success(
        `Accepted ${res.accepted_count} recommendation${res.accepted_count === 1 ? '' : 's'} — ` +
          `${res.po_count} draft PO${res.po_count === 1 ? '' : 's'} created`,
        { action: viewDraftPoAction() },
      );
      setPendingBulkAccept(null);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to accept recommendations');
    }
  };

  const handleBulkRejectConfirm = async (reason: string) => {
    if (!pendingBulkReject) return;
    try {
      const res = await bulkReject.mutateAsync({ recs: pendingBulkReject.recs, reason });
      pendingBulkReject.clear();
      toast.success(
        `Rejected ${res.rejected_count} recommendation${res.rejected_count === 1 ? '' : 's'}`,
      );
      setPendingBulkReject(null);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to reject recommendations');
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
          Accept a funded buy to draft a purchase order (one consolidated draft per supplier), Adjust
          to override qty or switch supplier, or Reject with a reason. Draft POs are held in Purchase
          Orders and are NOT counted as incoming stock until you confirm them. Deferred buys can still
          be actioned — their days-to-stockout shows the risk of waiting.
        </span>
      </div>

      <CashResultsGrid
        rows={funding.funded}
        variant="funded"
        isLoading={false}
        onRowClick={setExplainRec}
        decisionsById={decisionsById}
        onAccept={handleAccept}
        onAdjust={setAdjustRec}
        onReject={setRejectRec}
        onBulkAccept={(recs, clear) => setPendingBulkAccept({ recs, clear })}
        onBulkReject={(recs, clear) => setPendingBulkReject({ recs, clear })}
        selectable
      />
      <CashResultsGrid
        rows={funding.deferred}
        variant="deferred"
        isLoading={false}
        onRowClick={setExplainRec}
        decisionsById={decisionsById}
        onAccept={handleAccept}
        onAdjust={setAdjustRec}
        onReject={setRejectRec}
        onBulkAccept={(recs, clear) => setPendingBulkAccept({ recs, clear })}
        onBulkReject={(recs, clear) => setPendingBulkReject({ recs, clear })}
        selectable
      />
      {/* Always render Needs cost (M4-D16), even when empty — read-only (uncosted
          buys can't be actioned until a cost is added). */}
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

      <AdjustRecommendationModal
        rec={adjustRec}
        open={!!adjustRec}
        onOpenChange={(o) => !o && setAdjustRec(null)}
        onSubmit={handleAdjustSubmit}
        isSubmitting={adjust.isPending}
      />

      <RejectRecommendationDialog
        rec={rejectRec}
        open={!!rejectRec}
        onOpenChange={(o) => !o && setRejectRec(null)}
        onSubmit={handleRejectSubmit}
        isSubmitting={reject.isPending}
      />

      <ConfirmActionDialog
        open={!!pendingBulkAccept}
        onOpenChange={(o) => !o && setPendingBulkAccept(null)}
        title="Accept recommendations?"
        description={
          pendingBulkAccept
            ? `Accept ${fmtInt(pendingBulkAccept.recs.length)} recommendation${
                pendingBulkAccept.recs.length === 1 ? '' : 's'
              }? A consolidated draft purchase order will be created per supplier. Draft POs are not counted as incoming stock until you confirm them.`
            : ''
        }
        confirmLabel="Accept"
        onConfirm={handleBulkAcceptConfirm}
        isBusy={bulkAccept.isPending}
      />

      <BulkRejectDialog
        count={pendingBulkReject?.recs.length ?? 0}
        open={!!pendingBulkReject}
        onOpenChange={(o) => !o && setPendingBulkReject(null)}
        onSubmit={handleBulkRejectConfirm}
        isSubmitting={bulkReject.isPending}
      />
    </div>
  );
}
