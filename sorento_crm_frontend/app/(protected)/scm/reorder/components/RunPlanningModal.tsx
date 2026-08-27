'use client';

import { useEffect, useState } from 'react';
import { LoaderCircle } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { useProductOptions, useWarehouseOptions } from '../../hooks/useScmOptions';

/** Start Plan inputs (M8-D5, revised; captain 20 Aug dropped the cash budget field -
 *  budget stays a backend/post-run capability only, tightened afterwards on the plan
 *  via `CashBudgetPanel`/`applyBudget`, never set at launch). No market-insight
 *  toggle - market never enters a run; it reaches the plan only through the chat
 *  (Slice E). The legacy `buy_scope` is removed. Warehouse is MULTI-select and
 *  OPTIONAL (pick several, or leave it empty for every warehouse) so a plan can cover
 *  any subset - or the same ground as the daily run. */
export interface ManualPlanInputs {
  /**
   * Optional warehouse scope. **Empty means every warehouse** (P1, captain 25 Aug),
   * exactly as empty products already means every product - the backend resolves an
   * empty list to every active warehouse, so an unnarrowed manual plan covers the
   * same ground as the scheduled daily run.
   */
  warehouse_codes: string[];
  /**
   * Optional product scope (AC-B8a). **Empty means all products**, so the existing
   * behaviour and the scheduled daily run are unchanged. Human product codes, never
   * ids. This is an explicit product list and NOT a reinstatement of the removed
   * `buy_scope` category filter.
   */
  product_codes: string[];
  /**
   * "Sales order cut-off" (captain, 20 Aug; renamed in the revamp). **Empty means no horizon** - every open SO line is
   * planned regardless of when it is needed, today's behaviour. `YYYY-MM-DD` when set;
   * demand needed after it is excluded from this run's netting, and demand carrying no
   * date is always still counted.
   */
  plan_horizon_date: string;
}

/** Today, as the `YYYY-MM-DD` a `<input type="date">` needs - local calendar date, not
 *  `toISOString()`'s UTC one, which reads as yesterday or tomorrow depending on the
 *  browser's own offset. */
function todayDateInputValue(): string {
  const now = new Date();
  const yyyy = now.getFullYear();
  const mm = String(now.getMonth() + 1).padStart(2, '0');
  const dd = String(now.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

/**
 * Start Plan - the one way a person launches a run (plan 4.2). The scheduled daily run
 * (all warehouses, full budget) fires without this modal.
 *
 * Fields in the order the buyer decides them: how far ahead to plan, then which warehouses,
 * then which products. Every one is optional and empty means "everything", which is what
 * makes Start Plan a single click on the day the answer is "the usual".
 *
 * There is no Select all: empty ALREADY means every warehouse, so a button that filled the
 * box with every code produced the same run by a longer route and read as though leaving it
 * blank would do something else.
 */
export function RunPlanningModal({
  open,
  onOpenChange,
  onSubmit,
  isSubmitting,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (inputs: ManualPlanInputs) => void;
  isSubmitting: boolean;
}) {
  const [warehouses, setWarehouses] = useState<string[]>([]);
  const [products, setProducts] = useState<string[]>([]);
  const [horizon, setHorizon] = useState('');
  const [error, setError] = useState<string | null>(null);

  const {
    data: warehouseOptions,
    isLoading: warehousesLoading,
    isError: warehousesError,
  } = useWarehouseOptions();

  const {
    data: productOptions,
    isLoading: productsLoading,
    isError: productsError,
  } = useProductOptions();

  useEffect(() => {
    if (!open) return;
    setWarehouses([]);
    setProducts([]);
    setHorizon('');
    setError(null);
  }, [open]);

  const today = todayDateInputValue();

  const submit = () => {
    setError(null);
    // A past cutoff nets every open line against demand that "must" have been needed
    // before today, which is every line - the run then silently returns zero demand
    // rather than saying why (nit, code review 20 Aug 2026).
    if (horizon && horizon < today) {
      setError('The cut-off cannot be in the past - it would leave the run with no demand.');
      return;
    }
    onSubmit({
      // Empty = every warehouse (P1), the same rule products already carry: narrowing
      // is the exception, and requiring a pick made every manual run harder than the
      // daily one it stands in for.
      warehouse_codes: warehouses,
      // Empty = all products. Products are deliberately NOT required: narrowing to
      // one is the exception, and forcing a pick would make every run harder than
      // the daily one it stands in for.
      product_codes: products,
      // Empty = no horizon (today's behaviour): every open SO line is planned
      // regardless of when it is needed.
      plan_horizon_date: horizon,
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Start Plan</DialogTitle>
        </DialogHeader>

        <DialogBody className="space-y-5">
          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          <div>
            <Label htmlFor="plan-cutoff" className="mb-1 block">
              Sales order cut-off
            </Label>
            <Input
              id="plan-cutoff"
              type="date"
              min={today}
              value={horizon}
              onChange={(e) => setHorizon(e.target.value)}
            />
            <p className="mt-1 text-2xs text-muted-foreground">
              Empty = every open order counts.
            </p>
          </div>

          <div>
            <div className="mb-1 flex items-center justify-between">
              <Label>Warehouses</Label>
              {warehouses.length ? (
                <button
                  type="button"
                  className="text-2xs font-medium text-primary underline-offset-2 hover:underline"
                  onClick={() => setWarehouses([])}
                >
                  Clear all
                </button>
              ) : null}
            </div>
            <SearchableMultiSelect
              value={warehouses}
              onChange={setWarehouses}
              options={warehouseOptions ?? []}
              disabled={warehousesLoading}
              placeholder={warehousesLoading ? 'Loading warehouses...' : 'All warehouses'}
              emptyMessage={warehousesError ? 'Could not load warehouses.' : 'No warehouses found.'}
            />
            <p className="mt-1 text-2xs text-muted-foreground">
              Leave empty to plan every warehouse.
            </p>
          </div>

          <div>
            <div className="mb-1 flex items-center justify-between">
              <Label>Products</Label>
              {products.length ? (
                <button
                  type="button"
                  className="text-2xs font-medium text-primary underline-offset-2 hover:underline"
                  onClick={() => setProducts([])}
                >
                  Clear all
                </button>
              ) : null}
            </div>
            <SearchableMultiSelect
              value={products}
              onChange={setProducts}
              options={productOptions ?? []}
              disabled={productsLoading}
              placeholder={productsLoading ? 'Loading products...' : 'All products'}
              emptyMessage={productsError ? 'Could not load products.' : 'No products found.'}
            />
            <p className="mt-1 text-2xs text-muted-foreground">
              Leave empty to plan every product.
            </p>
          </div>
        </DialogBody>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={isSubmitting}>
            {isSubmitting ? <LoaderCircle className="size-4 animate-spin" /> : null}
            Start Plan
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
