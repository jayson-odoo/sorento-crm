'use client';

import { useCallback, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { LoaderCircle, SquarePen } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardHeading, CardTitle, CardToolbar } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { EM_DASH, fmtDate, fmtInt, fmtMoney } from '../../lib/format';
import { runStartedLabel } from '../lib/runListing';
import { searchProductOptions } from '../../services/scmOptionsService';
import { useWarehouseOptions } from '../../hooks/useScmOptions';
import { runHistoryKey, todayRunKey } from '../hooks/useReorderRun';
import { replanReorderRun } from '../services/reorderRunService';
import { ConfirmActionDialog } from '../../components/ConfirmActionDialog';
import type { ReorderRun } from '../types/reorder.types';

/** Read-only field, or its edit-mode input in the SAME place (ADR-PRODUCT-STANDARDS -
 *  view and edit share one layout). Mirrors the `Field` helper other SCM detail pages
 *  already use (`PurchaseOrderDetail.tsx`). */
function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      {htmlFor ? (
        <Label htmlFor={htmlFor} className="text-xs text-muted-foreground">
          {label}
        </Label>
      ) : (
        <span className="text-xs text-muted-foreground">{label}</span>
      )}
      <div className="text-sm">{children}</div>
    </div>
  );
}

/** Today, as the `YYYY-MM-DD` a `<input type="date">` needs - local calendar date. */
function todayDateInputValue(): string {
  const now = new Date();
  const yyyy = now.getFullYear();
  const mm = String(now.getMonth() + 1).padStart(2, '0');
  const dd = String(now.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

/**
 * The plan detail's Header tab (S5, plan 5.1, AC-5.1) - Sales order cut-off, warehouse/
 * product scope, status and the run's own summary counts. View and edit share the SAME
 * layout (ADR-PRODUCT-STANDARDS): editing swaps a read-only value for an input in place.
 *
 * Editing "Sales order cut-off" (G8's "Plan until") OR the warehouse/product scope offers
 * **Re-plan**, not an in-place save: a run is immutable history, so the edit launches a
 * NEW run carrying the edited values, which supersedes this one once it finishes (G8).
 * Decisions carry across for a product/location whose suggestion did not change; a changed
 * one arrives flagged "re-check" on the Lines tab of the new plan (the `ConfirmActionDialog`
 * below states the consequence - no second explanation lives on the page, per the repo's
 * own "no feature explanations in the UI" rule).
 */
export function PlanHeaderTab({
  runId,
  run,
  unsavedCount,
}: {
  runId: string;
  run: ReorderRun;
  /** Decided-but-unsaved rows on the Lines tab (review S5) - the same count `goToPlans`
   *  guards leaving the page with. Re-plan navigates away exactly like Leave does, so it
   *  needs the same guard: dropping unsaved decisions silently just because the exit was
   *  a different button is still dropping them silently. */
  unsavedCount: number;
}) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [isEditing, setIsEditing] = useState(false);
  const [horizon, setHorizon] = useState('');
  const [warehouses, setWarehouses] = useState<string[]>([]);
  const [products, setProducts] = useState<string[]>([]);
  const [productLabels, setProductLabels] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [unsavedWarnOpen, setUnsavedWarnOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const { data: warehouseOptions, isLoading: warehousesLoading, isError: warehousesError } =
    useWarehouseOptions();

  const fetchProductOptions = useCallback(async (query: string) => {
    const options = await searchProductOptions(query);
    setProductLabels((prev) => {
      const next = { ...prev };
      for (const opt of options) next[opt.value] = opt.label;
      return next;
    });
    return options;
  }, []);

  const selectedProductOptions = useMemo(
    () => products.map((code) => ({ value: code, label: productLabels[code] ?? code })),
    [products, productLabels],
  );

  const today = todayDateInputValue();

  const beginEdit = () => {
    // Clamped to today (review nit): a cut-off the run was launched with can already be in
    // the PAST by the time someone edits it, and the date input's own `min={today}` would
    // otherwise show that stored value as invalid the instant the form opens - blocking a
    // scope-only edit that never touched the date at all. Today is the same floor the field
    // already enforces on submit, so clamping the prefill to it changes nothing about what
    // the buyer is allowed to pick.
    const stored = run.plan_horizon_date ?? '';
    setHorizon(stored && stored > today ? stored : stored ? today : '');
    setWarehouses(run.is_all_warehouses ? [] : (run.warehouse_codes ?? []));
    setProducts(run.product_codes ?? []);
    setError(null);
    setIsEditing(true);
  };

  const cancelEdit = () => {
    setIsEditing(false);
    setError(null);
  };

  // A run that has already been re-planned, or is not yet completed, cannot be re-planned
  // again (the backend's own guard) - the Edit control is simply not offered.
  const canReplan = run.status === 'completed' && !run.superseded_by_run_id;

  const openConfirm = () => {
    setError(null);
    if (horizon && horizon < today) {
      setError('The cut-off cannot be in the past - it would leave the run with no demand.');
      return;
    }
    // Re-plan navigates away from THIS run exactly like the "Plans" back-link does
    // (`ReorderPlanView.goToPlans`) - same guard, same reason: leaving drops whatever the
    // Lines tab has decided and not yet saved.
    if (unsavedCount > 0) {
      setUnsavedWarnOpen(true);
      return;
    }
    setConfirmOpen(true);
  };

  const doReplan = async () => {
    setSubmitting(true);
    try {
      const created = await replanReorderRun(runId, {
        warehouse_codes: warehouses,
        product_codes: products,
        plan_horizon_date: horizon || null,
      });
      setConfirmOpen(false);
      setIsEditing(false);
      // Mirrors Start Plan's own accept handler (`ReorderRunsGrid.start`) - the plans list
      // and "today's plan" must see the new run the moment its 202 lands, not stale until
      // their own staleTime lapses.
      void queryClient.invalidateQueries({ queryKey: runHistoryKey });
      void queryClient.invalidateQueries({ queryKey: todayRunKey });
      router.push(`/scm/reorder/${created.run_id}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to re-plan');
    } finally {
      setSubmitting(false);
    }
  };

  const summary = run.summary;
  const warehouseSummary = run.is_all_warehouses
    ? 'All warehouses'
    : (run.warehouse_codes ?? []).length
      ? (run.warehouse_codes ?? []).join(', ')
      : EM_DASH;
  const productSummary =
    run.product_codes === null || run.product_codes === undefined
      ? 'All products'
      : run.product_codes.length
        ? `${fmtInt(run.product_codes.length)} product${run.product_codes.length === 1 ? '' : 's'}`
        : 'None resolved';

  return (
    <div className="space-y-4">
      {run.superseded_by_run_id ? (
        <Alert>
          <AlertDescription>
            This plan has been superseded by a newer plan.{' '}
            <button
              type="button"
              className="font-medium underline underline-offset-2"
              onClick={() => router.push(`/scm/reorder/${run.superseded_by_run_id}`)}
            >
              Open the newer plan
            </button>
          </AlertDescription>
        </Alert>
      ) : null}
      {run.supersedes_run_id ? (
        <Alert>
          <AlertDescription>
            This plan replaced an earlier one.{' '}
            <button
              type="button"
              className="font-medium underline underline-offset-2"
              onClick={() => router.push(`/scm/reorder/${run.supersedes_run_id}`)}
            >
              Open the earlier plan
            </button>
          </AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardHeading>
            <CardTitle>Plan</CardTitle>
          </CardHeading>
          <CardToolbar>
            {canReplan ? (
              isEditing ? (
                <div className="flex items-center gap-2">
                  <Button variant="outline" size="sm" onClick={cancelEdit} disabled={submitting}>
                    Cancel
                  </Button>
                  <Button size="sm" onClick={openConfirm} disabled={submitting}>
                    {submitting ? <LoaderCircle className="size-4 animate-spin" /> : null}
                    Re-plan
                  </Button>
                </div>
              ) : (
                <Button variant="outline" size="sm" onClick={beginEdit}>
                  <SquarePen className="size-4" />
                  Edit
                </Button>
              )
            ) : null}
          </CardToolbar>
        </CardHeader>
        <CardContent className="space-y-4">
          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Field label="Plan">
              <span className="tabular-nums">
                {run.started_at ? runStartedLabel(run.started_at) : EM_DASH}
              </span>
            </Field>
            <Field label="Status">
              {/* This tab only ever renders once the plan is complete - `ReorderPlanView`
                  shows its own running/failed states before the tabs exist at all, so
                  there is no reachable status here other than Completed. */}
              <Badge variant="success" appearance="light" size="sm">
                Completed
              </Badge>
            </Field>
            <Field label="Sales order cut-off" htmlFor={isEditing ? 'plan-header-cutoff' : undefined}>
              {isEditing ? (
                <Input
                  id="plan-header-cutoff"
                  type="date"
                  min={today}
                  value={horizon}
                  onChange={(e) => setHorizon(e.target.value)}
                />
              ) : run.plan_horizon_date ? (
                <span className="tabular-nums">{fmtDate(run.plan_horizon_date)}</span>
              ) : (
                <span className="text-muted-foreground" title="Every open order counted">
                  Every open order
                </span>
              )}
            </Field>

            <Field label="Warehouses" htmlFor={isEditing ? 'plan-header-warehouses' : undefined}>
              {isEditing ? (
                <div className="space-y-1">
                  {warehouses.length ? (
                    <div className="flex justify-end">
                      <button
                        type="button"
                        className="text-2xs font-medium text-primary underline-offset-2 hover:underline"
                        onClick={() => setWarehouses([])}
                      >
                        Clear all
                      </button>
                    </div>
                  ) : null}
                  <SearchableMultiSelect
                    value={warehouses}
                    onChange={setWarehouses}
                    options={warehouseOptions ?? []}
                    disabled={warehousesLoading}
                    placeholder={warehousesLoading ? 'Loading warehouses...' : 'All warehouses'}
                    emptyMessage={warehousesError ? 'Could not load warehouses.' : 'No warehouses found.'}
                  />
                </div>
              ) : (
                <span className="block truncate" title={warehouseSummary}>
                  {warehouseSummary}
                </span>
              )}
            </Field>
            <Field label="Products" htmlFor={isEditing ? 'plan-header-products' : undefined}>
              {isEditing ? (
                <div className="space-y-1">
                  {products.length ? (
                    <div className="flex justify-end">
                      <button
                        type="button"
                        className="text-2xs font-medium text-primary underline-offset-2 hover:underline"
                        onClick={() => setProducts([])}
                      >
                        Clear all
                      </button>
                    </div>
                  ) : null}
                  <SearchableMultiSelect
                    value={products}
                    onChange={setProducts}
                    fetchOptions={fetchProductOptions}
                    selectedOptions={selectedProductOptions}
                    placeholder="All products"
                    emptyMessage="No products found."
                  />
                </div>
              ) : (
                <span>{productSummary}</span>
              )}
            </Field>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardHeading>
            <CardTitle>Counts</CardTitle>
          </CardHeading>
        </CardHeader>
        <CardContent>
          {summary ? (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
              <Field label="Buy">
                <span className="tabular-nums">{fmtInt(summary.buy_count)}</span>
              </Field>
              <Field label="Exceptions">
                <span className="tabular-nums">{fmtInt(summary.exception_count)}</span>
              </Field>
              <Field label="Recommendations">
                <span className="tabular-nums">{fmtInt(summary.recommendation_count)}</span>
              </Field>
              <Field label="Cash impact">
                <span className="tabular-nums">{fmtMoney(summary.total_cash_impact)}</span>
              </Field>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No counts yet.</p>
          )}
        </CardContent>
      </Card>

      <ConfirmActionDialog
        open={unsavedWarnOpen}
        onOpenChange={setUnsavedWarnOpen}
        title="Leave with unsaved changes?"
        description={`${fmtInt(unsavedCount)} product${unsavedCount === 1 ? '' : 's'} carry changes nobody has saved. Re-planning drops them.`}
        confirmLabel="Continue anyway"
        isBusy={false}
        onConfirm={() => {
          setUnsavedWarnOpen(false);
          setConfirmOpen(true);
        }}
      />

      <ConfirmActionDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Re-plan this plan?"
        description="This starts a new plan with the values above and marks this one superseded once it finishes. Decisions carry over automatically wherever the suggestion has not changed; a changed one arrives flagged for another look."
        confirmLabel="Re-plan"
        onConfirm={() => void doReplan()}
        isBusy={submitting}
      />
    </div>
  );
}
